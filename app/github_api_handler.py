import os
import base64
import requests
from urllib.parse import quote
import random
import time

from app import logging
from app.config import settings
from app.transcript import Transcript

logger = logging.get_logger()

class GitHubAPIHandler:
    def __init__(self, token=None):
        self.token = token or settings.GITHUB_TOKEN
        self.headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json"
        }
        self.user = self.get_authenticated_user()
        self.repos = {
            'transcripts': {
                'owner': settings.GITHUB_REPO_OWNER,
                'name': settings.GITHUB_REPO_NAME,
            },
            'metadata': {
                'owner': settings.GITHUB_REPO_OWNER,
                'name': settings.GITHUB_METADATA_REPO_NAME,
            }
        }
        self.fork_urls = {}
        self.origin_urls = {}
        for repo_type in self.repos:
            self.fork_urls[repo_type] = f"https://api.github.com/repos/{self.user}/{self.repos[repo_type]['name']}"
            self.origin_urls[repo_type] = f"https://api.github.com/repos/{self.repos[repo_type]['owner']}/{self.repos[repo_type]['name']}"
        
        for repo_type in self.repos:
            self.ensure_fork_exists(repo_type)

    def get_authenticated_user(self):
        response = requests.get("https://api.github.com/user", headers=self.headers)
        response.raise_for_status()
        return response.json()['login']

    def get_repo_url(self, repo_type, is_fork=False):
        repo = self.repos[repo_type]
        owner = self.user if is_fork else repo['owner']
        return f"https://api.github.com/repos/{owner}/{repo['name']}"

    def ensure_fork_exists(self, repo_type):
        # Check if fork exists
        response = requests.get(self.fork_urls[repo_type], headers=self.headers)
        if response.status_code == 404:
            # Fork doesn't exist, create it
            response = requests.post(f"{self.origin_urls[repo_type]}/forks", headers=self.headers)
            response.raise_for_status()
            logger.info(f"Created fork for {repo_type}: {response.json()['html_url']}")
            # Wait for fork to be ready
            time.sleep(5)
        elif response.status_code != 200:
            response.raise_for_status()

    def get_default_branch(self, repo_type):
        response = requests.get(self.origin_urls[repo_type], headers=self.headers)
        response.raise_for_status()
        return response.json()["default_branch"]

    def get_branch_sha(self, repo_type, branch):
        response = requests.get(f"{self.origin_urls[repo_type]}/git/ref/heads/{branch}", headers=self.headers)
        response.raise_for_status()
        return response.json()["object"]["sha"]

    def create_branch(self, repo_type, branch_name, sha):
        response = requests.post(
            f"{self.fork_urls[repo_type]}/git/refs",
            headers=self.headers,
            json={
                "ref": f"refs/heads/{branch_name}",
                "sha": sha
            }
        )
        response.raise_for_status()
        return response.json()


    def create_or_update_file(self, repo_type, file_path, content, commit_message, branch):
        response = requests.put(
            f"{self.fork_urls[repo_type]}/contents/{quote(file_path)}",
            headers=self.headers,
            json={
                "message": commit_message,
                "content": base64.b64encode(content.encode()).decode(),
                "branch": branch
            }
        )
        response.raise_for_status()
        return response.json()


    def create_pull_request(self, repo_type, title, head, base, body):
        response = requests.post(
            f"{self.origin_urls[repo_type]}/pulls",
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

    def push_transcripts(self, transcripts: list[Transcript]) -> str | None:
        try:
            # Create a new branch in the user's fork, but based on the origin's latest commit
            default_branch = self.get_default_branch('transcripts')
            branch_sha = self.get_branch_sha('transcripts', default_branch)
            branch_name = f"transcripts-{''.join(random.choices('0123456789', k=6))}"
            self.create_branch('transcripts', branch_name, branch_sha)

            for transcript in transcripts:
                if transcript.outputs and transcript.outputs['markdown']:
                    with open(transcript.outputs['markdown'], 'r') as file:
                        content = file.read()
                    self.create_or_update_file(
                        'transcripts',
                        transcript.output_path_with_title,
                        content,
                        f'ai(transcript): {transcript.title} ({transcript.source.loc})',
                        branch_name
                    )

            pr = self.create_pull_request(
                'transcripts',
                f"ai(transcript): Add {len(transcripts)} transcripts",
                branch_name,
                default_branch,
                f"This PR adds {len(transcripts)} new transcripts generated by [tstbtc](https://github.com/bitcointranscripts/tstbtc)."
            )

            return pr['html_url']
        except requests.exceptions.RequestException as e:
            logger.error(f"An error occurred while interacting with the GitHub API: {e}")
            return None

    def push_metadata(self, transcripts: list[Transcript], transcripts_pr_url: str):
        try:
            default_branch = self.get_default_branch('metadata')
            branch_sha = self.get_branch_sha('metadata', default_branch)
            branch_name = f"metadata-{''.join(random.choices('0123456789', k=6))}"
            self.create_branch('metadata', branch_name, branch_sha)

            for transcript in transcripts:
                metadata_files = [
                    transcript.metadata_file,
                    transcript.outputs["transcription_service_output_file"],
                    transcript.outputs.get("dpe_file")
                ]
                
                # Group all metadata files for this transcript into a single commit
                commit_files = []
                for file_path in metadata_files:
                    if file_path:
                        with open(file_path, 'r') as file:
                            content = file.read()
                        commit_files.append({
                            'path': os.path.join(transcript.output_path_with_title, os.path.basename(file_path)),
                            'content': content
                        })
                
                if commit_files:
                    self.create_commit_with_multiple_files(
                        'metadata',
                        commit_files,
                        f"ai(transcript): {transcript.title} ({transcript.source.loc})",
                        branch_name
                    )

            pr_body = (
                f"This PR adds metadata for {len(transcripts)} new transcripts generated by tstbtc.\n\n"
                f"Related transcripts PR: {transcripts_pr_url}"
            )

            pr = self.create_pull_request(
                'metadata',
                f"ai(transcript): Add metadata for {len(transcripts)} transcripts",
                branch_name,
                default_branch,
                pr_body
            )

            return pr['html_url']
        except requests.exceptions.RequestException as e:
            logger.error(f"An error occurred while interacting with the GitHub API for metadata: {e}")
            return None

    def create_commit_with_multiple_files(self, repo_type, files, commit_message, branch):
        # Get the latest commit SHA for the branch
        branch_ref = requests.get(f"{self.fork_urls[repo_type]}/git/ref/heads/{branch}", headers=self.headers)
        branch_ref.raise_for_status()
        latest_commit_sha = branch_ref.json()['object']['sha']

        # Get the tree SHA of the latest commit
        latest_commit = requests.get(f"{self.fork_urls[repo_type]}/git/commits/{latest_commit_sha}", headers=self.headers)
        latest_commit.raise_for_status()
        base_tree_sha = latest_commit.json()['tree']['sha']

        # Create a new tree with the new files
        new_tree = []
        for file in files:
            new_tree.append({
                'path': file['path'],
                'mode': '100644',
                'type': 'blob',
                'content': file['content']
            })

        tree_response = requests.post(
            f"{self.fork_urls[repo_type]}/git/trees",
            headers=self.headers,
            json={
                'base_tree': base_tree_sha,
                'tree': new_tree
            }
        )
        tree_response.raise_for_status()
        new_tree_sha = tree_response.json()['sha']

        # Create a new commit
        commit_response = requests.post(
            f"{self.fork_urls[repo_type]}/git/commits",
            headers=self.headers,
            json={
                'message': commit_message,
                'tree': new_tree_sha,
                'parents': [latest_commit_sha]
            }
        )
        commit_response.raise_for_status()
        new_commit_sha = commit_response.json()['sha']

        # Update the branch reference
        update_ref_response = requests.patch(
            f"{self.fork_urls[repo_type]}/git/refs/heads/{branch}",
            headers=self.headers,
            json={'sha': new_commit_sha}
        )
        update_ref_response.raise_for_status()

        return new_commit_sha
