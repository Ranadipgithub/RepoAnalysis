# Plan for Coding the Crawler

## Context
The crawler is responsible for fetching source code from various sources (GitHub, local filesystem, or uploaded tarball) and returning a list of file entries with their content. This is the first step in the pipeline (fetch_repo node). The crawler must respect rate limits (for GitHub), detect binary files, and enforce a size cap per file.

## Approach
We will implement three crawler modules under `backend/src/codebase_kb/crawler/`:
1. `github.py`: Uses the user's OAuth token to fetch repositories via GitHub API (Git Trees API for discovery, Contents API for content).
2. `local.py`: For admin/dev use only; reads files from a local directory (behind a feature flag).
3. `upload.py`: Handles tarball uploads (up to 100 MB), extracts to a temporary directory, and scans the contents.

All crawlers return a list of `FileEntry` objects (defined in `models.py`). Each `FileEntry` has `path` (relative to the repository root) and `content` (string, UTF-8 decoded). Binary files are skipped (NUL byte in first 8KB). Each file's content is checked against `max_file_size` (default 100 KB).

The crawlers are used by the `fetch_repo_node` in the LangGraph pipeline, which calls the appropriate crawler based on the input (repo_url, local_dir, or upload).

## Implementation Details

### 1. `models.py`
Define the `FileEntry` dataclass:
```python
from dataclasses import dataclass

@dataclass
class FileEntry:
    path: str
    content: str
```

### 2. `github.py`
- Uses `github_token` (decrypted OAuth token) from the state.
- Steps:
  a. Parse the `repo_url` to get owner and repo name.
  b. Use Git Trees API (with `recursive=1`) to get all file paths in the default branch (or specified branch).
  c. For each file, use Contents API to fetch the content (handling pagination if needed, but Trees API with recursive gives all files in one call? Note: Git Trees API returns SHA and path; we then need to fetch each file's content via Contents API or use the blob SHA? Actually, the Trees API with recursive returns the SHA for each file as a blob. We can then use the Git Blob API to get the content, but it's base64 encoded. Alternatively, we can use the Contents API for each file, but that would be many requests. Better: use the Trees API to get the list, then use the Contents API to get the content for each file? However, the Contents API can also get the contents of a directory? We can use the Contents API to get the contents of the root directory and then recursively get the contents of subdirectories. But that would be many requests.

  Alternatively, we can use the Git Trees API to get the tree and then for each blob, use the Git Blob API to get the content (which is base64). This is two requests per file? Actually, the Trees API gives us the blob SHA, then we can make a request to `git/blobs/{sha}` to get the content. This is still many requests.

  However, note the requirement: respect `X-RateLimit-Remaining`. We must be cautious.

  Another approach: use the Contents API to get the contents of the repository by path, but we can only get one directory at a time. We can do a breadth-first traversal.

  Given the constraints, we will implement:
  - Get the default branch (or use the one specified in the repo_url? The repo_url might be just the GitHub URL; we can extract the owner/repo and then use the default branch from the repository API, or allow specifying a branch? For simplicity, we use the default branch.

  - Use the Git Trees API to get the tree recursively (one request). Then for each file in the tree, we fetch the content via the Contents API (one request per file) OR we can use the Git Blob API (one request per file). Both are similar in terms of requests.

  However, note that the Contents API can also return the content of a file if we give the path. So we can do:

  For each file in the tree (from the Trees API), we make a request to `GET /repos/{owner}/{repo}/contents/{path}?ref={branch}`. This returns the content (base64) and metadata.

  We must handle pagination for the Trees API? The Trees API with `recursive=1` returns the entire tree in one response (if the repository is not too large). For very large repositories, we might need to paginate, but we assume the repository size is within limits (we have a max repo size limit?).

  Alternatively, we can use the Contents API to get the contents of the root directory and then recursively get the contents of each subdirectory. This would be one request per directory. We'll choose this method to avoid hitting rate limits too quickly? Actually, the number of requests is proportional to the number of directories and files.

  We'll implement a helper that uses the Contents API to traverse the repository.

  Steps for github.py:
  1. Extract owner and repo from the repo_url.
  2. Determine the branch (default branch from the repository API, or allow override? We'll use the default branch for simplicity).
  3. Use a queue to traverse directories starting from the root.
  4. For each directory, call Contents API to get its contents.
  5. For each item:
        - If it's a file, fetch its content (the Contents API response already includes the content for files? Actually, the Contents API for a directory returns a list of items, each of which has a `type` (file or dir) and for files, it includes `content` (base64) and `encoding`. However, note that the API only returns the content for files if the request is for a specific file? Actually, when you request a directory, the response does NOT include the content of the files. You have to make a separate request for each file to get its content.

  So we are back to one request per file.

  We'll implement:
      - Use the Contents API to get the root directory (one request).
      - For each item in the root:
            - If it's a directory, add it to a queue.
            - If it's a file, make a request to get its content (one request per file).
      - Then process each directory in the queue similarly.

  This results in 1 request for the root directory, plus 1 request per subdirectory (to get its contents), plus 1 request per file (to get its content). We can optimize by noting that when we request a directory's contents, we get the metadata for the files (size, etc.) but not the content. So we still need a separate request for the content.

  Alternatively, we can use the Git Trees API to get the list of all files (one request) and then for each file, use the Contents API to get the content (one request per file). This is 1 + (number of files) requests.

  We'll choose the Git Trees API for getting the file list (one request) and then for each file, use the Contents API to get the content.

  Steps:
      a. Get the default branch (via GET /repos/{owner}/{repo}).
      b. Get the Git Trees API with recursive=1 for the default branch: GET /repos/{owner}/{repo}/git/trees/{branch_sha}?recursive=1
         Note: we need the branch's commit SHA. We can get it from the branch API: GET /repos/{owner}/{repo}/branches/{branch}.
      c. For each item in the tree that is a blob (file), make a request to GET /repos/{owner}/{repo}/contents/{path}?ref={branch} to get the content (base64).
      d. Decode the content, check for binary (NUL byte in first 8KB), and check size.

  We must handle rate limits: check the `X-RateLimit-Remaining` header and if we are about to run out, we can pause and reset? The design says: on 403 with rate-limit hit, mark run as paused and resumes after the reset.

  We'll implement a helper function that makes a GitHub API call and handles rate limiting by checking the headers and waiting if necessary.

  However, note that the worker is expected to pause the entire run and resume later. We'll design the crawler to return control to the caller when a rate limit is hit, and the caller (the worker) can mark the run as paused and then retry later.

  We'll throw an exception when a rate limit is hit (status 429 or 403 with rate limit exceeded) and let the caller handle it.

  We'll also respect the `X-RateLimit-Remaining` and `X-RateLimit-Reset` to wait if we are close to the limit? But the requirement is to mark as paused on 403.

  We'll keep it simple: if we get a 403 and the response indicates rate limit exceeded, we raise an exception.

  We'll also handle other errors.

  We'll set a timeout for requests.

  We'll use the `requests` library? But note the backend is async (FastAPI). We should use an async HTTP client. However, the worker is running in an async context (Arq). We can use `httpx` async client.

  But note: the plan does not specify the HTTP client. We'll assume we can use `httpx` with async.

  However, the worker is a synchronous function? Actually, Arq jobs are async functions. We can use async HTTP.

  We'll write the crawler as an async function.

  We'll define an async function `fetch_github_repo(repo_url: str, github_token: str, branch: str = None) -> List[FileEntry]`.

  We'll extract owner and repo from the repo_url (supporting both https://github.com/owner/repo and git@github.com:owner/repo.git).

  We'll then:
      1. If branch is not provided, get the default branch.
      2. Get the commit SHA for the branch.
      3. Get the tree recursively.
      4. For each blob in the tree, fetch the content via Contents API.
      5. Convert to FileEntry.

  We'll also skip files that are too large (max_file_size) or binary.

### 3. `local.py`
- For admin/dev only, behind a feature flag (we'll check an environment variable or a setting).
- Walks the local directory (given by `local_dir` in the state) and reads each file.
- Skips binary files (NUL byte in first 8KB) and files larger than `max_file_size`.
- Returns List[FileEntry].

### 4. `upload.py`
- Handles an uploaded tarball (the upload endpoint saves the tarball to a temporary location).
- Extracts the tarball to a temporary directory.
- Then scans the extracted directory (same as local.py) to get the files.
- Cleans up the temporary directory after.

## Integration
The `fetch_repo_node` in the graph will:
   - Determine the source: if `local_dir` is set, use local crawler; else if `repo_url` is a GitHub URL, use GitHub crawler; else if there's an uploaded tarball (how do we know? We'll have an `upload_path` in the state? Actually, the upload crawler is called by the upload endpoint, which then enqueues the run with the local directory of the extracted tarball? We need to see the flow.

   From the directory listing, we have an upload endpoint in the API. The upload endpoint (in `api/v1/projects.py` or `api/v1/runs.py`?) probably saves the uploaded tarball and then creates a project or run with a flag indicating it's an upload and the path to the extracted tarball.

   We'll assume that the state for a run from an upload will have `local_dir` set to the extracted tarball directory (and maybe a flag to indicate it's from upload). Then the crawler can be the same as local.

   Alternatively, we can have the upload crawler return the list of FileEntry directly, and the `fetch_repo_node` will call the appropriate crawler.

   We'll design the `fetch_repo_node` to:
        if state.get("local_dir"):
            return crawler.local.fetch(state["local_dir"], ...)
        elif state.get("repo_url"):
            if is_github_url(state["repo_url"]):
                return crawler.github.fetch(state["repo_url"], state["github_token"], ...)
            else:
                # maybe support other git URLs? For now, only GitHub.
                raise ValueError("Unsupported repo URL")
        else:
            # maybe from upload? We'll have an upload_path in state?
            # We'll leave this for now and assume local_dir covers uploads after extraction.

   We'll need to define the interface for each crawler: a function that takes the necessary parameters and returns List[FileEntry].

## Verification
We will write unit tests for each crawler:
   - For github.py: mock the GitHub API responses and verify that we return the correct FileEntry list.
   - For local.py: create a temporary directory with some files (including binary and large files) and verify we skip them appropriately.
   - For upload.py: create a tarball, extract it, and verify we get the same as local.

We will also test that the crawlers respect the size cap and binary detection.

We will test the rate limit handling by mocking a 403 response and verifying that an exception is raised.

## Conclusion
This plan outlines the implementation of the crawler module for the automated codebase knowledge builder. The crawler is a critical component that fetches code from various sources while respecting constraints and preparing the data for the subsequent pipeline steps.