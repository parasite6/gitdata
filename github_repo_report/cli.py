"""Argument parsing, user-facing progress, output and process exit codes."""
import argparse
import json
import math
import os
import sys

from .api import API
from .errors import Cancelled, Unavailable
from .inputs import repository
from .models import ProgressEvent, is_partial
from .markdown import format_markdown
from .output import write_report
from .progress import TerminalProgress
from .rendering import format_plain, format_table
from .report import REPORT_TASKS, build_report


def print_report(text):
    # Preserve Unicode on capable streams; escape unrepresentable characters
    # before writing so legacy encodings cannot fail halfway through a report.
    encoding = getattr(sys.stdout, "encoding", None)
    if encoding:
        text = text.encode(encoding, errors="backslashreplace").decode(encoding)
    print(text)
    sys.stdout.flush()


def main(argv=None):
    parser = argparse.ArgumentParser(prog="gitdata", description="Report on a GitHub repository.")
    parser.add_argument("repo", nargs="?", type=repository,
                        help="Repository name or URL (alternative to -repo)")
    parser.add_argument("-repo", "--repo", dest="repo_option", type=repository,
                        metavar="OWNER/REPO", help="Repository name or URL")
    formats = parser.add_mutually_exclusive_group()
    formats.add_argument("--json", action="store_true", help="Machine-readable JSON")
    formats.add_argument("--plain", action="store_true", help="Readable text without a table")
    formats.add_argument("--md", action="store_true", help="Markdown report")
    parser.add_argument("-o", "--output", metavar="FILE",
                        help="Write the selected format to a UTF-8 file")
    parser.add_argument("--workers", type=int, choices=range(1, 9), default=4,
                        metavar="1-8", help="Concurrent collectors (default: 4; 1 for serial)")
    parser.add_argument("--max-wait", type=float, default=60,
                        help="Total retry wait budget in seconds (default: 60)")
    parser.add_argument("--verbose", action="store_true",
                        help="Show field and request progress on stderr")
    parser.add_argument("--no-auth", action="store_true",
                        help="Use public access without checking environment or local credentials")
    parser.add_argument("--no-progress", action="store_true",
                        help="Hide the terminal progress bar")
    args = parser.parse_args(argv)
    if args.repo is not None and args.repo_option is not None:
        parser.error("Specify the repository once, using -repo or a positional argument")
    repo = args.repo_option if args.repo_option is not None else args.repo
    if repo is None:
        parser.print_help()
        return 0
    if not math.isfinite(args.max_wait) or args.max_wait < 0:
        parser.error("--max-wait must be finite and nonnegative")

    bar = TerminalProgress(("authenticate", *REPORT_TASKS, "render", "deliver"),
                           enabled=False if args.no_progress else None)

    def progress(event: ProgressEvent):
        bar.handle(event)
        if (args.verbose and event.phase in ("auth", "field", "request", "retry")) or (
                event.phase == "retry" and not bar.enabled):
            bar.log(event.message)

    bar.start()
    try:
        with API(args.max_wait, on_progress=progress, workers=args.workers,
                 token="" if args.no_auth else None, credential_repo=repo) as api:
            api.progress("auth", "Authentication: " + api.auth_source)
            bar.complete("authenticate")
            report = build_report(api, repo)
        bar.set_activity("Formatting report")
        if args.json:
            text = json.dumps(report, indent=2, ensure_ascii=True)
        elif args.plain:
            text = format_plain(report)
        elif args.md:
            text = format_markdown(report)
        else:
            text = format_table(report)
        bar.complete("render")
        bar.set_activity("Writing report" if args.output else "Printing report")
        if args.output:
            try:
                write_report(args.output, text)
            except OSError as e:
                bar.finish("Failed to write report")
                print(f"Cannot write report to {args.output}: {e}", file=sys.stderr)
                return 1
        else:
            bar.suspend()
            print_report(text)
        bar.complete("deliver")
        partial = is_partial(report)
        bar.finish("Done (partial report)" if partial else "Done")
        return 2 if partial else 0
    except BrokenPipeError:
        bar.finish("Output closed")
        # Prevent a second BrokenPipeError during interpreter shutdown.
        try:
            sys.stdout = open(os.devnull, "w")
        except OSError:
            pass
        return 1
    except (OSError, UnicodeError) as e:
        bar.finish("Output failed")
        print(f"Cannot write report: {type(e).__name__}", file=sys.stderr)
        return 1
    except Unavailable as e:
        bar.finish("Failed")
        if args.json and not args.output:
            print(json.dumps({"error": str(e)}))
        else:
            print(f"Error: {e}", file=sys.stderr)
        return 1
    except (KeyboardInterrupt, Cancelled):
        bar.finish("Cancelled")
        print("Interrupted", file=sys.stderr)
        return 130
    finally:
        bar.finish("Failed")  # No-op after a normal finish; closes on unexpected errors.
