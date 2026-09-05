import ast
import json
import math
import os
import re
from importlib import import_module
from pathlib import Path
from typing import Literal, TypedDict, cast

from openai import APITimeoutError, OpenAI

github_api = import_module("common.github-api")
SKILL_PATH = Path(__file__).resolve().parents[2] / ".agents/skills/code-review/SKILL.md"


class ReviewComment(TypedDict):
    path: str
    start_line: int
    end_line: int
    side: Literal["LEFT", "RIGHT"]
    body: str


def diff_ranges(diff: str) -> list[tuple[str, str, int, int]]:
    """Validate hunk lengths and index inclusive file ranges on both sides."""
    ranges: list[tuple[str, str, int, int]] = []
    old_path = new_path = ""
    remaining_old = remaining_new = 0
    in_hunk = False

    def parse_path(value: str) -> str:
        if value.startswith('"'):
            value = ast.literal_eval("b" + value).decode("utf-8")
        return value if value == "/dev/null" else value[2:]

    for line in diff.split("\n"):
        if in_hunk and (remaining_old or remaining_new):
            if line.startswith("\\ No newline at end of file"):
                continue
            if line.startswith(" "):
                remaining_old -= 1
                remaining_new -= 1
            elif line.startswith("-"):
                remaining_old -= 1
            elif line.startswith("+"):
                remaining_new -= 1
            else:
                raise ValueError("Malformed or truncated diff hunk")
            if min(remaining_old, remaining_new) < 0:
                raise ValueError("Diff hunk length mismatch")
            continue
        in_hunk = False
        if line.startswith("diff --git "):
            old_path = new_path = ""
        elif line.startswith("--- "):
            old_path = parse_path(line[4:])
        elif line.startswith("+++ "):
            new_path = parse_path(line[4:])
        elif line.startswith("@@"):
            match = re.fullmatch(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@.*", line)
            if not match or not old_path or not new_path:
                raise ValueError("Malformed diff hunk header")
            old_start, new_start = int(match[1]), int(match[3])
            remaining_old = int(match[2]) if match[2] is not None else 1
            remaining_new = int(match[4]) if match[4] is not None else 1
            path = old_path if new_path == "/dev/null" else new_path
            for side, start, count in (
                ("LEFT", old_start, remaining_old),
                ("RIGHT", new_start, remaining_new),
            ):
                if count:
                    ranges.append((path, side, start, start + count - 1))
            in_hunk = True
    if remaining_old or remaining_new:
        raise ValueError("Truncated diff hunk")
    return ranges


def validate_comments(content: str, diff: str) -> list[ReviewComment]:
    """Reject the entire response before posting if any item is invalid."""
    result = json.loads(content)
    if not isinstance(result, dict) or set(result) != {"comments"}:
        raise ValueError("Review must be a JSON object containing only comments")
    if not isinstance(result["comments"], list):
        raise TypeError("comments must be an array")
    ranges = diff_ranges(diff)
    comments: list[ReviewComment] = []
    for item in result["comments"]:
        if not isinstance(item, dict) or set(item) != {
            "path",
            "start_line",
            "end_line",
            "side",
            "body",
        }:
            raise ValueError("Invalid review comment fields")
        if (
            not isinstance(item["path"], str)
            or not isinstance(item["body"], str)
            or not item["body"].strip()
            or item["side"] not in ("LEFT", "RIGHT")
            or type(item["start_line"]) is not int
            or type(item["end_line"]) is not int
            or not 1 <= item["start_line"] <= item["end_line"]
        ):
            raise ValueError("Invalid review comment values")
        if not any(
            item["path"] == path
            and item["side"] == side
            and start <= item["start_line"] <= item["end_line"] <= end
            for path, side, start, end in ranges
        ):
            raise ValueError("Review comment range is outside a single diff hunk")
        comment = cast(ReviewComment, item)
        if comment not in comments:
            comments.append(comment)
    return comments


def render_hunk(
    header: str, old: int, new: int, body: str, old_size: int, new_size: int
) -> str:
    """Render a fragment with original file coordinates and updated counts."""
    old_start = old if old_size else max(0, old - 1)
    new_start = new if new_size else max(0, new - 1)
    return header + f"@@ -{old_start},{old_size} +{new_start},{new_size} @@\n" + body


def split_diff_batches(diff: str, max_chars: int) -> list[str]:
    """Pack files/hunks; split oversized hunks at lines with original coordinates."""
    if max_chars <= 0:
        raise ValueError("LLM_BATCH_MAX_CHARS must be positive")
    diff_ranges(diff)
    units: list[str] = []
    files = re.split(r"(?m)(?=^diff --git )", diff)
    for file_diff in files:
        if not file_diff.strip():
            continue
        if not file_diff.startswith("diff --git "):
            raise ValueError("Expected a GitHub unified diff file header")
        hunks = list(re.finditer(r"(?m)^@@ .*", file_diff))
        if not hunks:
            print(f"Skipping non-text change: {file_diff.splitlines()[0]}", flush=True)
            continue
        if len(file_diff) <= max_chars:
            units.append(file_diff)
            continue
        header = file_diff[: hunks[0].start()]
        for i, match in enumerate(hunks):
            end = hunks[i + 1].start() if i + 1 < len(hunks) else len(file_diff)
            hunk = file_diff[match.start() : end]
            if len(header + hunk) <= max_chars:
                units.append(header + hunk)
                continue
            coordinates = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", hunk)
            if coordinates is None:
                raise ValueError("Invalid hunk coordinates")
            old, new = int(coordinates[1]), int(coordinates[2])
            # Keep no-newline markers attached to their preceding code line.
            records: list[str] = []
            for line in hunk.splitlines(keepends=True)[1:]:
                if line.startswith("\\ No newline at end of file") and records:
                    records[-1] += line
                else:
                    records.append(line)
            chunk = ""
            old_count = new_count = 0

            # Zero-count original sides point to the preceding line already.
            original = re.match(r"@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@", hunk)
            if original and original[1] == "0":
                old += 1
            if original and original[2] == "0":
                new += 1
            for record in records:
                add_old = int(record.startswith((" ", "-")))
                add_new = int(record.startswith((" ", "+")))
                if (
                    chunk
                    and len(
                        render_hunk(
                            header,
                            old,
                            new,
                            chunk + record,
                            old_count + add_old,
                            new_count + add_new,
                        )
                    )
                    > max_chars
                ):
                    units.append(
                        render_hunk(header, old, new, chunk, old_count, new_count)
                    )
                    old += old_count
                    new += new_count
                    chunk = ""
                    old_count = new_count = 0
                if (
                    len(
                        render_hunk(
                            header,
                            old,
                            new,
                            chunk + record,
                            old_count + add_old,
                            new_count + add_new,
                        )
                    )
                    > max_chars
                ):
                    raise ValueError(
                        "One diff line plus headers exceeds LLM_BATCH_MAX_CHARS; increase the limit"
                    )
                chunk += record
                old_count += add_old
                new_count += add_new
            if chunk:
                units.append(render_hunk(header, old, new, chunk, old_count, new_count))
    batches: list[str] = []
    current = ""
    for unit in units:
        separator = "\n" if current and not current.endswith("\n") else ""
        if current and len(current + separator + unit) > max_chars:
            batches.append(current)
            current = ""
            separator = ""
        current += separator + unit
    if current:
        batches.append(current)
    for batch in batches:
        diff_ranges(batch)
    return batches


def review_batch(
    diff: str, llm_api_key: str, skill: str, timeout: float
) -> list[ReviewComment]:
    """Review one bounded batch without publishing any comments."""
    with OpenAI(
        api_key=llm_api_key,
        base_url="https://api.siliconflow.cn/v1",
        timeout=timeout,
        max_retries=0,
    ) as client:
        response = client.chat.completions.create(
            model="zai-org/GLM-5.3",
            extra_body={"enable_thinking": False},
            messages=[
                {"role": "system", "content": skill},
                {
                    "role": "user",
                    "content": "请按 skill 审查以下 diff 批次，只返回约定的 JSON。"
                    "这是完整 PR 的一部分，只评论本批次中有充分证据的问题，不推测缺失上下文。"
                    "你没有源码读取或执行工具。\n\n" + diff,
                },
            ],
        )
    if not response.choices or response.choices[0].finish_reason != "stop":
        raise ValueError("LLM review did not finish normally; no comments posted")
    content = response.choices[0].message.content
    if not content or not content.strip():
        raise ValueError("LLM returned no review JSON")
    return validate_comments(content, diff)


def review_diff(diff: str, llm_api_key: str) -> list[ReviewComment]:
    if not diff.strip():
        return []
    timeout = float(os.environ.get("LLM_TIMEOUT_SECONDS", "600"))
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("LLM_TIMEOUT_SECONDS must be a finite positive number")
    limit = int(os.environ.get("LLM_BATCH_MAX_CHARS", "12000"))
    batches = split_diff_batches(diff, limit)
    skill = SKILL_PATH.read_text(encoding="utf-8")
    comments: list[ReviewComment] = []
    for index, batch in enumerate(batches, 1):
        print(
            f"Reviewing batch {index}/{len(batches)}: {len(batch)} diff characters "
            f"(timeout: {timeout:g}s)...",
            flush=True,
        )
        result = review_batch(batch, llm_api_key, skill, timeout)
        for item in result:
            if item not in comments:
                comments.append(item)
    # Recheck against the complete PR before allowing publication.
    return validate_comments(json.dumps({"comments": comments}), diff)


def main() -> None:

    repo = os.environ["GITHUB_REPOSITORY"]
    pr_number = int(os.environ["PR_NUMBER"])
    token = os.environ["GITHUB_TOKEN"]
    api_url = os.environ.get("GITHUB_API_URL", "https://api.github.com")
    head_sha = os.environ["PR_HEAD_SHA"]
    github_api.assert_pull_request_head(
        repo, pr_number, token, head_sha, api_url=api_url
    )
    diff = github_api.get_pull_request_diff(repo, pr_number, token, api_url=api_url)
    github_api.assert_pull_request_head(
        repo, pr_number, token, head_sha, api_url=api_url
    )
    print(f"Fetched PR #{pr_number} diff ({len(diff)} characters).", flush=True)
    if not diff.strip():
        print("Empty diff; skipping review and comments.")
        return
    try:
        comments = review_diff(diff, os.environ["LLM_API_KEY"])
    except APITimeoutError:
        raise SystemExit(
            "GLM review timed out; no comments posted. "
            "Retry the CI job or increase LLM_TIMEOUT_SECONDS "
            "if the service needs more time for this diff."
        ) from None
    if not comments:
        print("No review findings; no comments posted.")
        return
    github_api.assert_pull_request_head(
        repo, pr_number, token, head_sha, api_url=api_url
    )
    for item in comments:
        comment = github_api.create_pull_request_comment(
            repo, pr_number, token, commit_id=head_sha, api_url=api_url, **item
        )
        print(f"Created review comment: {comment['html_url']}")


if __name__ == "__main__":
    main()
