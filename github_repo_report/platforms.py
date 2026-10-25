"""Heuristic platform evidence; never a declaration of verified support."""
import base64
import re
from urllib.parse import quote

from .errors import RateLimited, Unavailable

PATTERNS = {
    "Linux": r"\b(?:linux|ubuntu|debian|fedora|manylinux|musllinux|appimage)\b",
    "Windows": r"\b(?:windows|win32|win64|win-x64|win-arm64)\b|\.msi\b|\.exe\b",
    "macOS": r"\b(?:macos|mac-os|darwin|osx)\b|\.dmg\b",
    "Android": r"\bandroid\b|\.apk\b|\.aab\b",
    "iOS": r"\bios\b|\.ipa\b",
    "FreeBSD": r"\bfreebsd\b",
    "Web/WebAssembly": r"\b(?:webassembly|wasm|emscripten)\b",
}


def matrix_lines(text):
    # Textual heuristic, NOT a YAML parser: inspect matrix blocks and runs-on.
    # Expressions, reusable workflows, YAML aliases and exclusions may defeat it.
    matrix_indent = None
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(stripped)
        if matrix_indent is not None and indent <= matrix_indent:
            matrix_indent = None
        if re.match(r"matrix\s*:", stripped):
            matrix_indent = indent
        if matrix_indent is not None or re.match(r"runs-on\s*:", stripped):
            yield number, line


def workflow_texts(api, root, sha):
    # Traverse only .github/workflows via nonrecursive Git trees. Unlike the
    # Contents directory endpoint, this does not silently stop at 1,000 files.
    tree_sha = api.get(root + "/git/commits/" + sha).json()["tree"]["sha"]
    for directory in (".github", "workflows", None):
        tree = api.get(root + "/git/trees/" + quote(tree_sha, safe="")).json()
        if tree.get("truncated"):
            raise Unavailable("Workflow tree truncated by GitHub")
        entries = tree["tree"]
        if directory is None:
            break
        entry = next((e for e in entries if e["path"] == directory
                      and e["type"] == "tree"), None)
        if entry is None:
            return
        tree_sha = entry["sha"]
    for entry in entries:
        if entry["type"] == "blob" and entry["path"].lower().endswith((".yml", ".yaml")):
            blob = api.get(root + "/git/blobs/" + entry["sha"]).json()
            if blob.get("encoding") != "base64":
                raise Unavailable("Unsupported workflow blob encoding")
            yield entry["path"], base64.b64decode(blob["content"]).decode("utf-8-sig")


class PlatformInference:
    def __init__(self):
        self.evidence = []
        self.errors = []

    def observe(self, text, source):
        for platform, pattern in PATTERNS.items():
            if re.search(pattern, text, re.I):
                self.evidence.append({"platform": platform, "source": source,
                                      "text": text.strip()[:240]})

    def collect_workflows(self, api, root, sha):
        try:
            if sha is None:
                raise Unavailable("Cannot pin workflows without default branch head")
            if sha != "EMPTY":
                for filename, text in workflow_texts(api, root, sha):
                    for n, line in matrix_lines(text):
                        api.check_cancelled()
                        self.observe(line, f".github/workflows/{filename}:{n}")
        except RateLimited as e:
            self.errors.append(str(e))
        except (Unavailable, UnicodeError, ValueError, KeyError) as e:
            self.errors.append(f"Workflows: {e}")

    def collect_releases(self, api, root):
        from .collectors import release_assets

        try:
            release_assets(api, root, self.observe, self.errors)
        except RateLimited as e:
            self.errors.append(str(e))
        except (Unavailable, UnicodeError, ValueError, KeyError) as e:
            self.errors.append(f"Release assets: {e}")

    def result(self):
        return {
            "value": sorted({e["platform"] for e in self.evidence}),
            "status": "inferred; not verified support",
            "evidence": sorted(self.evidence, key=lambda e: (e["source"], e["platform"], e["text"])),
            "collection_errors": sorted(set(self.errors)),
            "note": "Text matches can be negative mentions, CI hosts or excluded matrix values. "
                    "No matches means unknown. External/reusable CI and dynamic matrices are unresolved. "
                    "Release evidence uses asset metadata returned by release listings; an exhaustive "
                    "asset inventory is not verified.",
        }
