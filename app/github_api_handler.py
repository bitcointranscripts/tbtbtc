import os
import base64
import requests
from urllib.parse import quote
import random
import time

from app.config import settings
from app.transcript import Transcript

class GitHubAPIHandler:
    def __init__(self, token=None, target_repo_owner=None, target_repo_name=None):
        self.token = token or settings.GITHUB_TOKEN
        self.target_repo_owner = target_repo_owner or settings.GITHUB_REPO_OWNER
        self.target_repo_name = target_repo_name or settings.GITHUB_REPO_NAME
        self.headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json"
        }
        self.user = self.get_authenticated_user()
        self.fork_url = f"https://api.github.com/repos/{self.user}/{self.target_repo_name}"
        self.origin_url = f"https://api.github.com/repos/{self.target_repo_owner}/{self.target_repo_name}"
        self.check_token_permissions()
        self.ensure_fork_exists()

    def get_authenticated_user(self):
        response = requests.get("https://api.github.com/user", headers=self.headers)
        response.raise_for_status()
        return response.json()['login']

    def check_token_permissions(self):
        try:
            # Check user repository permissions
            response = requests.get(self.fork_url, headers=self.headers)
            if response.status_code == 404:
                # Repository doesn't exist, so we'll need fork permissions
                response = requests.get("https://api.github.com/user/repos", headers=self.headers, params={"per_page": 1})
                response.raise_for_status()  # This will raise an exception if we can't list repos (don't have repo or public_repo scope)
            else:
                response.raise_for_status()  # This will raise an exception if we can't access the repo

            # Check permissions on target repository
            response = requests.get(self.origin_url, headers=self.headers)
            response.raise_for_status()

        except requests.exceptions.RequestException as e:
            raise PermissionError(f"The provided token does not have sufficient permissions: {str(e)}")

    def ensure_fork_exists(self):
        # Check if fork exists
        response = requests.get(self.fork_url, headers=self.headers)
        if response.status_code == 404:
            # Fork doesn't exist, create it
            response = requests.post(f"{self.origin_url}/forks", headers=self.headers)
            response.raise_for_status()
            print(f"Created fork: {response.json()['html_url']}")
            # Wait for fork to be ready
            time.sleep(5)
        elif response.status_code != 200:
            response.raise_for_status()

    def get_default_branch(self):
        response = requests.get(self.origin_url, headers=self.headers)
        response.raise_for_status()
        return response.json()["default_branch"]

    def get_branch_sha(self, branch):
        response = requests.get(f"{self.origin_url}/git/ref/heads/{branch}", headers=self.headers)
        response.raise_for_status()
        return response.json()["object"]["sha"]

    def create_branch(self, branch_name, sha):
        # Create the branch in the fork
        response = requests.post(
            f"{self.fork_url}/git/refs",
            headers=self.headers,
            json={
                "ref": f"refs/heads/{branch_name}",
                "sha": sha
            }
        )
        response.raise_for_status()
        return response.json()

    def delete_branch(self, branch_name):
        response = requests.delete(
            f"{self.fork_url}/git/refs/heads/{branch_name}",
            headers=self.headers
        )
        response.raise_for_status()

    def create_or_update_file(self, file_path, content, commit_message, branch):
        response = requests.put(
            f"{self.fork_url}/contents/{quote(file_path)}",
            headers=self.headers,
            json={
                "message": commit_message,
                "content": base64.b64encode(content.encode()).decode(),
                "branch": branch
            }
        )
        response.raise_for_status()
        return response.json()

    def create_pull_request(self, title, head, base, body):
        response = requests.post(
            f"{self.origin_url}/pulls",
            headers=self.headers,
            json={
                "title": title,
                "head": f"{self.user}:{head}",
                "base": base,
                "body": body
            }
        )
        response.raise_for_status()
        return response.json()

    def push_transcripts(self, transcripts: list[Transcript], transcript_by: str):
        try:
            # Get the default branch of the origin repo
            default_branch = self.get_default_branch()

            # Get the SHA of the latest commit on the default branch of the origin repo
            branch_sha = self.get_branch_sha(default_branch)

            # Create a new branch in the user's fork, but based on the origin's latest commit
            branch_name = f"{transcript_by}-{''.join(random.choices('0123456789', k=6))}"
            self.create_branch(branch_name, branch_sha)

            # For each transcript with markdown, create a new commit in the new branch
            for transcript in transcripts:
                if transcript.outputs and transcript.outputs['markdown']:

                    # Read the content of the markdown file
                    with open(transcript.outputs['markdown'], 'r') as file:
                        content = file.read()

                    # Create or update the file in the repository
                    self.create_or_update_file(
                        transcript.output_path_with_title,
                        content,
                        f'Add "{transcript.title}" to {transcript.source.loc}',
                        branch_name
                    )

            # Create a pull request
            pr = self.create_pull_request(
                f"Add transcripts by {transcript_by}",
                branch_name,
                default_branch,
                "This PR adds new transcripts generated by tstbtc."
            )

            return pr['html_url']

        except requests.exceptions.RequestException as e:
            print(f"An error occurred while interacting with the GitHub API: {e}")
            return None
