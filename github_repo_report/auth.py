"""Reuse local GitHub credentials without printing or persisting tokens."""
from dataclasses import dataclass, field
import os
import subprocess

from .errors import Unavailable
from .processes import run_command
from .inputs import repository


@dataclass(frozen=True)
class Credentials:
    token: str | None = field(repr=False)
    source: str = "anonymous"


def clean_token(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    # Reject multiline/control-character output instead of putting it in a
    # header. Do not require a PAT prefix: OAuth/helper tokens can differ.
    return value if value and all(33 <= ord(c) <= 126 for c in value) else None


def command_output(command, *, env, input_text=None):
    """Capture secret output privately; missing tools and timeouts are normal."""
    try:
        options = dict(stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       text=True, encoding="utf-8", errors="replace",
                       timeout=5, check=False, env=env, shell=False)
        if input_text is None:
            options["stdin"] = subprocess.DEVNULL
        else:
            options["input"] = input_text
        result = run_command(command, **options)
        return result.stdout if result.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        # Exception strings/stderr can contain secrets. Never surface them.
        return None


def resolve_credentials(token=None, *, repo=None):
    """Explicit token (empty disables auth), env, gh, Git helper, anonymous.

    gh uses its active account for github.com. Git resolves host/path context
    through the user's configured HTTPS helpers; no credential stores are read
    directly, and no login, approve, reject, or logout command is run.
    """
    if token is not None:
        if token == "":
            return Credentials(None)
        cleaned = clean_token(token)
        if cleaned is None:
            raise Unavailable("Explicit authentication token has an invalid format")
        return Credentials(cleaned, "explicit token")

    for name in ("GITHUB_TOKEN", "GH_TOKEN"):
        if os.environ.get(name, "").strip():
            cleaned = clean_token(os.environ[name])
            if cleaned is None:
                raise Unavailable(f"{name} has an invalid token format")
            return Credentials(cleaned, name)

    env = os.environ.copy()
    # Disallow Git's terminal/askpass and GCM browser/GUI login flows. Custom
    # helpers are trusted user configuration and must honor these controls.
    env.update(GIT_TERMINAL_PROMPT="0", GIT_ASKPASS="", SSH_ASKPASS="",
               GCM_INTERACTIVE="Never", GH_PROMPT_DISABLED="1")
    # Do not let inherited diagnostic settings write credentials to trace logs.
    for name in list(env):
        if name.startswith("GIT_TRACE") or name in ("GH_DEBUG", "GCM_TRACE", "GCM_TRACE_SECRETS"):
            env.pop(name)

    value = command_output(["gh", "auth", "token", "--hostname", "github.com"], env=env)
    cleaned = clean_token(value)
    if cleaned:
        return Credentials(cleaned, "GitHub CLI")

    context = "protocol=https\nhost=github.com\n"
    if repo is not None:
        context += "path=" + repository(repo) + ".git\n"
    context += "\n"
    value = command_output([
        "git", "-c", "credential.interactive=false", "-c", "core.askPass=",
        "-c", "credential.trace=false", "-c", "credential.traceSecrets=false",
        "credential", "fill",
    ], env=env, input_text=context)
    if value:
        fields = {}
        for line in value.splitlines():
            key, separator, item = line.partition("=")
            if separator:
                fields[key] = item
        if fields.get("protocol") == "https" and fields.get("host", "").lower() == "github.com":
            cleaned = clean_token(fields.get("password"))
            if cleaned:
                return Credentials(cleaned, "Git HTTPS credential helper")
    return Credentials(None)
