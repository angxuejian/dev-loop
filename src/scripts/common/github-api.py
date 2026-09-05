"""GitHub REST API helpers used by automation scripts."""

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
