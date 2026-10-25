"""Count tracked repository file bytes from complete, pinned Git trees."""
from urllib.parse import quote

from .errors import Unavailable


def entry_totals(entry):
    if entry["type"] == "blob":
        size = entry.get("size")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise Unavailable("A tracked file has no exact byte size")
        return size, 1, 0
    if entry["type"] == "commit":
        return 0, 0, 1
    if entry["type"] == "tree":
        return 0, 0, 0
    raise Unavailable("Unsupported Git tree entry type")


def repository_contents_size(api, root, sha):
    if sha is None:
        raise Unavailable("Default branch head unavailable")
    total = files = submodules = 0
    if sha != "EMPTY":
        tree_sha = api.get(root + "/git/commits/" + sha).json()["tree"]["sha"]

        def get_tree(value, recursive=False):
            return api.get(root + "/git/trees/" + quote(value, safe=""),
                           {"recursive": "1"} if recursive else None).json()

        tree = get_tree(tree_sha, recursive=True)
        if "truncated" not in tree:
            raise Unavailable("Git tree response lacks completeness information")
        if tree["truncated"]:
            # A Git tree is a DAG: different paths can share one subtree SHA.
            # Memoize aggregate totals, not expanded paths, to keep work linear
            # in unique tree entries while counting every directory occurrence.
            totals = {}
            active = set()
            pending = [(tree_sha, False)]
            parts = {}
            while pending:
                api.check_cancelled()
                current, finish = pending.pop()
                if current in totals:
                    continue
                if not finish:
                    if current in active:
                        raise Unavailable("Cyclic Git tree response")
                    active.add(current)
                    part = get_tree(current)
                    if part.get("truncated") is not False:
                        raise Unavailable("Nonrecursive Git tree is incomplete; contents size unavailable")
                    parts[current] = part["tree"]
                    pending.append((current, True))
                    for entry in reversed(part["tree"]):
                        if entry["type"] == "tree":
                            pending.append((entry["sha"], False))
                else:
                    subtotal = [0, 0, 0]
                    for entry in parts.pop(current):
                        api.check_cancelled()
                        values = totals[entry["sha"]] if entry["type"] == "tree" else entry_totals(entry)
                        subtotal = [a + b for a, b in zip(subtotal, values)]
                    totals[current] = subtotal
                    active.remove(current)
            total, files, submodules = totals[tree_sha]
            entries = []
        else:
            entries = tree["tree"]
        for entry in entries:
            api.check_cancelled()
            size, count, modules = entry_totals(entry)
            total += size
            files += count
            submodules += modules
    return {
        "bytes": total, "MB": total / 1_000_000, "GB": total / 1_000_000_000,
        "files": files, "submodule_entries": submodules, "ref": sha,
        "scope": "Tracked file content on the captured default branch, including symlink blob bytes",
        "note": "Excludes .git/history, filesystem allocation, submodule repositories, release attachments and build/dependency files not tracked in Git. External Git LFS payloads are excluded; their tracked pointer bytes are included.",
    }
