import os
import re
from importlib import import_module

github_api = import_module("common.github-api")
repo = os.environ["GITHUB_REPOSITORY"]
pr_number = os.environ["PR_NUMBER"]
token = os.environ["GITHUB_TOKEN"]
llm_api_key = os.environ["LLM_API_KEY"]


def select_test_comment_range(diff: str) -> tuple[str, int, int] | None:
    """Select up to two new-side lines in the first suitable text hunk."""
    path = ""
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            path = ""
        elif line.startswith("+++ b/"):
            path = line[6:]
        elif path and (
            match := re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
        ):
            start = int(match[1])
            count = int(match[2]) if match[2] is not None else 1
            if start > 0 and count > 0:
                return path, start, start + min(count, 2) - 1
    return None

print(f"Fetching diff for PR #{pr_number} in repository {repo}...")
diff = github_api.get_pull_request_diff(
    repo,
    int(pr_number),
    token,
    api_url=os.environ.get("GITHUB_API_URL", "https://api.github.com"),
)
print(diff)
print(f"Fetched PR diff ({len(diff)} characters).")

test_range = select_test_comment_range(diff)
if test_range is None:
    print("Skipping test comment: no suitable new-side text lines in the diff.")
else:
    path, start_line, end_line = test_range
    comment = github_api.create_pull_request_comment(
        repo,
        int(pr_number),
        token,
        commit_id=os.environ["PR_HEAD_SHA"],
        path=path,
        start_line=start_line,
        end_line=end_line,
        body="测试评论：验证 PR 行内评论接口，所选代码范围不代表实际 review 问题。",
        api_url=os.environ.get("GITHUB_API_URL", "https://api.github.com"),
    )
    print(f"Created test comment: {comment['html_url']}")
