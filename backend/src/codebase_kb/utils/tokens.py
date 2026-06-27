import tiktoken

def estimate_token(text: str) -> int:
    """Estimates the number of tokens in the given text."""
    enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text, disallowed_special=()))

def estimate_tokens(text: str) -> int:
    """Estimates the number of tokens in the given text."""
    return estimate_token(text)

def truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Truncates the text to a maximum number of tokens."""
    enc = tiktoken.get_encoding("cl100k_base")
    encoded = enc.encode(text, disallowed_special=())
    if len(encoded) <= max_tokens:
        return text
    return enc.decode(encoded[:max_tokens])
