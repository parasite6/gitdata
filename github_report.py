#!/usr/bin/env python3
"""Compatibility entry point: python github_report.py owner/repo."""
from github_repo_report.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
