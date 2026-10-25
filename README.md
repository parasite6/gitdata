# gitdata

> Modular Python 3.10+ CLI + reusable reporting core. Only extra dependency: `httpx`.

---

## Cheat sheet

```bash
pip install .
gitdata -repo 'example/repo'               # default table
gitdata -repo 'example/repo' --json      # machine-readable
gitdata -repo 'example/repo' --plain     # readable labels / %
gitdata -repo 'example/repo' --md -o r.md # markdown report
gitdata --repo https://... --verbose
```

> Tip: No flags or args results in the output of `--help`

| Flag | Meaning |
|------|---------|
| `-repo` / `--repo` | Repository spec (local or URL) |
| `--json` / `--plain` / `--md` | Output format (mutually exclusive) |
| `-o FILE/PATH` | Save to file; creates dirs; needs filename |
| `--verbose` | Verbose logging |
| `--no-progress` | Hide progress bar |
| `--workers N` | Concurrent workers (1–8, default 4) |

---

## Table of contents

- [What it is](#what-it-is)
- [Quick start](#quick-start)
- [Run examples](#run-examples)
- [Output formats](#output-formats)
- [Terminal progress](#terminal-progress)
- [Report ordering](#report-ordering)
- [Repository contents size](#repository-contents-size)
- [Speed](#speed)
- [Authentication](#authentication)
- [Layout / reuse / testing](#layout--reuse--testing)
- [Counting limits](#counting-limits)

---

## What it is

Collects repo metadata (GitHub or spec) and outputs a structured report.

Every report includes:
- Repo, owner, age, language %, counts, homepage/links
- Branches, contributors, README (fenced in `--md`)
- Inferred platforms + evidence notes
- Repocontents size — exact git-blob sums (not estimates)

---

## Quick start

```bash
pip install .
gitdata -repo 'example/repo'
```

> Tip: `gitdata` alone prints help and exits successfully — no API calls.

---

## Run examples

| Goal | Command |
|------|---------|
| Table to terminal | `gitdata -repo 'example/repo'` |
| JSON file | `gitdata -repo 'example/repo' --json -o reports/x.json` |
| Plain text | `gitdata -repo 'example/repo' --plain -o report.txt` |
| Markdown | `gitdata -repo 'example/repo' --md -o reports/x.md` |
| Verbose + URL | `gitdata --repo https://github.com/example/repo --verbose` |

---

## Output formats

| Flag | Use | Notes |
|------|-----|-------|
| `--json` | Pipelines / APIs | Keeps float values; fixed key order |
| `--plain` | Human review | Readable labels + nested lists + rounded floats |
| `--md` | Docs / repo notes | Summary table + sections + fenced README excerpt |

Rules:
- Mutually exclusive.
- Terminal table is default.
- `-o FILE`: parent dirs auto-created; replaces only after full write; path must include filename; extension does not choose format; partial reports exit 2; fatal errors leave existing file untouched.
- 
- If a SOCKS proxy is required, install with `python -m pip install "httpx[socks]>=0.27,<1"`. Invalid proxy setup produces controlled errors (no tracebacks).
- On limited encodings, unprintable chars become backslash escapes; saved files always UTF-8.

---

## Terminal progress

**Quick:** single-line bar on stderr when TTY attached; orange segment + gray track; Unicode spinner (falls back to `/--\--`); count + elapsed + active op; adapts to narrow; disabled by `NO_COLOR` / `CLICOLOR=0` / `TERM=dumb` / `--no-progress`.

**Percent:** counts real completed checks (auth, plan, format, output). Updates up to 60 fps; can briefly trail. Not an estimate of remaining time. Long paginated checks show page counts; rate-limit waits show retry countdown.

**Stop:** 100% only after flush/file write (≤240 ms transition, then stops — no pause). Partial = "Done (partial)" (all checks done, some missing). Fatal/cancel/write-fail stops below 100%.

> Report content / saved files never contain progress output. Verbose logs print above bar.

**Details:** percentages absorb bursts without predicting work. Check counter = exact completed count. Animation never invents percentage increases during network waits.

---

## Report ordering

Fixed sequence across all formats (even dicts from other callers):

1. Compact: repo, owner, age, language %, counts, contents size, homepage, links
2. Collection notes: branches, contributors, README
3. Inferred platforms + evidence

---

## Repository contents size

Always in output as `repository_contents_size`.

**What:** tracked file content bytes on captured default branch; decimal MB/GB; exact git-tree blob sizes (not GitHub estimate). No clone/checkout/temp repo needed.

**How:** usually one tree request; if truncated, nonrecursive subtrees traversed with no file cap. Missing/incomplete = unavailable, not partial.

**Included:** tracked content, symlink blobs, tracked LFS pointers. **Excluded:** `.git` history, filesystem allocation, releases, untracked build outputs, submodules, external LFS payloads. Identical paths counted per occurrence; shared subtrees summed once per SHA.

> Former clone-measurement flags removed.

A complete recursive tree normally needs one request; if truncated, nonrecursive subtrees are traversed without file-count cap. Missing/incomplete = unavailable, never partial. Identical files at different paths counted per occurrence; shared subtrees summed once per SHA and reused per path (avoids exponential expansion).

Explicit limits (stated in all output formats): excludes `.git` history, filesystem allocation, release attachments, untracked build outputs. Submodule repos and external Git LFS payloads excluded; tracked LFS pointer bytes included. Symlink blobs included.

**Mechanics:** a complete recursive tree normally needs one request; if truncated, nonrecursive subtrees are traversed without file-count cap. Missing/incomplete = unavailable, never partial. Identical files at different paths counted per occurrence; shared subtrees summed once per SHA and reused per path (avoids exponential expansion in shared trees).

**Explicit limits (all formats state these):** excludes `.git` history, filesystem allocation, release attachments, untracked build outputs. Submodule repos and external Git LFS payloads excluded; tracked LFS pointer bytes included. Symlink blob bytes included.

---

## Speed

- Default 4 workers; HTTP reused; paginated streams complete.
- Serial: `--workers 1`; max 8.
- Small contributor lists often skip second count.
- Large counts use pagination; never truncated.

**Release counts** use pagination independently of platform inference.

**Platform inference** reuses asset metadata in release-list responses (avoids extra asset-list per release). Fallback to paginated assets if embedded metadata missing.

---

## Authentication

Tries `GITHUB_TOKEN` → configured `gh` token → unauthenticated public.

- Unauthenticated: 60/hour.
- Authenticated: up to 5,000/hour (classic) or 15,000/hour (fine-grained).
- No prompts.

---

## Layout / reuse / testing

- `gitdata/` source; `tests/` fixtures; `reports/` examples (ignored at install).
- Core is importable — pass repo spec → get dict; stages separated; GUI can reuse collectors + renderers + progress events.
- Offline: fixtures in `tests/`; refresh with `--record` against live repo, then copy to fixtures.

---


---

## Code map

| Module | Responsibility |
|--------|----------------|
| `api.py` | Authentication, HTTP, pagination, retry budget, cancellation |
| `auth.py` | Environment, GitHub CLI and Git HTTPS credential discovery |
| `processes.py` | Bounded helper execution and descendant cleanup |
| `collectors.py` | Independently testable field collectors and count arithmetic |
| `report.py` | Report assembly and per-field unavailable handling |
| `platforms.py` | Workflow inspection and explicitly inferred platform evidence |

## Counting limits

| Count | Endpoint | Notes |
|-------|----------|-------|
| Branches | Branches | — |
| Contributors | Contributors + pagination | Small lists avoid second request |
| Releases | Releases + pagination | Independent of platform evidence |
| Followers | Followers + pagination | — |
| Languages | Languages | Normalized to 100% |

Limits stated in all outputs; missing = omitted, never guessed.
