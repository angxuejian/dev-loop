"""GitHub REST and gh CLI helpers used by automation scripts."""

import json
import subprocess
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


def _get_pull_request(
    repo: str,
    pr_number: int,
    token: str,
    *,
    accept: str,
    api_url: str = "https://api.github.com",
    timeout: float = 30,
) -> str:
    """Fetch a PR using the requested response media type."""
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
            "Accept": accept,
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
            f"Failed to fetch {repo} PR #{pr_number}: HTTP {exc.code}"
        ) from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(
            f"Failed to fetch {repo} PR #{pr_number}: network error or timeout"
        ) from exc


def get_pull_request_diff(
    repo: str,
    pr_number: int,
    token: str,
    *,
    api_url: str = "https://api.github.com",
    timeout: float = 30,
) -> str:
    """Return the PR unified diff using the GitHub API root URL."""
    return _get_pull_request(
        repo,
        pr_number,
        token,
        accept="application/vnd.github.diff",
        api_url=api_url,
        timeout=timeout,
    )


def assert_pull_request_head(
    repo: str,
    pr_number: int,
    token: str,
    expected_sha: str,
    *,
    api_url: str = "https://api.github.com",
    timeout: float = 30,
) -> None:
    """Stop a stale CI run before reviewing or posting against a changed PR."""
    pull_request = json.loads(
        _get_pull_request(
            repo,
            pr_number,
            token,
            accept="application/vnd.github+json",
            api_url=api_url,
            timeout=timeout,
        )
    )
    if pull_request["head"]["sha"] != expected_sha:
        raise RuntimeError("PR head changed; rerun review for the current commit")


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
        try:
            # Bound untrusted response data and redact credentials before escaping it.
            detail = exc.read(4096).decode("utf-8", errors="replace")
            detail = detail.replace(token, "[REDACTED]")
            detail = detail.replace(json.dumps(token)[1:-1], "[REDACTED]")
        except OSError:
            detail = "Response body unavailable"
        raise RuntimeError(
            f"Failed to comment on {repo} PR #{pr_number}: HTTP {exc.code}"
            + (f"; response: {detail!a}" if detail else "")
        ) from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(
            f"Failed to comment on {repo} PR #{pr_number}: network error or timeout"
        ) from exc


def get_pull_request_review_comments(
    repo: str,
    pr_number: int,
    token: str,
    *,
    api_url: str = "https://api.github.com",
    timeout: float = 30,
) -> list[dict[str, object]]:
    """Return all inline review comments on a pull request."""
    parts = repo.split("/")
    if len(parts) != 2 or not all(parts):
        raise ValueError("repo must have the form owner/repository")
    if pr_number <= 0:
        raise ValueError("pr_number must be positive")
    if not token:
        raise ValueError("A GitHub token is required")
    repository = "/".join(quote(part, safe="") for part in parts)
    comments: list[dict[str, object]] = []
    page = 1
    while True:
        request = Request(
            f"{api_url.rstrip('/')}/repos/{repository}/pulls/{pr_number}/comments"
            f"?per_page=100&page={page}",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "dev-loop-code-review",
            },
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                page_comments = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise RuntimeError(
                f"Failed to fetch comments for {repo} PR #{pr_number}: HTTP {exc.code}"
            ) from exc
        except (URLError, TimeoutError) as exc:
            raise RuntimeError(
                f"Failed to fetch comments for {repo} PR #{pr_number}: network error or timeout"
            ) from exc
        if not isinstance(page_comments, list):
            raise TypeError("GitHub returned an invalid pull request comment list")
        comments.extend(page_comments)
        if len(page_comments) < 100:
            return comments
        page += 1


def _gh_request_json(
    hostname: str | None,
    timeout: float,
    endpoint: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Request JSON through gh using its existing authentication."""
    command = ["gh", "api", endpoint, "--method", "GET" if payload is None else "POST"]
    if hostname:
        command.extend(["--hostname", hostname])
    if payload is not None:
        command.extend(["--input", "-"])
    try:
        response = subprocess.run(
            command,
            input=json.dumps(payload) if payload is not None else None,
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "GitHub CLI (gh) is required; install it and run gh auth login"
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"GitHub CLI request failed: {exc.stderr.strip()}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("GitHub CLI request timed out") from exc
    result = json.loads(response.stdout)
    if result.get("errors"):
        raise RuntimeError(f"GitHub GraphQL request failed: {result['errors']}")
    return result


def _gh_request_value(endpoint: str, field: str, *, timeout: float = 30) -> str:
    """Read one value from gh's local repository or pull request context."""
    try:
        response = subprocess.run(
            ["gh", *endpoint.split(), "--json", field, "--jq", f".{field}"],
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "GitHub CLI (gh) is required; install it and run gh auth login"
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"GitHub CLI request failed: {exc.stderr.strip()}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("GitHub CLI request timed out") from exc
    value = response.stdout.strip()
    if not value:
        raise RuntimeError(f"GitHub CLI returned no value for {field}")
    return value


def get_current_repository(*, timeout: float = 30) -> str:
    """Return owner/repository for the current checkout."""
    return _gh_request_value("repo view", "nameWithOwner", timeout=timeout)


def create_pull_request(
    repo: str,
    *,
    title: str,
    body: str,
    head: str,
    base: str,
    draft: bool = False,
    hostname: str | None = None,
    timeout: float = 30,
) -> str:
    """Create a PR from an already-pushed head branch and return its URL."""
    parts = repo.split("/")
    if len(parts) != 2 or not all(parts):
        raise ValueError("repo must have the form owner/repository")
    if not title.strip() or not head.strip() or not base.strip():
        raise ValueError("title, head and base must not be empty")
    repository = f"{hostname}/{repo}" if hostname else repo
    command = [
        "gh",
        "pr",
        "create",
        "--repo",
        repository,
        "--title",
        title,
        "--body-file",
        "-",
        "--head",
        head,
        "--base",
        base,
    ]
    if draft:
        command.append("--draft")
    try:
        response = subprocess.run(
            command,
            input=body,
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "GitHub CLI (gh) is required; install it and run gh auth login"
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"Failed to create pull request: {exc.stderr.strip()}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            "PR creation timed out; check GitHub before retrying"
        ) from exc
    url = response.stdout.strip()
    if not url:
        raise RuntimeError("GitHub CLI returned no pull request URL")
    return url


def get_current_pull_request_number(*, timeout: float = 30) -> int:
    """Return the PR number associated with the current branch."""
    value = _gh_request_value("pr view", "number", timeout=timeout)
    try:
        number = int(value)
    except ValueError as exc:
        raise RuntimeError(
            f"Invalid pull request number returned by gh: {value}"
        ) from exc
    if number <= 0:
        raise RuntimeError(f"Invalid pull request number returned by gh: {number}")
    return number


def _has_pending_workflows(
    hostname: str | None,
    timeout: float,
    repository_url: str,
    head_sha: str,
    own_run_id: str,
) -> bool:
    page = 1
    while True:
        result = _gh_request_json(
            hostname,
            timeout,
            f"{repository_url}/actions/runs?head_sha={quote(head_sha, safe='')}"
            f"&per_page=100&page={page}",
        )
        runs = result["workflow_runs"]
        if any(
            run["status"] != "completed" and str(run["id"]) != own_run_id
            for run in runs
        ):
            return True
        if len(runs) < 100:
            return False
        page += 1


def _get_unresolved_comments(
    hostname: str | None, timeout: float, owner: str, name: str, pr_number: int
) -> list[dict[str, Any]]:
    query = """
        query($owner: String!, $name: String!, $number: Int!, $cursor: String) {
          repository(owner: $owner, name: $name) {
            pullRequest(number: $number) {
              reviewThreads(first: 100, after: $cursor) {
                nodes { id isResolved }
                pageInfo { hasNextPage endCursor }
              }
            }
          }
        }
    """
    comments_query = """
        query($id: ID!, $cursor: String) {
          node(id: $id) {
            ... on PullRequestReviewThread {
              comments(first: 100, after: $cursor) {
                nodes { databaseId body path line url author { login } }
                pageInfo { hasNextPage endCursor }
              }
            }
          }
        }
    """
    comments: list[dict[str, Any]] = []
    cursor = None
    while True:
        result = _gh_request_json(
            hostname,
            timeout,
            "graphql",
            {
                "query": query,
                "variables": {
                    "owner": owner,
                    "name": name,
                    "number": pr_number,
                    "cursor": cursor,
                },
            },
        )
        repository = result["data"]["repository"]
        if repository is None or repository["pullRequest"] is None:
            raise RuntimeError("Repository or pull request not found")
        threads = repository["pullRequest"]["reviewThreads"]
        for thread in threads["nodes"]:
            if thread["isResolved"]:
                continue
            comment_cursor = None
            while True:
                result = _gh_request_json(
                    hostname,
                    timeout,
                    "graphql",
                    {
                        "query": comments_query,
                        "variables": {"id": thread["id"], "cursor": comment_cursor},
                    },
                )
                connection = result["data"]["node"]["comments"]
                comments.extend(connection["nodes"])
                if not connection["pageInfo"]["hasNextPage"]:
                    break
                comment_cursor = connection["pageInfo"]["endCursor"]
        if not threads["pageInfo"]["hasNextPage"]:
            return comments
        cursor = threads["pageInfo"]["endCursor"]


def _find_review_thread_id(
    hostname: str | None,
    timeout: float,
    owner: str,
    name: str,
    pr_number: int,
    comment_database_id: int,
) -> str:
    query = """
        query($owner: String!, $name: String!, $number: Int!, $cursor: String) {
          repository(owner: $owner, name: $name) {
            pullRequest(number: $number) {
              reviewThreads(first: 100, after: $cursor) {
                nodes {
                  id
                  comments(first: 100) { nodes { databaseId } }
                }
                pageInfo { hasNextPage endCursor }
              }
            }
          }
        }
    """
    cursor = None
    while True:
        result = _gh_request_json(
            hostname,
            timeout,
            "graphql",
            {
                "query": query,
                "variables": {
                    "owner": owner,
                    "name": name,
                    "number": pr_number,
                    "cursor": cursor,
                },
            },
        )
        repository = result["data"]["repository"]
        if repository is None or repository["pullRequest"] is None:
            raise RuntimeError("Repository or pull request not found")
        threads = repository["pullRequest"]["reviewThreads"]
        for thread in threads["nodes"]:
            if any(
                comment["databaseId"] == comment_database_id
                for comment in thread["comments"]["nodes"]
            ):
                return thread["id"]
        if not threads["pageInfo"]["hasNextPage"]:
            break
        cursor = threads["pageInfo"]["endCursor"]
    raise RuntimeError(f"Review comment databaseId {comment_database_id} was not found")


def _validate_pull_request(repo: str, pr_number: int) -> list[str]:
    parts = repo.split("/")
    if len(parts) != 2 or not all(parts):
        raise ValueError("repo must have the form owner/repository")
    if pr_number <= 0:
        raise ValueError("pr_number must be positive")
    return parts


def has_pending_pull_request_workflows(
    repo: str,
    pr_number: int,
    *,
    own_run_id: str = "",
    hostname: str | None = None,
    timeout: float = 30,
) -> bool:
    """Check unfinished PR workflows using gh, excluding our own run."""
    parts = _validate_pull_request(repo, pr_number)
    repository_url = "repos/" + "/".join(quote(part, safe="") for part in parts)
    pr = _gh_request_json(hostname, timeout, f"{repository_url}/pulls/{pr_number}")
    return _has_pending_workflows(
        hostname, timeout, repository_url, pr["head"]["sha"], own_run_id
    )


def get_unresolved_pull_request_comments(
    repo: str,
    pr_number: int,
    *,
    hostname: str | None = None,
    timeout: float = 30,
) -> list[dict[str, Any]]:
    """Return unresolved review comments for open PRs only, including replies."""
    parts = _validate_pull_request(repo, pr_number)
    repository_url = "repos/" + "/".join(quote(part, safe="") for part in parts)
    pr = _gh_request_json(hostname, timeout, f"{repository_url}/pulls/{pr_number}")
    if pr["state"] != "open":
        return []
    return _get_unresolved_comments(hostname, timeout, parts[0], parts[1], pr_number)


def resolve_pull_request_comment(
    repo: str,
    pr_number: int,
    comment_database_id: int,
    *,
    hostname: str | None = None,
    timeout: float = 30,
) -> dict[str, Any]:
    """Resolve the review thread containing a PR comment using gh."""
    parts = _validate_pull_request(repo, pr_number)
    if comment_database_id <= 0:
        raise ValueError("comment_database_id must be positive")
    thread_id = _find_review_thread_id(
        hostname,
        timeout,
        parts[0],
        parts[1],
        pr_number,
        comment_database_id,
    )
    mutation = """
        mutation($threadId: ID!) {
          resolveReviewThread(input: {threadId: $threadId}) {
            thread { id isResolved }
          }
        }
    """
    result = _gh_request_json(
        hostname,
        timeout,
        "graphql",
        {"query": mutation, "variables": {"threadId": thread_id}},
    )
    return result["data"]["resolveReviewThread"]["thread"]
