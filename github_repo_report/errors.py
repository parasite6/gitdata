"""Expected API failures and explicit user cancellation."""
import math


class Unavailable(Exception):
    pass

class APIError(Unavailable):
    def __init__(self, status, message):
        self.status = status
        super().__init__(f"HTTP {status}: {message}")


class RateLimited(Unavailable):
    """One shared terminal rate-limit failure, reused by all collectors."""
    def __init__(self, retry_after, *, authenticated, reason):
        self.retry_after = max(0, math.ceil(retry_after))
        self.authenticated = authenticated
        guidance = (
            "A token is configured; wait for GitHub's limit to reset."
            if authenticated else
            "Run gh auth login, configure a Git HTTPS credential helper, "
            "or set GITHUB_TOKEN for authenticated requests; otherwise wait and rerun."
        )
        super().__init__(f"Rate limited: retry after {self.retry_after}s. {reason}. {guidance}")

class Cancelled(Exception):
    """Cancellation propagates to the caller; it is never a missing field."""
