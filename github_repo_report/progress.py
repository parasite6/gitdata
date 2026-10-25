"""A small stderr-only terminal display; percentages count completed checks."""
import math
import os
import shutil
import sys
from threading import Event, RLock, Thread, get_ident
import time

from .rendering import LABELS, safe_text


ACTIVITIES = {
    "repository_metadata": "Repository", "default_branch_head": "Default branch",
    "commits_reachable_from_default_branch_head": "Commits", "pr_merged": "Merged PRs",
    "mixed_issues_open": "Open issues", "mixed_issues_total": "Total issues",
    "workflows": "CI workflows", "release_assets": "Release assets",
    "readme_first_20_lines": "README", "release_count_visible_to_caller": "Releases",
}


class TerminalProgress:
    def __init__(self, tasks, *, stream=None, enabled=None):
        self.stream = sys.stderr if stream is None else stream
        tty = bool(getattr(self.stream, "isatty", lambda: False)())
        self.enabled = (tty and os.environ.get("TERM") != "dumb") if enabled is None else enabled
        self.tasks = frozenset(tasks)
        self.completed = set()
        self.lock = RLock()
        self.stop = Event()
        self.thread = None
        self.started_at = time.monotonic()
        self.finished = False
        self.suspended = False
        self.width = 0
        self.displayed = 0.0
        self.last_frame_at = self.started_at
        self.activity = "Authenticating"
        self.active = {}
        self.pages = {}
        self.retry_until = 0
        self.color = self.enabled and "NO_COLOR" not in os.environ and os.environ.get("CLICOLOR") != "0"
        if os.name == "nt" and not any(os.environ.get(k) for k in ("WT_SESSION", "ANSICON", "TERM")):
            self.color = False
        try:
            "━╸─".encode(getattr(self.stream, "encoding", None) or "utf-8")
            self.unicode = True
        except UnicodeEncodeError:
            self.unicode = False
        self.spinner_frames = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        try:
            self.spinner_frames.encode(getattr(self.stream, "encoding", None) or "utf-8")
        except UnicodeEncodeError:
            self.spinner_frames = "/--\\--"

    @property
    def percent(self):
        actual = 100 * len(self.completed) // len(self.tasks) if self.tasks else 0
        # Output delivery must have finished, and finish() must be called,
        # before the terminal can display 100%.
        return min(actual, 100 if self.finished else 99)

    def start(self):
        if not self.enabled:
            return
        with self.lock:
            self._draw()
        self.thread = Thread(target=self._animate, name="gitdata-progress", daemon=True)
        self.thread.start()

    def _animate(self):
        while not self.stop.wait(1 / 60):
            with self.lock:
                if self.enabled and not self.suspended:
                    self._draw()

    def set_activity(self, text):
        with self.lock:
            self.activity = text

    def complete(self, task):
        with self.lock:
            if task in self.tasks:
                self.completed.add(task)

    def handle(self, event):
        if not self.enabled and event.phase != "task_done":
            return
        with self.lock:
            if event.phase == "task_done":
                self.complete(event.message)
                self.active.pop(get_ident(), None)
                self.activity = next(reversed(self.active.values()), "Finalizing")
            elif event.phase == "field":
                key = event.message.lstrip("_")
                name = ACTIVITIES.get(key, LABELS.get(key, key.replace("_", " ").capitalize()))
                self.active[get_ident()] = name
                self.activity = name
            elif event.phase == "page":
                name = self.active.get(get_ident(), "Fetching records")
                suffix = f"{event.completed}/{event.total}" if event.total is not None else str(event.completed)
                self.pages[name] = suffix + " pages"
                self.activity = name
            elif event.phase == "request":
                self.activity = self.active.get(get_ident(), self.activity)
            elif event.phase == "retry":
                self.retry_until = max(self.retry_until, time.monotonic() + (event.retry_seconds or 0))

    def suspend(self):
        """Keep redraws away from a report being written to the same terminal."""
        with self.lock:
            self.suspended = True
            self._clear()

    def log(self, message):
        with self.lock:
            self._clear()
            print(safe_text(message), file=self.stream)
            if self.enabled and not self.suspended:
                self._draw()

    def _clear(self):
        if self.enabled and self.width:
            self._write("\r" + " " * self.width + "\r")
            self.width = 0

    def _write(self, text):
        try:
            self.stream.write(text)
            self.stream.flush()
        except (OSError, ValueError):
            self.enabled = False
            self.stop.set()

    def _advance(self, now):
        # Only interpolate toward earned progress, never predict future work.
        # A short exponential response absorbs simultaneous task completions.
        elapsed = min(0.05, max(0, now - self.last_frame_at))
        self.last_frame_at = now
        self.displayed += max(0, self.percent - self.displayed) * (1 - math.exp(-elapsed / 0.12))
        if 0 <= self.percent - self.displayed < 0.05:
            self.displayed = float(self.percent)

    def _draw(self, status=None, *, advance=True):
        if not self.enabled:
            return
        columns = shutil.get_terminal_size(fallback=(80, 24)).columns
        if advance:
            self._advance(time.monotonic())
        percentage = min(self.percent, int(self.displayed))
        bar_width = 16 if columns >= 70 else 10
        filled = bar_width * percentage // 100
        solid, head, empty = ("━", "╸", "─") if self.unicode else ("=", ">", "-")
        bar = solid * filled
        if filled < bar_width:
            bar += head + empty * (bar_width - filled - 1)
        elapsed = time.monotonic() - self.started_at
        if status is not None:
            activity = status
        elif self.retry_until > time.monotonic():
            activity = f"Retrying in {math.ceil(self.retry_until - time.monotonic())}s"
        else:
            activity = self.activity
            if activity in self.pages:
                activity += (" · " if self.unicode else " / ") + self.pages[activity]
        activity = safe_text(activity).replace("\n", " ").replace("\t", " ")
        # Keep the spinner at a readable 80 ms cadence independently of the
        # smoother 60 Hz bar redraws. No vertical-bar ASCII frame.
        spinner = " " if status else self.spinner_frames[int(elapsed / 0.08) % len(self.spinner_frames)]
        prefix = f"gitdata {spinner} [{bar}] {percentage:3d}% {len(self.completed)}/{len(self.tasks)} checks {elapsed:.1f}s"
        if columns < 55:
            prefix = f"gitdata [{bar}] {percentage:3d}%"
        available = max(0, columns - len(prefix) - 3)
        text = (prefix + "  " + activity[:available])[:max(1, columns - 1)]
        if columns < 36:
            text = f"gitdata {percentage:3d}%"[:max(1, columns - 1)]
        padding = " " * max(0, self.width - len(text))
        if self.color:
            growing = solid * filled + (head if filled < bar_width else "")
            remaining = empty * max(0, bar_width - len(growing))
            colored_bar = "\x1b[38;5;208m" + growing + "\x1b[90m" + remaining + "\x1b[0m"
            styled = text.replace("[" + bar + "]", "[" + colored_bar + "]", 1)
        else:
            styled = text
        self._write("\r" + styled + padding)
        self.width = len(text)

    def finish(self, status="Done"):
        self.stop.set()
        if self.thread is not None:
            self.thread.join()
        with self.lock:
            if self.finished:
                return
            self.suspended = False
            # Finish a short transition below 100, then show 100 exactly once.
            # Delivery has already completed. No pause is added at 100%, and
            # failed/cancelled work never animates toward unearned completion.
            complete = bool(self.tasks) and self.completed == self.tasks
            if self.enabled and complete:
                start = self.displayed
                began = time.monotonic()
                duration = 0.24 * min(1, max(0, 99 - start) / 12)
                tick = Event()
                while True:
                    fraction = min(1.0, (time.monotonic() - began) / duration) if duration else 1.0
                    eased = fraction * fraction * (3 - 2 * fraction)
                    self.displayed = start + (99 - start) * eased
                    self._draw(advance=False)
                    if fraction >= 1 or not self.enabled:
                        break
                    tick.wait(1 / 60)
            self.finished = True
            if self.enabled:
                if complete:
                    self.displayed = 100.0
                self._draw(status, advance=False)
                self._write("\n")
