from dataclasses import dataclass

@dataclass
class FileEntry:
    path: str
    content: str

    
@dataclass
class CommitEntry:
    sha: str
    author: str
    date: str
    message: str