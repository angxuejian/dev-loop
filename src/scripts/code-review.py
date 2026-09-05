import os
import requests

repo = os.environ["GITHUB_REPOSITORY"]
pr_number = os.environ["PR_NUMBER"]
token = os.environ["GITHUB_TOKEN"]
llm_api_key = os.environ["GLM_LLM_API_KEY"]

print(f"Fetching code review comments for PR #{pr_number} in repository {repo}... {llm_api_key}")