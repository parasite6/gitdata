"""GitHub-flavored Markdown reports, with untrusted repository text escaped."""
import html
import re

from .models import Report
from .ordering import ordered_report, DETAIL_FIELDS
from .rendering import LABELS, safe_text


def escape(value):
    text = html.escape(safe_text(value), quote=False)
    text = re.sub(r"([\\`*_{}\[\]()#+.!|~-])", r"\\\1", text)
    return text.replace("\r\n", "\n").replace("\n", "<br>")


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
    return str(value)


def format_markdown(report: Report) -> str:
    """Summary table plus detailed sections; all fields and evidence survive."""
    output = ["# GitHub repository report", ""]
    rows, sections = [], []
    for key, entry in ordered_report(report).items():
        value = entry.get("value", entry)
        if key in DETAIL_FIELDS:
            sections.append((key, entry))
        elif "unavailable" in entry:
            rows.append((label(key), "Unavailable: " + entry["unavailable"]))
        elif isinstance(value, (dict, list)):
            sections.append((key, entry))
        else:
            rows.append((label(key), scalar(value)))

    if rows:
        output.extend(["| Field | Value |", "| --- | --- |"])
        output.extend(f"| {escape(name)} | {escape(value)} |" for name, value in rows)
        output.append("")

    def render(value, indent=""):
        if isinstance(value, dict):
            for key, item in value.items():
                if isinstance(item, (dict, list)) and item:
                    output.append(f"{indent}- **{escape(label(key))}:**")
                    render(item, indent + "    ")
                else:
                    text = "None reported" if isinstance(item, (dict, list)) else scalar(item)
                    output.append(f"{indent}- **{escape(label(key))}:** {escape(text)}")
        elif isinstance(value, list):
            for n, item in enumerate(value, 1):
                if isinstance(item, (dict, list)):
                    output.append(f"{indent}- **Item {n}:**")
                    render(item, indent + "    ")
                else:
                    output.append(f"{indent}- {escape(scalar(item))}")

    for key, entry in sections:
        output.extend([f"## {escape(label(key))}", ""])
        value = entry.get("value", entry)
        if "unavailable" in entry:
            output.append(escape("Unavailable: " + entry["unavailable"]))
        elif key == "readme_first_20_lines":
            text = "\n".join(safe_text(line) for line in value)
            # A fence longer than every README backtick run prevents README
            # contents from closing the block and changing the report layout.
            longest = max((len(m.group()) for m in re.finditer(r"`+", text)), default=0)
            fence = "`" * max(3, longest + 1)
            output.extend([fence + "text", text or "(empty README)", fence])
        elif key == "languages" and value:
            output.extend(["| Language | Percentage | Code bytes |", "| --- | ---: | ---: |"])
            output.extend(f"| {escape(name)} | {data['percent']:.2f}% | {data['bytes']:,} |"
                          for name, data in value.items())
        elif key == "supported_platforms":
            output.append("**Platforms:** " + escape(
                ", ".join(value) or "Unknown (no matching evidence)"))
            output.append("")
            render({k: v for k, v in entry.items() if k != "value"})
        elif value:
            render(value)
        else:
            output.append("None reported.")
        output.append("")
    return "\n".join(output).rstrip()
