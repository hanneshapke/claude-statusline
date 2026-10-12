#!/usr/bin/env python3
"""Single-line status bar for Claude Code.

Claude Code passes a JSON snapshot of the session on stdin. This script turns it
into one line of segments separated by "│". Each segment is a small function
that takes a `Session` and returns a string, or None to hide itself when the
data it needs is absent.

To customize: edit a segment function, or add/remove/reorder entries in
SEGMENTS at the bottom of the file. Changes apply on the next refresh.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any, Callable, Optional

# --------------------------------------------------------------------------
# Theme
# --------------------------------------------------------------------------


class C:
    """ANSI color and style codes."""

    RESET = "\033[0m"
    DIM = "\033[2m"
    BOLD = "\033[1m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    GREY = "\033[90m"


SEPARATOR = f" {C.GREY}│{C.RESET} "
BAR_WIDTH = 10
BAR_FILLED, BAR_EMPTY = "▓", "░"
WARN_PCT, DANGER_PCT = 65, 85  # thresholds for yellow / red
MAX_DIR_LEN = 40
MAX_SESSION_NAME_LEN = 30
GIT_TIMEOUT_S = 1.5


def paint(text: Any, *styles: str) -> str:
    """Wrap text in one or more ANSI styles and reset afterwards."""
    return "".join(styles) + str(text) + C.RESET


def dim(text: Any) -> str:
    return paint(text, C.DIM)


def level_color(pct: float) -> str:
    """Green / yellow / red depending on how close a percentage is to its limit."""
    if pct >= DANGER_PCT:
        return C.RED
    if pct >= WARN_PCT:
        return C.YELLOW
    return C.GREEN


# --------------------------------------------------------------------------
# Formatting helpers
# --------------------------------------------------------------------------


def fmt_tokens(n: float) -> str:
    """15500 -> '15.5k', 143500 -> '144k', 1200000 -> '1.2M'."""
    n = int(n)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 10_000:
        return f"{n / 1_000:.0f}k"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def fmt_duration(ms: float) -> str:
    """5025000 -> '1h23m', 317000 -> '5m17s', 4000 -> '4s'."""
    total = int(ms // 1000)
    hours, rem = divmod(total, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    if minutes:
        return f"{minutes}m{seconds:02d}s"
    return f"{seconds}s"


def truncate(text: str, limit: int, from_start: bool = False) -> str:
    if len(text) <= limit:
        return text
    return "…" + text[-(limit - 1):] if from_start else text[: limit - 1] + "…"


# --------------------------------------------------------------------------
# Session: safe access to the JSON Claude Code sends
# --------------------------------------------------------------------------


class Session:
    """Thin wrapper around the stdin JSON with null-safe dotted lookups.

    Every field Claude Code sends may be absent or null, so callers should
    always go through `get` / `num` rather than indexing the raw dict.
    """

    def __init__(self, data: dict):
        self.data = data if isinstance(data, dict) else {}

    @classmethod
    def from_stdin(cls) -> "Session":
        try:
            return cls(json.load(sys.stdin))
        except Exception:
            return cls({})

    def get(self, path: str, default: Any = None) -> Any:
        """session.get('context_window.current_usage.input_tokens')"""
        node: Any = self.data
        for key in path.split("."):
            if not isinstance(node, dict) or key not in node or node[key] is None:
                return default
            node = node[key]
        return node

    def num(self, path: str, default: float = 0.0) -> float:
        try:
            value = self.get(path)
            return float(value) if value is not None else default
        except (TypeError, ValueError):
            return default

    def has(self, path: str) -> bool:
        return self.get(path) is not None

    @property
    def cwd(self) -> str:
        return self.get("workspace.current_dir") or self.get("cwd") or os.getcwd()


# --------------------------------------------------------------------------
# Git
# --------------------------------------------------------------------------


def _git(cwd: str, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", cwd, *args],
        capture_output=True, text=True, timeout=GIT_TIMEOUT_S,
    )
    return result.stdout


def git_state(cwd: str) -> Optional[tuple[str, int, int]]:
    """Return (branch, staged_count, modified_count), or None outside a repo."""
    try:
        branch = _git(cwd, "rev-parse", "--abbrev-ref", "HEAD").strip()
        if not branch:
            return None
        lines = _git(cwd, "status", "--porcelain", "--untracked-files=no").splitlines()
        staged = sum(1 for l in lines if l[:1] not in (" ", "?"))
        modified = sum(1 for l in lines if l[1:2] not in (" ", "?"))
        return branch, staged, modified
    except Exception:
        return None


# --------------------------------------------------------------------------
# Segments. Each returns a string, or None to be skipped.
# --------------------------------------------------------------------------

Segment = Callable[[Session], Optional[str]]


def seg_model(s: Session) -> Optional[str]:
    """Model name, effort level, fast-mode flag."""
    name = s.get("model.display_name") or s.get("model.id") or "Claude"
    out = paint(name, C.MAGENTA, C.BOLD)
    if s.has("effort.level"):
        out += " " + dim(s.get("effort.level"))
    if s.get("fast_mode"):
        out += " " + paint("⚡", C.YELLOW)
    return out


def seg_directory(s: Session) -> Optional[str]:
    """Current directory with ~ for home, truncated from the left."""
    home = os.path.expanduser("~")
    path = s.cwd
    if path.startswith(home):
        path = "~" + path[len(home):]
    return paint(truncate(path, MAX_DIR_LEN, from_start=True), C.CYAN)


def seg_git(s: Session) -> Optional[str]:
    """Branch, staged/modified counts, worktree name."""
    state = git_state(s.cwd)
    if not state:
        return None
    branch, staged, modified = state
    out = paint(f"⎇ {branch}", C.BLUE)
    marker = ""
    if staged:
        marker += paint(f"+{staged}", C.GREEN)
    if modified:
        marker += paint(f"~{modified}", C.YELLOW)
    if marker:
        out += " " + marker
    worktree = s.get("worktree.name") or s.get("workspace.git_worktree")
    if worktree:
        out += " " + dim(f"[wt:{worktree}]")
    return out


def seg_pull_request(s: Session) -> Optional[str]:
    """Open PR / MR number, colored by review state."""
    number = s.get("pr.number")
    if not number:
        return None
    colors = {"approved": C.GREEN, "changes_requested": C.RED, "draft": C.GREY}
    color = colors.get(s.get("pr.review_state"), C.YELLOW)
    prefix = "!" if s.get("pr.kind") == "mr" else "#"
    return paint(f"PR {prefix}{number}", color)


def seg_session_name(s: Session) -> Optional[str]:
    name = s.get("session_name")
    return dim(truncate(name, MAX_SESSION_NAME_LEN)) if name else None


def seg_context(s: Session) -> Optional[str]:
    """Progress bar of context window usage."""
    size = s.num("context_window.context_window_size", 200_000)
    if s.has("context_window.used_percentage"):
        pct = s.num("context_window.used_percentage")
    else:
        pct = s.num("context_window.total_input_tokens") / size * 100 if size else 0
    filled = int(round(pct / (100 / BAR_WIDTH)))
    bar = BAR_FILLED * filled + BAR_EMPTY * (BAR_WIDTH - filled)
    return paint(f"{bar} {pct:.0f}%", level_color(pct)) + " " + dim(f"of {fmt_tokens(size)}")


def seg_tokens(s: Session) -> Optional[str]:
    """Input/output tokens in context and share served from cache."""
    tokens_in = s.num("context_window.total_input_tokens")
    tokens_out = s.num("context_window.total_output_tokens")
    out = f"{dim('in')} {fmt_tokens(tokens_in)} {dim('out')} {fmt_tokens(tokens_out)}"
    cache_read = s.num("context_window.current_usage.cache_read_input_tokens")
    if cache_read and tokens_in:
        out += f" {dim('cache')} {cache_read / tokens_in * 100:.0f}%"
    return out


def seg_cost(s: Session) -> Optional[str]:
    return paint(f"${s.num('cost.total_cost_usd'):.2f}", C.GREEN)


def seg_runtime(s: Session) -> Optional[str]:
    """Wall-clock session time and time spent waiting on the API."""
    wall = fmt_duration(s.num("cost.total_duration_ms"))
    api = fmt_duration(s.num("cost.total_api_duration_ms"))
    return f"{dim('⏱')} {wall} {dim('api')} {api}"


def seg_lines_changed(s: Session) -> Optional[str]:
    added = int(s.num("cost.total_lines_added"))
    removed = int(s.num("cost.total_lines_removed"))
    if not (added or removed):
        return None
    return f"{paint(f'+{added}', C.GREEN)} {paint(f'-{removed}', C.RED)}"


def seg_rate_limits(s: Session) -> Optional[str]:
    """5-hour / 7-day subscription limits and gateway spend limit."""
    parts = []
    for label, path in (("5h", "rate_limits.five_hour"), ("7d", "rate_limits.seven_day")):
        if s.has(f"{path}.used_percentage"):
            pct = s.num(f"{path}.used_percentage")
            parts.append(paint(f"{label} {pct:.0f}%", level_color(pct)))
    if s.has("rate_limits.spend_limit.used_percentage"):
        pct = s.num("rate_limits.spend_limit.used_percentage")
        text = paint(f"spend {pct:.0f}%", level_color(pct))
        if s.has("rate_limits.spend_limit.used_usd") and s.has("rate_limits.spend_limit.limit_usd"):
            used = s.num("rate_limits.spend_limit.used_usd")
            limit = s.num("rate_limits.spend_limit.limit_usd")
            text += " " + dim(f"(${used:.0f}/${limit:.0f})")
        parts.append(text)
    return " ".join(parts) if parts else None


def seg_prompt_cache(s: Session) -> Optional[str]:
    """Whether the prompt cache prefix is still warm."""
    if not s.has("prompt_cache"):
        return None
    warm = bool(s.get("prompt_cache.warm"))
    dot = paint("●", C.GREEN if warm else C.GREY)
    return f"{dot} {dim('cache warm' if warm else 'cache cold')}"


# Order here is display order. Remove or reorder entries to taste.
SEGMENTS: list[Segment] = [
    seg_model,
    seg_directory,
    seg_git,
    seg_pull_request,
    seg_session_name,
    seg_context,
    seg_tokens,
    seg_cost,
    seg_runtime,
    seg_lines_changed,
    seg_rate_limits,
    seg_prompt_cache,
]


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def render(session: Session, segments: list[Segment] = SEGMENTS) -> str:
    rendered = []
    for segment in segments:
        try:
            text = segment(session)
        except Exception:
            text = None  # one broken segment must never blank the whole bar
        if text:
            rendered.append(text)
    return SEPARATOR.join(rendered)


def main() -> None:
    sys.stdout.write(render(Session.from_stdin()) + "\n")


if __name__ == "__main__":
    main()
