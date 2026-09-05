import ast
import json
import os
import re
from importlib import import_module
from pathlib import Path
from typing import Literal, TypedDict, cast

from openai import OpenAI

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


def review_diff(diff: str, llm_api_key: str) -> list[ReviewComment]:
    """Load the review skill as instructions and ask GLM for comment JSON."""
    if not diff.strip():
        return []
    diff_ranges(diff)
    skill = SKILL_PATH.read_text(encoding="utf-8")
    with OpenAI(
        api_key=llm_api_key,
        base_url="https://api.siliconflow.cn/v1",
        timeout=180,
        max_retries=0,
    ) as client:
        response = client.chat.completions.create(
            model="zai-org/GLM-5.3",
            messages=[
                {"role": "system", "content": skill},
                {
                    "role": "user",
                    "content": "请按 skill 审查以下 diff，只返回约定的 JSON。"
                    "你只能看到此 diff，没有源码读取或执行工具。\n\n" + diff,
                },
            ],
        )
    if not response.choices or response.choices[0].finish_reason != "stop":
        raise ValueError("LLM review did not finish normally; no comments posted")
    content = response.choices[0].message.content
    if not content or not content.strip():
        raise ValueError("LLM returned no review JSON")
    return validate_comments(content, diff)


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
    print(f"Fetched PR #{pr_number} diff ({len(diff)} characters).")
    if not diff.strip():
        print("Empty diff; skipping review and comments.")
        return
    comments = review_diff(diff, os.environ["LLM_API_KEY"])
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
