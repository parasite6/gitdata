# gitdata

A modular Python 3.10+ CLI and reusable reporting core. The only runtime
dependency beyond the standard library is `httpx`.

## Run

From the extracted project directory:

```bash
pip install .
gitdata -repo 'example/repo'
gitdata -repo 'example/repo' --json
gitdata -repo 'example/repo' --plain
gitdata -repo 'example/repo' --plain -o report.txt
gitdata -repo 'example/repo' --json -o reports/example.json
gitdata -repo 'example/repo' --md -o reports/example.md
gitdata --repo https://github.com/example/repo --verbose
```

Running `gitdata` without a repository prints help and exits successfully,
without making API requests. `gitdata --help` also shows all options.

## Terminal progress

An automatic, single-line progress bar appears on stderr when attached to a
terminal. It uses an orange growing section against a muted gray track, a Unicode dot spinner, completed-check
counts, elapsed time and the active operation. It falls back to ASCII when the
terminal encoding cannot display the bar characters (with a `/--\--` spinner
fallback), and adapts to narrow
terminal widths. `NO_COLOR` or `CLICOLOR=0` disables color.

Percentages count actual completed checks: authentication, the fixed report
plan, formatting, and output delivery. The displayed percentage smoothly follows
earned progress at up to 60 frames per second, absorbing bursts of completed
checks without predicting work. The check counter remains the exact completed
count; the animated percentage can briefly trail it.
Percentages are not an estimate of elapsed or remaining time. Longer paginated
checks show consumed page counts (and the total when GitHub provides it), while
rate-limit waits show a retry countdown. The animation keeps running without
inventing percentage increases during a network wait.

100% appears only after the report has been printed/flushed or the output file
has been successfully written. A final transition takes at most 240 ms, then
the animation stops immediately at 100%; there is no pause at 100%. A partial report ends with "Done (partial report)"
because all checks were processed, even if some values are unavailable. A fatal
error, cancelled scan or failed file write stops below 100%.

JSON/Markdown/plain report content and saved files do not contain progress
output. The bar is disabled automatically when stderr is redirected or
`TERM=dumb`, and can be hidden with `--no-progress`. Verbose logs are printed
above the bar without corrupting its line.

`--plain` uses readable labels, nested lists, thousands separators, and language
percentages instead of the table's JSON-like values. It retains all report
fields and explicitly inferred platform evidence. Displayed floating-point
values are rounded; `--json` retains the underlying numeric values.

`--md` produces GitHub-flavored Markdown with a summary table, detailed sections,
a language table, and a fenced README excerpt. It retains unavailable values,
platform-inference caveats, evidence and collection errors. Repository text is
escaped outside the README code block; README fences are chosen to keep its
contents inside that block. `--md`, `--plain` and `--json` are mutually exclusive;
the terminal table remains the default.

`-o FILE` (or `--output FILE`) saves the selected format as UTF-8 instead of
printing the report. Parent directories are created as needed, and an existing
file is replaced after the new report is fully written. An output path must
include a filename. The extension does not select the format: use `--json`,
`--plain` or `--md` explicitly. Partial reports are saved with unavailable fields and
exit code 2; fatal API failures leave an existing output file untouched.

On output streams with limited encodings, characters that cannot be represented
are printed as backslash escapes. Saved reports always use UTF-8. Invalid API
JSON, malformed root metadata, unsupported SOCKS proxy setup, invalid home-directory
paths and closed output pipes produce controlled errors instead of tracebacks.
If a SOCKS proxy is required, install its optional transport dependency with
`python -m pip install "httpx[socks]>=0.27,<1"`.

## Report ordering

All formats, including JSON key order, put compact facts first: repository, owner,
age, language percentages, counts, contents size, homepage and links. Collection
notes and longer blocks follow: branches, contributors, README, then inferred
platforms and their evidence. Ordering is shared across renderers, including when
they receive a report dictionary assembled by another caller.

## Repository contents size

The normal report always includes `repository_contents_size`: the sum of tracked
file content bytes on the captured default branch, with MB/GB in decimal units.
It uses exact Git-tree blob sizes, not GitHub's repository-size estimate.
No extra flag, clone, checkout or temporary repository is needed.

A complete recursive tree normally needs one tree request. If GitHub truncates
it, nonrecursive subtrees are traversed without a file-count cap. Missing sizes
or incomplete trees make the field unavailable rather than returning a partial
sum. Identical files at different paths are counted for each occurrence.
Shared subtrees are summed once per SHA and their totals reused for each path,
avoiding exponential path expansion in heavily shared Git trees.

This is repository content, excluding `.git` history, filesystem allocation,
release attachments, and untracked dependencies/build outputs. Symlink blob
bytes are included. Submodule repositories and external Git LFS payloads are
excluded; tracked LFS pointer bytes are included. These limits are stated in
all output formats. The former clone-measurement flags and implementation have
been removed.

## Speed

Independent collectors overlap network waits using four workers by default;
HTTP connections are reused, and each paginated stream remains complete.
`--workers 1` selects serial collection; up to eight workers are allowed.
Small contributor lists no longer need a second count request. Large counts
still use pagination metadata, and complete lists are never truncated for speed.

Release counts use pagination metadata independently of platform evidence.
Platform inference reuses asset metadata embedded in release-list responses,
avoiding one extra asset-list request for every release. An endpoint response
without embedded asset metadata falls back to that release's paginated assets
endpoint. No exhaustive asset inventory or asset count is claimed.

Rate-limit pauses and the retry wait budget are shared across workers. New
requests pause during a cooldown, already in-flight requests may finish, and
longer `Retry-After` deadlines extend the shared pause. GitHub recommends serial
requests to minimize secondary rate limits; use `--workers 1` if needed.
See https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api.

When the wait budget is exhausted, asset processing stops immediately. All
collectors reuse the same terminal rate-limit failure, and platform errors
deduplicate it rather than printing one copy per release. Already collected
evidence remains visible; incomplete count fields stay unavailable. Release
counts that completed before an inference failure remain valid.

GitHub limits unauthenticated requests to 60 per hour per originating IP. A
personal access token typically allows 5,000 per hour. Configure `GITHUB_TOKEN`
for large scans; authentication does not remove all rate limits. Otherwise wait
for the limit to reset, or deliberately allow a longer wait with
`--max-wait 3600`. Increasing workers does not increase the API allowance.
See https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api.

Speedups depend on repository size, API latency and rate limits. Merged-PR
inspection, full branch lists and release evidence still require all their pages. An
offline latency benchmark is available with `python -m tests.benchmark`.

Installation creates the `gitdata` command, including a command launcher on
Windows. The Python environment's scripts directory must be on PATH; if using
a virtual environment, activate it first. Python 3.10+ is required. This is an
installed command, not a standalone binary. If you use pipx, `pipx install .`
installs it into an isolated environment with a command exposed on PATH.

For development, use an editable installation so source edits take effect:

```bash
python -m pip install -e .
gitdata -repo owner/repo
```

The positional form `gitdata owner/repo`, the previous `github-report` command,
`python -m github_repo_report owner/repo`, and the `github_report.py` launcher
remain supported. Supply the repository once, either positionally or using
`-repo`/`--repo`.

Existing GitHub credentials are detected automatically; no environment variable
is required when GitHub CLI or a Git HTTPS helper already has a usable token.
Token permissions determine which private objects and draft releases are visible.
`--max-wait SECONDS`
controls the total retry wait budget (default 60). `--verbose` reports fields
and request URLs on stderr; JSON stdout remains machine-readable.

Exit codes: 0 complete, 1 fatal API failure, 2 partial report, 130 interrupted.
Missing README or inaccessible platform evidence makes a report partial.
The current repository owner is shown as "Repo owner" in text/Markdown output
and under the `owner` key in JSON; no repository-author field is emitted.

## Automatic authentication

The CLI checks these sources in order:

1. `GITHUB_TOKEN`.
2. `GH_TOKEN`.
3. The active GitHub CLI account for github.com, via `gh auth token --hostname github.com`.
4. Git's configured HTTPS credential helper, via `git credential fill`, using
   github.com and the requested repository path as context.
5. Anonymous public access if no usable local credential is found.

If you're already signed into `gh`, just run:

```bash
gitdata -repo 'example/repo' --plain -o report.txt
```

If needed, sign in once using `gh auth login --hostname github.com`. The tool
does not run login itself, change the active account, or save a new token. For
multiple gh accounts, select the intended active account with `gh auth switch`.

Git name/email settings are commit identity, not a GitHub login. SSH keys used
for `git push` cannot authenticate the REST API. Git HTTPS credential helpers
can supply a stored PAT/OAuth token; that credential still needs appropriate API
permissions. Invalid/revoked credentials produce an API error; the tool does
not silently rotate accounts or retry with anonymous access after a rejection.

Credential commands capture output privately, do not put tokens in command-line
arguments, and have a five-second timeout per command. On timeout or interruption,
the tool terminates the command process group on POSIX, or uses Windows
`taskkill /T /F` to terminate its process tree, before reaping the command.
Git terminal/askpass
prompts and standard Git Credential Manager interactivity are disabled. Custom
helpers are trusted local configuration and must honor noninteractive settings.
The tool does not directly read credential files or SSH private keys. It does
not print tokens, store them in reports, or persist them itself.

Use `--verbose` to see the selected authentication source (never the token).
Use `--no-auth` to disable environment and local credential lookup entirely.

References:
- https://cli.github.com/manual/gh_auth_token
- https://git-scm.com/docs/git-credential
- https://git-scm.com/docs/gitcredentials

## Code map

| Module | Responsibility |
| --- | --- |
| `api.py` | Authentication, HTTP, pagination, retry budget, cancellation |
| `auth.py` | Environment, GitHub CLI and Git HTTPS credential discovery |
| `processes.py` | Bounded helper execution and descendant cleanup |
| `collectors.py` | Independently testable field collectors and count arithmetic |
| `report.py` | Report assembly and per-field unavailable handling |
| `platforms.py` | Workflow inspection and explicitly inferred platform evidence |
| `models.py` | Shared report typing, progress events, partial-report classification |
| `progress.py` | Terminal bar, page/retry status and thread-safe completed-check tracking |
| `inputs.py` | Repository URL/name validation |
| `rendering.py` | Plain/table formatting with terminal control escaping |
| `ordering.py` | Shared compact-first report ordering |
| `markdown.py` | Markdown tables, sections and safely fenced README text |
| `output.py` | UTF-8 file saving and atomic replacement |
| `contents.py` | Exact tracked-file byte totals from complete Git trees |
| `cli.py` | Arguments, terminal output and exit codes |
| `errors.py` | API failures, unavailable values and cancellation |
| `__main__.py` | `python -m github_repo_report` entry point |

`github_report.py` is a small compatibility launcher. Counting semantics remain
unchanged. Repo owner replaces the former author field, and `repository_contents_size`
replaces the old API estimate and clone-measurement fields. No GUI is implemented.

## Reuse from a future GUI

Run the synchronous collector outside the GUI thread. Progress callbacks may
run concurrently on collection worker threads; send events through a queue or
your GUI's signal mechanism instead of changing GUI widgets inside callbacks.

```python
from queue import Queue
from threading import Event

from github_repo_report import API, Cancelled, build_report, repository

events = Queue()
cancel = Event()

def collect_in_worker(repo_input):
    try:
        with API(on_progress=events.put, cancel_event=cancel) as api:
            report = build_report(api, repository(repo_input))
        events.put(("finished", report))
    except Cancelled:
        events.put(("cancelled", None))
    except Exception as exc:
        events.put(("error", exc))

# Schedule collect_in_worker("owner/repo") in your GUI's worker mechanism.
# Your Cancel button calls cancel.set(); the UI polls or receives events.
```

Create a fresh API instance and cancellation event for each report. The API
stores retry-budget state and is intended for one collection at a time. To use
an explicitly supplied token, pass `token="..."`; `token=None` performs automatic
discovery, while `token=""` disables all credential lookup. Pass
`credential_repo="owner/repo"` to give Git's helper the repository context.

Cancellation interrupts retry waits and is checked before/after requests,
between paginated records and between fields. An in-flight synchronous HTTP
request completes or reaches its HTTP timeout before cancellation takes effect.
`Cancelled` propagates to the caller; it never becomes an unavailable field.
The core does not print or exit the process. It owns a bounded worker pool and
joins it before returning or propagating cancellation. Other in-flight requests
may still finish before cancellation is returned to the caller.

## Debug and test offline

```bash
python -m unittest discover -s tests -t . -v
```

Tests use `httpx.MockTransport`, require no GitHub token or internet, and cover
million-scale pagination counts, full branch and asset lists, issue/PR
separation, merged PRs, empty repositories, partial failures, authentication,
rate-limit waits, cancellation, progress events, redirects and CLI output.
They also cover bounded concurrent collection, serial/parallel result equality,
shared cooldowns, plain text, no-argument help, and safe file replacement.
Credential discovery tests mock all credential commands, including source precedence, GitHub CLI,
Git helper context, disabled prompts, missing tools, timeouts and secret masking.
Tests do not inspect your actual local credential stores. A separate local Python
parent/child fixture verifies POSIX timeout cleanup without accessing credentials.
Contents-size tests cover complete/truncated trees, shared subtrees, duplicate
file occurrences, symlinks, missing sizes and empty repositories. No repository
is cloned by the tool or its test suite.
Progress tests cover concurrent completion events, exact plan coverage, page
counts, no-argument/redirected behavior, clean JSON, output delivery before 100%,
failed writes, cancellation, color control, narrow terminals and animation cleanup.

To debug a particular API response, inject a client:

```python
import httpx
from github_repo_report import API

def handler(request):
    return httpx.Response(200, json=[])

with httpx.Client(transport=httpx.MockTransport(handler)) as client:
    with API(client=client, token="") as api:
        assert api.count("/repos/owner/repo/tags") == 0
```

An injected client remains owned by its caller and is not closed by `API`.
Authentication and API headers are applied even to injected clients. Redirects
are checked manually so credentials are not forwarded outside api.github.com.

## Counting methods and limits

- Counts use `per_page=1` and the `last` pagination link when available. If
  `last` is absent but `next` exists, all pages are traversed without a cap.
- Branches need every page because the complete list is requested. Release
  counts use the cheap last-link method. For platform inference, every release
  listing page is inspected using its embedded asset metadata; the embedded
  asset inventory is not independently verified as exhaustive.
- Merged PRs are counted by inspecting every closed PR. Issue totals subtract
  matching PR totals from the mixed issues endpoint. Search is not used as an
  authoritative census.
- Contributors include anonymous API entries, including those beyond GitHub's
  account-linking limit. Cached contributor entries are not distinct humans.
  The top ten follows GitHub's contribution ordering. Endpoint failures become
  unavailable values; no partial count is presented as complete.
- Commits mean commits reachable from the captured default-branch SHA, not
  unique commits across every ref. README and workflows use that same SHA.
- REST has no atomic snapshot. Concurrent changes and server caches can affect
  counts; deleted objects and historical repository transfers are not counted.
- Repo owner is current ownership. Age starts at
  GitHub's repository creation timestamp, not the original project's start.
- Repository contents size is always calculated from tracked Git-tree blob
  bytes on the captured default branch. No clone is downloaded.
  Language percentages describe reported code bytes. A null license means no
  detected license; it is not a legal determination. Links are not checked for
  reachability. README decoding assumes UTF-8 and fails explicitly otherwise.
- Platform output is inferred from release filenames, README mentions, and
  workflow matrix/runner text. Text matching is not YAML evaluation: negative
  mentions, CI hosts and excluded values can appear as evidence. Dynamic
  matrices, reusable workflows and external CI are unresolved. No matches means
  unknown, not zero supported platforms. Collection errors remain visible.

The refactor was verified with offline fixtures; no live GitHub scan is part
of its test suite.
