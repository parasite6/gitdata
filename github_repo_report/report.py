"""Assemble the report without terminal I/O or process exit behavior."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Lock

from .api import API
from . import collectors
from .contents import repository_contents_size
from .errors import Unavailable
from .models import Report
from .ordering import ordered_report
from .inputs import repository
from .platforms import PlatformInference


# Fixed report checks, not an estimate of seconds or unknown pagination work.
# CLI adds authentication, formatting and delivery to this explicit plan.
REPORT_TASKS = (
    "repository_metadata", "default_branch_head", "repository", "owner", "stars",
    "forks", "age", "topics", "homepage", "links", "license_detected_by_github",
    "repository_contents_size", "commits_reachable_from_default_branch_head",
    "contributors", "tag_count", "branches", "pr_open", "pr_total", "pr_merged",
    "languages", "_mixed_issues_open", "_mixed_issues_total", "readme_first_20_lines",
    "release_count_visible_to_caller", "_workflows", "_release_assets",
    "pr_closed_including_merged", "pr_closed_unmerged", "issues_open", "issues_total",
    "issues_closed", "supported_platforms", "collection",
)


def build_report(api: API, name: str) -> Report:
    started = datetime.now(timezone.utc)
    root = "/repos/" + name
    completed = set()
    progress_lock = Lock()
    api.progress("plan", "Repository report", completed=0, total=len(REPORT_TASKS), unit="checks")

    def done(key):
        with progress_lock:
            completed.add(key)
            api.progress("task_done", key, completed=len(completed), total=len(REPORT_TASKS), unit="checks")

    api.progress("field", "repository_metadata")
    repo = api.get(root).json()
    # Use the canonical name after transfers/renames.
    try:
        if not isinstance(repo, dict) or not isinstance(repo.get("full_name"), str):
            raise ValueError
        canonical = repository(repo["full_name"])
    except (ValueError, TypeError) as e:
        raise Unavailable("GitHub returned invalid repository metadata") from e
    root = "/repos/" + canonical
    done("repository_metadata")
    report: Report = {}

    def evaluate(key, operation):
        api.progress("field", key.lstrip("_"))
        try:
            result = {"value": operation()}
        except (Unavailable, UnicodeError, ValueError, KeyError, TypeError, AttributeError) as e:
            result = {"value": None, "unavailable": str(e)}
        done(key)
        return result

    def field(key, operation):
        report[key] = evaluate(key, operation)
        return report[key]["value"]

    def batch(operations):
        # Only independent collectors run together. Each collector still follows
        # every pagination link; the shared API bounds HTTP concurrency globally.
        executor = ThreadPoolExecutor(max_workers=api.workers)
        futures = {}
        try:
            futures = {key: executor.submit(evaluate, key, operation)
                       for key, operation in operations}
            results = {key: future.result() for key, future in futures.items()}
        except BaseException:
            api.cancel_event.set()
            for future in futures.values():
                future.cancel()
            raise
        finally:
            executor.shutdown(wait=True, cancel_futures=True)
        # Preserve a stable report order irrespective of request completion order.
        report.update((key, result) for key, result in results.items()
                      if not key.startswith("_"))
        return results

    sha = field("default_branch_head", lambda: collectors.head(api, root))
    field("repository", lambda: repo["full_name"])
    field("owner", lambda: {k: repo["owner"][k] for k in ("login", "type", "html_url")})
    field("stars", lambda: repo["stargazers_count"])
    field("forks", lambda: repo["forks_count"])
    field("age", lambda: {"created_at": repo["created_at"],
          "elapsed_days": (started - datetime.fromisoformat(
              repo["created_at"].replace("Z", "+00:00"))).total_seconds() / 86400})
    field("topics", lambda: repo["topics"])
    field("homepage", lambda: repo["homepage"])
    field("links", lambda: {k: repo[k] for k in ("html_url", "url", "clone_url", "ssh_url")})
    field("license_detected_by_github", lambda: repo["license"])

    inference = PlatformInference()
    results = batch([
        ("repository_contents_size", lambda: repository_contents_size(api, root, sha)),
        ("commits_reachable_from_default_branch_head", lambda: collectors.commits(api, root, sha)),
        ("contributors", lambda: collectors.contributors(api, root)),
        ("tag_count", lambda: api.count(root + "/tags")),
        ("branches", lambda: collectors.branches(api, root)),
        ("pr_open", lambda: api.count(root + "/pulls", state="open")),
        ("pr_total", lambda: api.count(root + "/pulls", state="all")),
        ("pr_merged", lambda: collectors.merged(api, root)),
        ("languages", lambda: collectors.languages(api, root)),
        ("_mixed_issues_open", lambda: api.count(root + "/issues", state="open")),
        ("_mixed_issues_total", lambda: api.count(root + "/issues", state="all")),
        ("readme_first_20_lines", lambda: collectors.readme(api, root, sha, inference.observe)),
        ("release_count_visible_to_caller", lambda: collectors.releases(api, root)),
        ("_workflows", lambda: inference.collect_workflows(api, root, sha)),
        ("_release_assets", lambda: inference.collect_releases(api, root)),
    ])
    pr_open = report["pr_open"]["value"]
    pr_total = report["pr_total"]["value"]
    merged_count = report["pr_merged"]["value"]
    closed = field("pr_closed_including_merged", lambda: collectors.difference(pr_total, pr_open))
    field("pr_closed_unmerged", lambda: collectors.difference(closed, merged_count))
    # The issues endpoint mixes issues and PRs. Subtract matching complete
    # counts; missing prerequisites propagate as unavailable, never as zero.
    def issue_count(key, prs):
        mixed = results[key]
        if "unavailable" in mixed:
            raise Unavailable(mixed["unavailable"])
        return collectors.difference(mixed["value"], prs)

    issue_open = field("issues_open", lambda: issue_count("_mixed_issues_open", pr_open))
    issue_total = field("issues_total", lambda: issue_count("_mixed_issues_total", pr_total))
    field("issues_closed", lambda: collectors.difference(issue_total, issue_open))
    for key in ("readme_first_20_lines",):
        if "unavailable" in report[key]:
            inference.errors.append(report[key]["unavailable"])
    for key in ("_workflows", "_release_assets"):
        if "unavailable" in results[key]:
            inference.errors.append(results[key]["unavailable"])
    report["supported_platforms"] = inference.result()
    done("supported_platforms")
    report["collection"] = {
        "started_at": started.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "note": "No atomic REST snapshot. Counts cover API-visible current objects; "
                "concurrent changes, caches, deleted/transferred objects affect history. "
                "Commit count, README and workflows use the captured default-branch SHA. "
                "All-refs unique commit count and distinct-human contributor count are unavailable."}
    done("collection")
    return ordered_report(report)
