"""GitHub REST transport, complete pagination, retries and cancellation."""
from email.utils import parsedate_to_datetime
import math
from threading import BoundedSemaphore, Event, RLock
import time
from urllib.parse import parse_qs, urlsplit

import httpx

from .errors import APIError, Cancelled, RateLimited, Unavailable
from .auth import resolve_credentials
from .models import ProgressCallback, ProgressEvent

class API:
    def __init__(self, max_wait: float = 60, *,
                 client: httpx.Client | None = None, token: str | None = None,
                 on_progress: ProgressCallback | None = None,
                 cancel_event: Event | None = None, workers: int = 4,
                 credential_repo: str | None = None):
        if not math.isfinite(max_wait) or max_wait < 0:
            raise ValueError("max_wait must be finite and nonnegative")
        if not isinstance(workers, int) or not 1 <= workers <= 8:
            raise ValueError("workers must be between 1 and 8")
        self.workers = workers
        self._requests = BoundedSemaphore(workers)
        self._retry_lock = RLock()
        self._rate_generation = 0
        self._rate_deadline = 0.0
        self.on_progress = on_progress
        self.cancel_event = cancel_event if cancel_event is not None else Event()
        self.wait_left = max_wait
        self.blocked = None
        self.rate_limit = None
        self._owns_client = client is None
        headers = {"Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28",
                   "User-Agent": "github-repository-report"}
        credentials = resolve_credentials(token, repo=credential_repo)
        self.auth_source = credentials.source
        if credentials.token:
            headers["Authorization"] = "Bearer " + credentials.token
        self.headers = headers
        try:
            self.client = client if client is not None else httpx.Client(timeout=45)
        except ImportError as e:
            raise Unavailable("HTTP client setup failed: SOCKS proxies require "
                              "httpx[socks]. Install that extra or use an HTTP(S) proxy.") from e

    def close(self):
        """Injected clients belong to the caller; owned clients are closed here."""
        if self._owns_client:
            self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def check_cancelled(self):
        if self.cancel_event.is_set():
            raise Cancelled("Collection cancelled")

    def progress(self, phase, message, *, retry_seconds=None,
                 completed=None, total=None, unit=None):
        self.check_cancelled()
        if self.on_progress is not None:
            self.on_progress(ProgressEvent(phase, message, retry_seconds, completed, total, unit))
        self.check_cancelled()

    def sleep(self, seconds):
        # Shared budget and pause: sibling collectors must not keep issuing
        # new requests while one thread waits for GitHub's rate-limit reset.
        with self._retry_lock:
            self._sleep(seconds)

    def _sleep(self, seconds):
        self.check_cancelled()
        seconds = max(0, seconds)
        if seconds > self.wait_left:
            raise Unavailable(f"Retry needs {seconds:.0f}s; wait budget exhausted")
        self.wait_left -= seconds
        self.progress("retry", f"Retrying after {seconds:.0f}s...",
                      retry_seconds=seconds)
        # Event.wait makes long rate-limit waits cancellable by a GUI worker.
        if self.cancel_event.wait(seconds):
            raise Cancelled("Collection cancelled")

    def get(self, path: str, params: dict | None = None,
            accept: str | None = None) -> httpx.Response:
        self.check_cancelled()
        if self.blocked:
            raise self.rate_limit or Unavailable(self.blocked)
        url = path if path.startswith("https://") else "https://api.github.com" + path
        # Never send the token to an arbitrary Link or redirect destination.
        for attempt in range(5):
            if urlsplit(url).scheme != "https" or urlsplit(url).netloc != "api.github.com":
                raise Unavailable("Refused API link outside api.github.com")
            try:
                with self._requests:
                    with self._retry_lock:
                        self.check_cancelled()
                        if self.blocked:
                            raise self.rate_limit or Unavailable(self.blocked)
                        generation = self._rate_generation
                    self.progress("request", url)
                    r = self.client.get(url, params=params,
                                        headers={**self.headers, **({"Accept": accept} if accept else {})},
                                        follow_redirects=False)
            except httpx.TransportError as e:
                if attempt == 4:
                    raise Unavailable(type(e).__name__) from e
                self.sleep(2 ** attempt)
                continue
            self.check_cancelled()
            if r.status_code in (301, 302, 307, 308):
                url = str(r.url.join(r.headers["Location"]))
                params = None
                continue
            if r.status_code < 300 and r.status_code != 202:
                # Validate JSON centrally before any collector uses .json().
                # Raw README/workflow media and 204 responses have no JSON body.
                if r.status_code != 204 and (accept is None or ("json" in accept and ".raw" not in accept)):
                    try:
                        data = r.json()
                    except (ValueError, UnicodeError) as e:
                        raise Unavailable("GitHub returned invalid JSON") from e
                    if not isinstance(data, (dict, list)):
                        raise Unavailable("GitHub returned an unexpected JSON value")
                return r
            try:
                message = r.json().get("message", r.reason_phrase)
            except (ValueError, AttributeError):
                message = r.reason_phrase
            limited = r.status_code == 429 or (
                r.status_code == 403 and (
                    r.headers.get("x-ratelimit-remaining") == "0"
                    or "retry-after" in r.headers
                    or "rate limit" in message.lower()))
            if limited:
                waits = [60 * 2 ** attempt]
                if "retry-after" in r.headers:
                    v = r.headers["retry-after"]
                    try:
                        waits = [float(v)]
                    except ValueError:
                        waits = [parsedate_to_datetime(v).timestamp() - time.time()]
                if r.headers.get("x-ratelimit-remaining") == "0":
                    waits.append(float(r.headers.get("x-ratelimit-reset", time.time() + 60))
                                 - time.time() + 1)
                deadline = time.monotonic() + max(waits)
                with self._retry_lock:
                    if self.blocked:
                        raise self.rate_limit or Unavailable(self.blocked)
                    # Several in-flight requests can hit the same cooldown.
                    # Reuse elapsed waits, extending them for a longer deadline
                    # rather than ignoring a sibling's longer Retry-After.
                    try:
                        if generation == self._rate_generation and attempt == 4:
                            raise Unavailable("Rate limit persists after retries")
                        remaining = deadline - max(time.monotonic(), self._rate_deadline)
                        if remaining > 0:
                            self.sleep(remaining)
                        self._rate_deadline = max(self._rate_deadline, deadline)
                        self._rate_generation += 1
                    except Unavailable as e:
                        self.rate_limit = RateLimited(
                            max(0, deadline - time.monotonic()),
                            authenticated=bool(self.headers.get("Authorization")),
                            reason=("The --max-wait budget is exhausted"
                                    if "wait budget exhausted" in str(e) else str(e)),
                        )
                        self.blocked = str(self.rate_limit)
                        raise self.rate_limit from e
                continue
            if r.status_code == 202 or 500 <= r.status_code < 600:
                if attempt < 4:
                    self.sleep(2 ** attempt)
                    continue
            raise APIError(r.status_code, message)
        raise Unavailable("Too many redirects or retries")

    def pages(self, path, **params):
        r = self.get(path, {**params, "per_page": 100})
        page = 1
        while True:
            items = [] if r.status_code == 204 else r.json()
            if not isinstance(items, list):
                raise Unavailable("Expected an API list")
            for item in items:
                self.check_cancelled()
                yield item
            # A page completes only once all its records have been consumed.
            # Last-page metadata describes this stream, not the whole report.
            last = r.links.get("last", {}).get("url")
            query = parse_qs(urlsplit(last).query) if last else {}
            total = int(query["page"][0]) if query.get("page", [""])[0].isdigit() else None
            if not r.links.get("next"):
                total = page
            self.progress("page", path.split("?")[0], completed=page, total=total, unit="pages")
            nxt = r.links.get("next", {}).get("url")
            if not nxt:
                return
            r = self.get(nxt)
            page += 1

    def count(self, path: str, **params) -> int:
        # With per_page=1, the last page number equals the total item count.
        # Do NOT use the last page number from per_page=100 as the count.
        # Some endpoints omit 'last'; then follow ALL pages, without a cap.
        r = self.get(path, {**params, "per_page": 1})
        items = [] if r.status_code == 204 else r.json()
        if not isinstance(items, list):
            raise Unavailable("Expected an API list")
        last = r.links.get("last", {}).get("url")
        if last:
            query = parse_qs(urlsplit(last).query)
            if query.get("per_page") == ["1"] and "page" in query:
                return int(query["page"][0])
        if not r.links.get("next"):
            return len(items)
        return sum(1 for _ in self.pages(path, **params))
