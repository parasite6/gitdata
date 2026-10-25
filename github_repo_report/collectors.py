"""Small independently testable collectors; no terminal output."""
from .errors import APIError, RateLimited, Unavailable

def head(api, root):
    """Capture the default-branch head, or EMPTY only for an empty repository."""
    try:
        commits = api.get(root + "/commits", {"per_page": 1}).json()
        return commits[0]["sha"] if commits else "EMPTY"
    except APIError as e:
        if e.status == 409 and "empty" in str(e).lower():
            return "EMPTY"
        raise


def commits(api, root, sha):
    """Count commits reachable from the captured head, not every repository ref."""
    if sha is None:
        raise Unavailable("Default branch head unavailable")
    return 0 if sha == "EMPTY" else api.count(root + "/commits", sha=sha)


def contributors(api, root):
    """Return API contributor entries including anonymous entries, and top ten."""
    path = root + "/contributors"
    # anon=1 includes authors beyond the 500-email account-linking limit.
    # API ordering is descending contributions; first ten is the API top ten.
    top = api.get(path, {"anon": "1", "per_page": 10})
    rows = [] if top.status_code == 204 else top.json()
    # A complete first page needs no second count request. Larger lists still
    # use the per_page=1 last-link method; no repository-size cap is introduced.
    total = api.count(path, anon="1") if top.links.get("next") else len(rows)
    return {"total_api_entries": total,
            "top_10": [{k: c[k] for k in (
                "login", "name", "html_url", "type", "contributions") if k in c}
                       for c in rows],
            "note": "Cached API identities, not a count of distinct humans"}


def branches(api, root):
    """Return the complete API-visible branch list and its length."""
    # The full list was requested, so all pages are unavoidable. Count the
    # completed list instead of spending extra requests on a separate count.
    names = [b["name"] for b in api.pages(root + "/branches")]
    return {"count": len(names), "names": names}


def difference(a, b):
    """Subtract complete counts; missing or inconsistent inputs stay unknown."""
    if a is None or b is None:
        raise Unavailable("A required count is unavailable")
    if a < b:
        raise Unavailable("Inconsistent counts; repository changed during collection")
    return a - b


def merged(api, root):
    """Count merged PRs by inspecting the complete closed-PR listing."""
    # REST has no merged-only list count. Inspect every closed PR, 100/page.
    # Search is avoided: its index is not an authoritative repository census.
    count = 0
    for pr in api.pages(root + "/pulls", state="closed", sort="created", direction="asc"):
        count += pr["merged_at"] is not None
    return count


def issues(api, root, state, prs):
    """Subtract a matching PR count from the mixed issues endpoint count."""
    # /issues includes PRs; subtract the matching /pulls count, never trust
    # repo.open_issues_count as an issue-only count. Link counts avoid scans.
    return difference(api.count(root + "/issues", state=state), prs)


def languages(api, root):
    """Convert GitHub code-byte totals to percentages with their raw bytes."""
    values = api.get(root + "/languages").json()
    total = sum(values.values())
    return {k: {"bytes": v, "percent": 100 * v / total}
            for k, v in values.items()} if total else {}


def readme(api, root, sha, observe):
    """Read pinned README text, collect evidence, and return its first 20 lines."""
    if sha is None:
        raise Unavailable("Cannot pin README without default branch head")
    if sha == "EMPTY":
        raise Unavailable("Empty repository has no README")
    r = api.get(root + "/readme", {"ref": sha},
                accept="application/vnd.github.raw+json")
    text = r.content.decode("utf-8-sig")
    for n, line in enumerate(text.splitlines(), 1):
        observe(line, f"README:{n}")
    return text.splitlines()[:20]


def releases(api, root):
    """Count releases cheaply, independently of optional asset evidence."""
    return api.count(root + "/releases")


def release_assets(api, root, observe, inference_errors):
    """Inspect asset metadata without one extra request for every release."""
    for release in api.pages(root + "/releases"):
        try:
            # Release listings already contain asset metadata. Platform
            # inference can use it directly: we do not claim an exact asset
            # inventory or count. Follow every release-list page, without a cap.
            assets = release.get("assets")
            if assets is None:
                # Defensive fallback for responses without embedded assets.
                assets = api.pages(root + f"/releases/{release['id']}/assets")
            elif not isinstance(assets, list):
                raise Unavailable("Invalid embedded release asset list")
            for asset in assets:
                api.check_cancelled()
                observe(asset["name"], asset["browser_download_url"])
        except RateLimited:
            # This is a global failure, not one independent error per release.
            # Propagate immediately; preserve already collected evidence.
            raise
        except (Unavailable, KeyError, ValueError) as e:
            inference_errors.append(f"Release {release['id']} assets: {e}")
