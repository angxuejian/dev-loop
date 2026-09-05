import ast
import json
import math
import os
import re
import unicodedata
from importlib import import_module
from pathlib import Path
from typing import Literal, TypedDict, cast

from openai import APITimeoutError, OpenAI

github_api = import_module("common.github-api")
SKILL_PATH = Path(__file__).resolve().parents[2] / ".agents/skills/code-review/SKILL.md"
REVIEW_FILE_EXTENSIONS = {".py", ".js", ".ts"}
MAX_COMMENT_BODY_BYTES = 10_000


class ReviewComment(TypedDict):
    path: str
    start_line: int
    end_line: int
    side: Literal["LEFT", "RIGHT"]
    body: str


def parse_review_json(content: str) -> object:
    """Parse a model response that should contain exactly one JSON object."""
    candidate = content.strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        if (
            lines
            and lines[0].strip().lower() in {"```", "```json"}
            and lines[-1].strip() == "```"
        ):
            candidate = "\n".join(lines[1:-1]).strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as first_error:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(candidate[start : end + 1])
            except json.JSONDecodeError:
                pass
        raise ValueError(
            "LLM response was not valid JSON; expected one object containing comments"
        ) from first_error


def validate_comment_body(body: str, secrets: tuple[str, ...] = ()) -> None:
    """Allow ordinary Markdown, but reject unsafe text without echoing it."""
    if any(
        unicodedata.category(char) in {"Cc", "Cs"} and char not in "\t\n\r"
        for char in body
    ):
        raise ValueError("Review comment body contains invalid characters")
    if len(body.encode("utf-8")) > MAX_COMMENT_BODY_BYTES:
        raise ValueError("Review comment body exceeds the byte limit")
    if any(secret and secret in body for secret in secrets):
        raise ValueError("Review comment body contains a runtime credential")


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
    result = parse_review_json(content)
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
    """Keep complete textual file diffs for the configured extensions."""
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
                path = line[4:]
                if path.startswith('"'):
                    path = ast.literal_eval("b" + path).decode("utf-8")
                if line.startswith("--- "):
                    old_path = path
                else:
                    new_path = path
        path = old_path if new_path == "/dev/null" else new_path
        if Path(path).suffix in REVIEW_FILE_EXTENSIONS:
            selected.append(file_diff)
    return "".join(selected)


def review_diff(diff: str, llm_api_key: str) -> list[ReviewComment]:
    """Review the already-filtered source diff in one request."""

    if not diff.strip():
        return []
    timeout = float(os.environ.get("LLM_TIMEOUT_SECONDS", "600"))
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("LLM_TIMEOUT_SECONDS must be a finite positive number")
    skill = SKILL_PATH.read_text(encoding="utf-8")
    print(f"Loaded skill from {SKILL_PATH}.", flush=True)
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
            model="deepseek-ai/DeepSeek-V4-Pro",
            extra_body={"enable_thinking": False},
            messages=[
                {"role": "system", "content": skill},
                {
                    "role": "user",
                    "content": "请按 skill 审查以下 diff。最终响应必须严格是一个 JSON 对象，"
                    "只能包含顶层 comments 数组；禁止 Markdown 代码围栏、解释文字、前后缀或其他字段。"
                    "此输入仅包含 PR 中符合扩展名过滤条件的文件变更。只评论有充分证据的问题，不推测其他文件的内容。"
                    "你没有源码读取或执行工具。"
                    "特别注意：diff 中以 - 开头的 LEFT 行属于旧代码；只有删除动作本身引入了可验证回归时才评论 LEFT 行。"
                    "如果问题只存在于被删除的旧代码中，且删除已经解决问题，不要输出该评论。\n\n"
                    + diff,
                },
            ],
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
    print(f"Fetched PR #{pr_number} diff ({len(diff)} characters).", flush=True)
    if not diff.strip():
        print("Empty diff; skipping review and comments.")
        return
    diff = filter_review_diff(diff)
    print(f"Filtered source diff: {len(diff)} characters.", flush=True)
    if not diff.strip():
        print(
            f"No text changes matching {sorted(REVIEW_FILE_EXTENSIONS)}; "
            "skipping review and comments."
        )
        return
    try:
        comments = review_diff(diff, llm_api_key)
    except APITimeoutError:
        raise SystemExit(
            "LLM review timed out; no comments posted. "
            "Retry the CI job or increase LLM_TIMEOUT_SECONDS "
            "if the service needs more time for this diff."
        ) from None
    if not comments:
        print("No review findings; no comments posted.")
        return
    # Preflight the entire batch so a later invalid body cannot cause partial posts.
    for item in comments:
        validate_comment_body(item["body"], (token, llm_api_key))
    for item in comments:
        comment = github_api.create_pull_request_comment(
            repo, pr_number, token, commit_id=head_sha, api_url=api_url, **item
        )
        print(f"Created review comment: {comment['html_url']}")


if __name__ == "__main__":
    main(os.environ["LLM_API_KEY"])
