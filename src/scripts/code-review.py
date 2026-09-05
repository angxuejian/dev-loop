import os
from importlib import import_module

github_api = import_module("common.github-api")

repo = os.environ["GITHUB_REPOSITORY"]
pr_number = os.environ["PR_NUMBER"]
token = os.environ["GITHUB_TOKEN"]
llm_api_key = os.environ["LLM_API_KEY"]

print(f"Fetching diff for PR #{pr_number} in repository {repo}...")
diff = github_api.get_pull_request_diff(
    repo,
    int(pr_number),
    token,
    api_url=os.environ.get("GITHUB_API_URL", "https://api.github.com"),
)
print(diff)
print(f"Fetched PR diff ({len(diff)} characters).")
