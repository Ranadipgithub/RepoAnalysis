import asyncio
import base64
from typing import List, Optional, Tuple
import httpx
from codebase_kb.crawler.configs.config import redirect_uri
from codebase_kb.crawler.models.models import FileEntry,CommitEntry
from codebase_kb.crawler.utils.tree_parser import build_tree,print_tree
import dotenv
import tqdm
import os
from dotenv import load_dotenv
import codebase_kb.crawler.github
from codebase_kb.crawler.github import exchange_code_for_token, fetch_github_repo ,fetch_commit_history,_get_tree_recursive
import requests

load_dotenv()

client_secret=os.getenv("client_secret")
client_id=os.getenv("client_id")


if __name__== "__main__":
    repository_url="https://github.com/KaiAllAlone/Q-Learning-From-Scratch"
    github_token=os.getenv("GITHUB_TOKEN")
    if(not github_token):
        github_token=asyncio.run(exchange_code_for_token(client_id))
        dotenv.set_key(".env","GITHUB_TOKEN",github_token)
    load_dotenv(override=True)
    repo_entries=asyncio.run(fetch_github_repo(repository_url,github_token,max_file_size=1024*1024))
    print("#"*50)
    print(print_tree(codebase_kb.crawler.github.project_tree))
    print("#"*50,"\n")
    for entries in repo_entries:
        print(entries.path)
        print(entries.content[:50]," ... ")
        print("\n")
    print("*"*50,"\n")
    print("COMMIT HISTORY \n")
    print("*"*50,"\n")
    commits=asyncio.run(fetch_commit_history(repo_url=repository_url,github_token=github_token))
    for commit in commits:
        print("COMMIT SHA:- \n",commit.sha,"\n")
        print("COMMIT AUTHOR:- \n",commit.author,"\n")
        print("COMMIT MESSAGE:- \n",commit.message,"\n")
        print("COMMIT DATE:- \n",commit.date,"\n")
        print(commit.sha)


    

