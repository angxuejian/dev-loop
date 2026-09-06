import ast
import json
import math
import os
import re
import subprocess
import unicodedata
from importlib import import_module
from pathlib import Path
from typing import Literal, TypedDict, cast

from openai import APITimeoutError, OpenAI
from openai.types.chat import ChatCompletionMessageParam

github_api = import_module("common.github-api")
SKILL_PATH = Path(__file__).resolve().parents[1] / ".agents/skills/code-review/SKILL.md"
REVIEW_FILE_EXTENSIONS = {".py", ".js", ".ts"}
REVIEW_DIRECTORIES = {"backend", "frontend"}
MAX_COMMENT_BODY_BYTES = 10_000


class ReviewComment(TypedDict):
    severity: Literal["HIGH_WARNING", "DANGER", "HIGH_DANGER"]
    path: str
    start_line: int
    end_line: int
    side: Literal["LEFT", "RIGHT"]
    body: str


def validate_comment_body(body: str) -> None:
    """Allow ordinary Markdown, but reject unsafe text without echoing it."""
    if any(
        unicodedata.category(char) in {"Cc", "Cs"} and char not in "\t\n\r"
        for char in body
    ):
        raise ValueError("Review comment body contains invalid characters")
    if len(body.encode("utf-8")) > MAX_COMMENT_BODY_BYTES:
        raise ValueError("Review comment body exceeds the byte limit")


def parse_diff_path(value: str) -> str:
    """Decode a Git file header into a repository-relative path."""
    if value.startswith('"'):
        value = ast.literal_eval("b" + value).decode("utf-8")
    if value == "/dev/null":
        return value
    if not value.startswith(("a/", "b/")):
        raise ValueError("Expected a Git diff path prefix")
    return value[2:]


def diff_ranges(diff: str) -> list[tuple[str, str, int, int]]:
    """Validate hunk lengths and index inclusive file ranges on both sides."""
    ranges: list[tuple[str, str, int, int]] = []
    old_path = new_path = ""
    remaining_old = remaining_new = 0
    in_hunk = False

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
            old_path = parse_diff_path(line[4:])
        elif line.startswith("+++ "):
            new_path = parse_diff_path(line[4:])
        elif line.startswith("@@"):
            match = re.fullmatch(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@.*", line)
            if not match or not old_path or not new_path:
                raise ValueError("Malformed diff hunk header")
            old_start, new_start = int(match[1]), int(match[3])
            remaining_old = int(match[2]) if match[2] is not None else 1
            remaining_new = int(match[4]) if match[4] is not None else 1
            path = old_path if new_path == "/dev/null" else new_path
            for side, side_path, start, count in (
                ("LEFT", old_path, old_start, remaining_old),
                ("RIGHT", new_path, new_start, remaining_new),
            ):
                if count and side_path != "/dev/null":
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
            "severity",
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
            or item["severity"] not in {"HIGH_WARNING", "DANGER", "HIGH_DANGER"}
            or item["side"] not in ("LEFT", "RIGHT")
            or type(item["start_line"]) is not int
            or type(item["end_line"]) is not int
            or not 1 <= item["start_line"] <= item["end_line"]
        ):
            raise ValueError("Invalid review comment values")
        validate_comment_body(item["body"])
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


def filter_review_diff(diff: str) -> str:
    """Keep textual file diffs within the review directories and extensions."""
    selected: list[str] = []
    file_header = (
        r'diff --git (?:a/[^"\r\n]+|"a/(?:\\[^\r\n]|[^"\\\r\n])+") '
        r'(?:b/[^"\r\n]+|"b/(?:\\[^\r\n]|[^"\\\r\n])+")(?=\r?$)'
    )
    for file_diff in re.split(rf"(?m)(?=^{file_header})", diff):
        if not file_diff.strip():
            continue
        if not re.match(file_header, file_diff, re.MULTILINE):
            raise ValueError("Expected a GitHub unified diff file header")
        hunk = re.search(r"(?m)^@@ ", file_diff)
        if hunk is None:
            continue
        headers = file_diff[: hunk.start()].splitlines()
        old_path = new_path = ""
        for line in headers:
            if line.startswith(("--- ", "+++ ")):
                path = parse_diff_path(line[4:])
                if line.startswith("--- "):
                    old_path = path
                else:
                    new_path = path
        path = old_path if new_path == "/dev/null" else new_path
        file_path = Path(path)
        if (
            len(file_path.parts) >= 2
            and file_path.parts[0] in REVIEW_DIRECTORIES
            and file_path.suffix in REVIEW_FILE_EXTENSIONS
        ):
            selected.append(file_diff)
    return "".join(selected)


def load_feature_context() -> str:
    """Read the current PR or local branch's optional feature specification."""
    root = Path(__file__).resolve().parents[1]
    branch = (
        os.environ.get("GITHUB_HEAD_REF")
        or subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    if not branch:
        return ""
    features = (root / "features").resolve()
    path = (features / f"{branch}.md").resolve()
    if not path.is_relative_to(features):
        raise ValueError("Feature path must be within features/")
    return path.read_text(encoding="utf-8").strip() if path.is_file() else ""


def review_diff(
    diff: str,
    llm_api_key: str,
    existing_comments: list[dict[str, object]] | None = None,
    *,
    feature: str = "",
) -> list[ReviewComment]:
    """Review the already-filtered source diff in one request."""

    if not diff.strip():
        return []
    timeout = float(os.environ.get("LLM_TIMEOUT_SECONDS", "600"))
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("LLM_TIMEOUT_SECONDS must be a finite positive number")
    skill = SKILL_PATH.read_text(encoding="utf-8")
    history = existing_comments or []
    history_context = [
        {
            "path": comment.get("path"),
            "line": comment.get("line"),
            "side": comment.get("side"),
            "body": str(comment.get("body", ""))[:2_000],
        }
        for comment in history[-100:]
    ]
    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": skill},
    ]
    if feature:
        messages.append(
            {
                "role": "system",
                "content": "Feature 需求与验收标准（参考上下文）：\n" + feature,
            }
        )
    messages.append(
        {
            "role": "system",
            "content": "历史评论（包括已解决的，参考上下文）：\n"
            + json.dumps(history_context, ensure_ascii=False, indent=2),
        }
    )
    messages.append(
        {
            "role": "user",
            "content": "请按 skill 审查以下 diff。\n\nDiff:\n" + diff,
        }
    )
    print(
        f"Reviewing {len(diff)} source diff characters in one request "
        f"(timeout: {timeout:g}s)...",
        flush=True,
    )
    with OpenAI(
        api_key=llm_api_key,
        base_url="https://api.siliconflow.cn/v1",
        timeout=timeout,
        max_retries=0,
    ) as client:
        response = client.chat.completions.create(
            model="moonshotai/Kimi-K2.7-Code",
            extra_body={"enable_thinking": False},
            messages=messages,
            response_format={"type": "json_object"},
        )
    if not response.choices or response.choices[0].finish_reason != "stop":
        raise ValueError("LLM review did not finish normally; no comments posted")
    content = response.choices[0].message.content
    if not content or not content.strip():
        raise ValueError("LLM returned no review JSON")
    return validate_comments(content, diff)


def main(llm_api_key: str) -> None:

    repo = os.environ["GITHUB_REPOSITORY"]
    pr_number = int(os.environ["PR_NUMBER"])
    token = os.environ["GITHUB_TOKEN"]
    api_url = os.environ.get("GITHUB_API_URL", "https://api.github.com")
    head_sha = os.environ["PR_HEAD_SHA"]
    github_api.assert_pull_request_head(
        repo, pr_number, token, head_sha, api_url=api_url
    )
    diff = github_api.get_pull_request_diff(repo, pr_number, token, api_url=api_url)
    diff = filter_review_diff(diff)
    if not diff.strip():
        print("No matching source changes; skipping review.")
        return
    existing_comments = github_api.get_pull_request_review_comments(
        repo, pr_number, token, api_url=api_url
    )
    feature = load_feature_context()
    try:
        comments = review_diff(diff, llm_api_key, existing_comments, feature=feature)
    except APITimeoutError:
        raise SystemExit(
            "LLM review timed out; no comments posted. "
            "Retry the CI job or increase LLM_TIMEOUT_SECONDS "
            "if the service needs more time for this diff."
        ) from None
    # Preflight the entire batch so a later invalid body cannot cause partial posts.
    for item in comments:
        if any(secret and secret in item["body"] for secret in (token, llm_api_key)):
            raise ValueError("Review comment body contains a runtime credential")
    for item in comments:
        github_api.create_pull_request_comment(
            repo,
            pr_number,
            token,
            commit_id=head_sha,
            api_url=api_url,
            path=item["path"],
            start_line=item["start_line"],
            end_line=item["end_line"],
            side=item["side"],
            body=item["body"],
        )
    print(f"Review complete: {len(comments)} comments posted.")


if __name__ == "__main__":
    main(os.environ["LLM_API_KEY"])
