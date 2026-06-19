from dataclasses import dataclass

@dataclass
class FileEntry:
    path: str
    content: str