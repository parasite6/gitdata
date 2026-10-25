"""Pure text formatting; callers decide where to write the result."""
import json
import textwrap

from .models import Report
from .ordering import ordered_report


LABELS = {
    "default_branch_head": "Default branch SHA",
    "owner": "Repo owner",
    "commits_reachable_from_default_branch_head": "Commits (default branch)",
    "license_detected_by_github": "License (GitHub detection)",
    "release_count_visible_to_caller": "Releases (visible to caller)",
    "readme_first_20_lines": "README (first 20 lines)",
    "pr_open": "Open PRs",
    "pr_total": "Total PRs",
    "pr_merged": "Merged PRs",
    "pr_closed_including_merged": "Closed PRs (including merged)",
    "pr_closed_unmerged": "Closed PRs (unmerged)",
    "issues_open": "Open issues",
    "issues_closed": "Closed issues",
    "issues_total": "Total issues",
    "supported_platforms": "Supported platforms (inferred)",
    "repository_contents_size": "Repository contents size",
    "total_api_entries": "Total contributor entries",
    "html_url": "Web URL",
    "ssh_url": "SSH URL",
    "clone_url": "Clone URL",
    "url": "API URL",
    "MB": "MB", "GB": "GB", "top_10": "Top 10",
}


def safe_text(value):
    """Escape terminal controls while preserving ordinary Unicode and newlines."""
    return "".join(c if c in "\n\t" or c.isprintable()
                   else f"\\x{ord(c):02x}" for c in str(value))


def format_plain(report: Report) -> str:
    """Readable labels and nested lists; every report field remains available."""
    output = []

    def label(key):
        return LABELS.get(key, key.replace("_", " ").capitalize())

    def scalar(value):
        if value is None:
            return "Not reported"
        if isinstance(value, bool):
            return "Yes" if value else "No"
        if isinstance(value, int):
            return f"{value:,}"
        if isinstance(value, float):
            return f"{value:,.6g}"
        return safe_text(value)

    def render(value, indent=""):
        if isinstance(value, dict):
            for key, item in value.items():
                if isinstance(item, (dict, list)) and item:
                    output.append(f"{indent}{label(key)}:")
                    render(item, indent + "  ")
                else:
                    output.append(f"{indent}{label(key)}: {scalar(item) if not isinstance(item, (dict, list)) else '(none reported)'}")
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, (dict, list)):
                    output.append(indent + "-")
                    render(item, indent + "  ")
                else:
                    output.append(indent + "- " + scalar(item))
        else:
            output.extend(indent + line for line in scalar(value).splitlines())

    for key, entry in ordered_report(report).items():
        title = label(key)
        if "unavailable" in entry:
            output.append(f"{title}: Unavailable ({safe_text(entry['unavailable'])})")
        elif key == "languages" and entry.get("value"):
            output.append(title + ":")
            for language, data in entry["value"].items():
                output.append(f"  {safe_text(language)}: {data['percent']:.2f}% ({data['bytes']:,} bytes)")
        elif key == "readme_first_20_lines" and isinstance(entry.get("value"), list):
            output.append(title + ":")
            output.extend("  " + safe_text(line) for line in entry["value"])
            if not entry["value"]:
                output.append("  (empty README)")
        elif key == "supported_platforms":
            output.append(f"{title}: {', '.join(entry['value']) or 'Unknown (no matching evidence)'}")
            render({k: v for k, v in entry.items() if k != "value"}, "  ")
        else:
            value = entry.get("value", entry)
            if isinstance(value, (dict, list)):
                output.append(title + ":")
                render(value, "  ")
                if not value:
                    output.append("  (none reported)")
            else:
                output.append(f"{title}: {scalar(value)}")
        output.append("")
    return "\n".join(output).rstrip()


def format_table(report: Report) -> str:
    output = []
    width = 88
    display_labels = {key: LABELS[key] if key in ("owner", "repository_contents_size") else key for key in report}
    label_width = max(map(len, display_labels.values()))
    output.append(f"{'Field':{label_width}} | Value")
    output.append("-" * (label_width + 1) + "+" + "-" * (width + 2))
    for key, entry in ordered_report(report).items():
        value = entry.get("value", entry)
        if "unavailable" in entry:
            value = "Unavailable: " + entry["unavailable"]
        if key == "readme_first_20_lines" and isinstance(value, list):
            text = "\n".join(value) or "(empty README)"
        else:
            text = json.dumps(entry if key == "supported_platforms" else value,
                              ensure_ascii=True)
        # Neutralize terminal escape/control characters in untrusted content.
        text = "".join(c if c in "\n\t" or c.isprintable()
                       else f"\\x{ord(c):02x}" for c in text)
        lines = [part for line in text.splitlines()
                 for part in (textwrap.wrap(line.expandtabs(4), width=width) or [""])]
        for i, line in enumerate(lines):
            display_key = display_labels[key]
            output.append(f"{display_key if i == 0 else '':{label_width}} | {line}")
    return "\n".join(output)
