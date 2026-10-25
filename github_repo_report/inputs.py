"""Repository input validation, independent of the CLI."""
import re
from urllib.parse import urlsplit

def repository(value: str) -> str:
    if "://" in value:
        u = urlsplit(value)
        if (u.scheme != "https" or u.netloc.lower() != "github.com"
                or u.query or u.fragment):
            raise ValueError("Use https://github.com/owner/repo")
        value = u.path.strip("/")
    value = value.removesuffix(".git")
    if not re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9_.-]+", value):
        raise ValueError("Expected owner/repo or repository URL")
    return value
