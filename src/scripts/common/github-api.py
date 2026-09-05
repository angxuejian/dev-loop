"""GitHub REST API helpers used by automation scripts."""

import json
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


def get_pull_request_diff(
    repo: str,
    pr_number: int,
    token: str,
    *,
    api_url: str = "https://api.github.com",
    timeout: float = 30,
) -> str:
    """Return a PR's unified diff, raising RuntimeError if GitHub fails.

    repo is an owner/repository pair. api_url is the GitHub API root,
    such as GITHUB_API_URL in Actions, rather than the website URL.
    """
    parts = repo.split("/")
    if len(parts) != 2 or not all(parts):
        raise ValueError("repo must have the form owner/repository")
    if pr_number <= 0:
        raise ValueError("pr_number must be positive")
    if not token:
        raise ValueError("A GitHub token is required")

    repository = "/".join(quote(part, safe="") for part in parts)
    request = Request(
        f"{api_url.rstrip('/')}/repos/{repository}/pulls/{pr_number}",
        headers={
            "Accept": "application/vnd.github.diff",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "dev-loop-code-review",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        raise RuntimeError(
            f"Failed to fetch diff for {repo} PR #{pr_number}: HTTP {exc.code}"
        ) from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(
            f"Failed to fetch diff for {repo} PR #{pr_number}: network error or timeout"
        ) from exc


def create_pull_request_comment(
    repo: str,
    pr_number: int,
    token: str,
    *,
    commit_id: str,
    path: str,
    start_line: int,
    end_line: int,
    body: str,
    side: Literal["LEFT", "RIGHT"] = "RIGHT",
    api_url: str = "https://api.github.com",
    timeout: float = 30,
) -> dict[str, object]:
    """Post an inline review comment and return GitHub's comment object.

    Lines are inclusive, one-based file line numbers on the specified side
    of the PR diff. The range must belong to one diff hunk. Use the PR head
    SHA for commit_id, not the Actions merge commit SHA.
    """
    parts = repo.split("/")
    if len(parts) != 2 or not all(parts):
        raise ValueError("repo must have the form owner/repository")
    if pr_number <= 0:
        raise ValueError("pr_number must be positive")
    if not token:
        raise ValueError("A GitHub token is required")
    if not commit_id.strip() or not path.strip() or not body.strip():
        raise ValueError("commit_id, path and body must not be empty")
    if start_line <= 0 or end_line < start_line:
        raise ValueError("Lines must satisfy 1 <= start_line <= end_line")
    if side not in ("LEFT", "RIGHT"):
        raise ValueError("side must be LEFT or RIGHT")

    payload: dict[str, str | int] = {
        "body": body,
        "commit_id": commit_id,
        "path": path,
        "line": end_line,
        "side": side,
    }
    if start_line < end_line:
        payload.update(start_line=start_line, start_side=side)

    repository = "/".join(quote(part, safe="") for part in parts)
    request = Request(
        f"{api_url.rstrip('/')}/repos/{repository}/pulls/{pr_number}/comments",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "dev-loop-code-review",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(
            f"Failed to comment on {repo} PR #{pr_number}: HTTP {exc.code}"
        ) from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(
            f"Failed to comment on {repo} PR #{pr_number}: network error or timeout"
        ) from exc
