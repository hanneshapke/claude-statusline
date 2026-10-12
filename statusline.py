#!/usr/bin/env python3
"""Claude Code status line: model · dir · git · context bar · tokens · cost · runtime · limits.

Reads the session JSON Claude Code passes on stdin and prints one line.
Every field is optional, so each segment degrades gracefully when data is absent.
"""
import json
import os
import subprocess
import sys

# ---- colors (ANSI) ---------------------------------------------------------
R = "\033[0m"
DIM = "\033[2m"
BOLD = "\033[1m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
GREY = "\033[90m"
SEP = f" {GREY}│{R} "


def num(x, default=0.0):
    try:
        return float(x) if x is not None else default
    except (TypeError, ValueError):
        return default


def fmt_tokens(n):
    n = int(n)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}k" if n >= 10_000 else f"{n / 1_000:.1f}k"
    return str(n)


def fmt_duration(ms):
    s = int(ms // 1000)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m"
    if m:
        return f"{m}m{s:02d}s"
    return f"{s}s"


def pct_color(p):
    if p >= 85:
        return RED
    if p >= 65:
        return YELLOW
    return GREEN


def git_info(cwd):
    """Return (branch, dirty_marker) or (None, '') when not in a git repo."""
    try:
        branch = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=1.5,
        ).stdout.strip()
        if not branch:
            return None, ""
        status = subprocess.run(
            ["git", "-C", cwd, "status", "--porcelain", "--untracked-files=no"],
            capture_output=True, text=True, timeout=1.5,
        ).stdout
        staged = sum(1 for l in status.splitlines() if l[:1] not in (" ", "?"))
        modified = sum(1 for l in status.splitlines() if l[1:2] not in (" ", "?"))
        marker = ""
        if staged:
            marker += f"{GREEN}+{staged}{R}"
        if modified:
            marker += f"{YELLOW}~{modified}{R}"
        return branch, marker
    except Exception:
        return None, ""


def main():
    try:
        d = json.load(sys.stdin)
    except Exception:
        d = {}

    model = d.get("model") or {}
    ws = d.get("workspace") or {}
    cost = d.get("cost") or {}
    ctx = d.get("context_window") or {}
    usage = ctx.get("current_usage") or {}
    limits = d.get("rate_limits") or {}
    cache = d.get("prompt_cache") or {}
    pr = d.get("pr") or {}

    cwd = ws.get("current_dir") or d.get("cwd") or os.getcwd()

    # ---------------- line 1: identity ----------------
    parts1 = []

    name = model.get("display_name") or model.get("id") or "Claude"
    effort = (d.get("effort") or {}).get("level")
    model_seg = f"{MAGENTA}{BOLD}{name}{R}"
    if effort:
        model_seg += f" {DIM}{effort}{R}"
    if d.get("fast_mode"):
        model_seg += f" {YELLOW}⚡{R}"
    parts1.append(model_seg)

    home = os.path.expanduser("~")
    short = cwd.replace(home, "~", 1) if cwd.startswith(home) else cwd
    if len(short) > 40:
        short = "…" + short[-39:]
    parts1.append(f"{CYAN}{short}{R}")

    branch, marker = git_info(cwd)
    if branch:
        seg = f"{BLUE}⎇ {branch}{R}"
        if marker:
            seg += " " + marker
        wt = (d.get("worktree") or {}).get("name") or ws.get("git_worktree")
        if wt:
            seg += f" {DIM}[wt:{wt}]{R}"
        parts1.append(seg)

    if pr.get("number"):
        state = pr.get("review_state")
        col = {"approved": GREEN, "changes_requested": RED, "draft": GREY}.get(state, YELLOW)
        kind = "!" if pr.get("kind") == "mr" else "#"
        parts1.append(f"{col}PR {kind}{pr['number']}{R}")

    if d.get("session_name"):
        sn = d["session_name"]
        if len(sn) > 30:
            sn = sn[:29] + "…"
        parts1.append(f"{DIM}{sn}{R}")

    # ---------------- line 2: metrics ----------------
    parts2 = []

    size = num(ctx.get("context_window_size"), 200_000)
    used_pct = ctx.get("used_percentage")
    if used_pct is None:
        tin = num(ctx.get("total_input_tokens"))
        used_pct = tin / size * 100 if size else 0
    used_pct = num(used_pct)
    filled = int(round(used_pct / 10))
    bar = "▓" * filled + "░" * (10 - filled)
    col = pct_color(used_pct)
    parts2.append(f"{col}{bar} {used_pct:.0f}%{R} {DIM}of {fmt_tokens(size)}{R}")

    tin = num(ctx.get("total_input_tokens"))
    tout = num(ctx.get("total_output_tokens"))
    tok = f"{DIM}in{R} {fmt_tokens(tin)} {DIM}out{R} {fmt_tokens(tout)}"
    cache_read = num(usage.get("cache_read_input_tokens"))
    if cache_read and tin:
        tok += f" {DIM}cache{R} {cache_read / tin * 100:.0f}%"
    parts2.append(tok)

    usd = num(cost.get("total_cost_usd"))
    parts2.append(f"{GREEN}${usd:.2f}{R}")

    dur = num(cost.get("total_duration_ms"))
    api = num(cost.get("total_api_duration_ms"))
    parts2.append(f"{DIM}⏱{R} {fmt_duration(dur)} {DIM}api{R} {fmt_duration(api)}")

    added = int(num(cost.get("total_lines_added")))
    removed = int(num(cost.get("total_lines_removed")))
    if added or removed:
        parts2.append(f"{GREEN}+{added}{R} {RED}-{removed}{R}")

    lim_parts = []
    fh = (limits.get("five_hour") or {}).get("used_percentage")
    sd = (limits.get("seven_day") or {}).get("used_percentage")
    if fh is not None:
        lim_parts.append(f"{pct_color(num(fh))}5h {num(fh):.0f}%{R}")
    if sd is not None:
        lim_parts.append(f"{pct_color(num(sd))}7d {num(sd):.0f}%{R}")
    sp = limits.get("spend_limit") or {}
    if sp.get("used_percentage") is not None:
        s = f"{pct_color(num(sp['used_percentage']))}spend {num(sp['used_percentage']):.0f}%{R}"
        if sp.get("used_usd") is not None and sp.get("limit_usd") is not None:
            s += f" {DIM}(${num(sp['used_usd']):.0f}/${num(sp['limit_usd']):.0f}){R}"
        lim_parts.append(s)
    if lim_parts:
        parts2.append(" ".join(lim_parts))

    if cache:
        warm = cache.get("warm")
        parts2.append(f"{GREEN if warm else GREY}●{R} {DIM}cache {'warm' if warm else 'cold'}{R}")

    sys.stdout.write(SEP.join(parts1 + parts2) + "\n")


if __name__ == "__main__":
    main()
