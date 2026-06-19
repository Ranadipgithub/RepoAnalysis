import asyncio
import base64
from typing import List, Optional, Tuple
import httpx
from .models import FileEntry

class GitHubRateLimitExceeded(Exception):
    """Raised when GitHub API rate limit is exceeded."""
    pass

async def _github_request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    token: str,
    **kwargs
    ) -> httpx.Response:
    """Make a request to GitHub API with authentication and rate limit handling."""
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        **kwargs.pop("headers", {}),
    }
    response = await client.request(method, url, headers=headers, **kwargs)

    # Check for rate limit exceeded
    if response.status_code == 403:
        # gitHub returns 403 for rate limit exceeded with header "X-RateLimit-Remaining: 0"
        remaining = response.headers.get("X-RateLimit-Remaining")
        if remaining == "0":
            reset_time = response.headers.get("X-RateLimit-Reset")
            raise GitHubRateLimitExceeded(
                f"GitHub API rate limit exceeded. Reset at {reset_time}"
            )
    # For other errors, raise for status
    response.raise_for_status()
    return response

async def fetch_github_repo(
    repo_url: str,
    github_token: str,
    branch: Optional[str] = None,
    max_file_size: int = 100 * 1024,  # 100 KB
) -> List[FileEntry]:
    """
    Fetch a GitHub repository and return a list of FileEntry objects.

    Args:
        repo_url: GitHub repository URL (https://github.com/owner/repo or git@github.com:owner/repo.git)
        github_token: User's OAuth token (decrypted)
        branch: Branch name (if None, uses default branch)
        max_file_size: Maximum file size in bytes to include

    Returns:
        List of FileEntry objects with path and content.

    Raises:
        GitHubRateLimitExceeded: If GitHub API rate limit is exceeded.
        httpx.HTTPStatusError: For other HTTP errors.
    """
    # Parse owner and repo from URL
    owner, repo = _parse_github_url(repo_url)

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Determine branch
        if branch is None:
            branch = await _get_default_branch(client, owner, repo, github_token)

        # Get commit SHA for the branch
        commit_sha = await _get_branch_commit(client, owner, repo, branch, github_token)

        # Get recursive tree
        tree = await _get_tree_recursive(client, owner, repo, commit_sha, github_token)

        # Process each file in the tree
        entries: List[FileEntry] = []
        for item in tree:
            if item["type"] == "blob":  # file
                path = item["path"]
                # Get raw bytes of the file
                raw_bytes = await _get_file_raw_bytes(
                    client, owner, repo, path, branch, github_token
                )
                # Skip if too large
                if len(raw_bytes) > max_file_size:
                    continue
                # Check for binary (null byte in first 8KB)
                if _is_binary(raw_bytes):
                    continue
                # Decode to string
                try:
                    content = raw_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    #skip as binary
                    continue
                entries.append(FileEntry(path=path, content=content))

        return entries

def _parse_github_url(repo_url: str) -> Tuple[str, str]:
    """Extract owner and repo from GitHub URL."""
    # Remove protocol and git@
    if repo_url.startswith("https://github.com/"):
        repo_url = repo_url[len("https://github.com/"):]
    elif repo_url.startswith("git@github.com:"):
        repo_url = repo_url[len("git@github.com:"):]
    else:
        raise ValueError(f"Unsupported GitHub URL format: {repo_url}")
    if repo_url.endswith(".git"):
        repo_url = repo_url[:-4]
    parts = repo_url.split("/")
    if len(parts) < 2:
        raise ValueError(f"Could not parse owner/repo from URL: {repo_url}")
    owner = parts[0]
    repo = parts[1]
    return owner, repo

async def _get_default_branch(
    client: httpx.AsyncClient,
    owner: str,
    repo: str,
    token: str
) -> str:
    """Get the default branch for a repository."""
    url = f"https://api.github.com/repos/{owner}/{repo}"
    response = await _github_request(client, "GET", url, token)
    data = response.json()
    return data["default_branch"]

async def _get_branch_commit(
    client: httpx.AsyncClient,
    owner: str,
    repo: str,
    branch: str,
    token: str
) -> str:
    """Get the commit SHA for a branch."""
    """ SHA represents the commit uniquely through a stream of chars"""
    url = f"https://api.github.com/repos/{owner}/{repo}/branches/{branch}"
    response = await _github_request(client, "GET", url, token)
    data = response.json()
    return data["commit"]["sha"]

async def _get_tree_recursive(
    client: httpx.AsyncClient,
    owner: str,
    repo: str,
    commit_sha: str,
    token: str
) -> List[dict]:
    """Get recursive tree of the repository."""
    url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{commit_sha}"
    params = {"recursive": "1"}
    response = await _github_request(client, "GET", url, token, params=params)
    data = response.json()
    return data["tree"]

async def _get_file_raw_bytes(
    client: httpx.AsyncClient,
    owner: str,
    repo: str,
    path: str,
    branch: str,
    token: str
) -> bytes:
    """Get the raw bytes of a single file via Contents API."""
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    params = {"ref": branch}
    response = await _github_request(client, "GET", url, token, params=params)
    data = response.json()
    # Content is base64 encoded
    raw_bytes = base64.b64decode(data["content"])
    return raw_bytes

def _is_binary(content: bytes) -> bool:
    """
    Check if content is binary by looking for null byte in first 8KB.
    """
    # Check first 8192 bytes for null byte
    return b"\x00" in content[:8192]