# Claude Code status line

A single-line status bar for [Claude Code](https://code.claude.com) showing model, directory, git state, context usage, tokens, cost, runtime and rate limits.

```
Fable 5.1 high │ ~/projects/myapp │ ⎇ main +1~2 │ PR #42 │ ▓▓▓▓▓▓▓░░░ 72% of 200k │ in 144k out 4.2k cache 91% │ $3.46 │ ⏱ 1h23m api 13m32s │ +156 -23 │ 5h 24% 7d 88% │ ● cache warm
```

Segments, left to right:

| Segment | Meaning |
| - | - |
| `Fable 5.1 high` | Model and effort level. `⚡` appears when fast mode is on. |
| `~/projects/myapp` | Current directory. |
| `⎇ main +1~2` | Git branch, staged (`+`) and modified (`~`) file counts, worktree name if any. |
| `PR #42` | Open PR for the branch, colored by review state. |
| `▓▓▓▓▓▓▓░░░ 72% of 200k` | Context window used. Green, yellow above 65%, red above 85%. |
| `in 144k out 4.2k cache 91%` | Tokens in the context window and the share served from prompt cache. |
| `$3.46` | Estimated session cost. |
| `⏱ 1h23m api 13m32s` | Session runtime and time spent waiting on the API. |
| `+156 -23` | Lines added and removed this session. |
| `5h 24% 7d 88%` | 5-hour and 7-day rate limit usage (Pro/Max subscribers). |
| `● cache warm` | Whether the prompt cache is still warm. |

Segments only appear when Claude Code provides the data.

## Install

Requires Python 3 and git. No other dependencies.

```sh
curl -fsSL https://raw.githubusercontent.com/hanneshapke/claude-statusline/main/install.sh | bash
```

Or manually:

1. Copy `statusline.py` to `~/.claude/statusline.py` and `chmod +x` it.
2. Add to `~/.claude/settings.json`:

```json
"statusLine": {
  "type": "command",
  "command": "python3 /Users/you/.claude/statusline.py",
  "padding": 0,
  "refreshInterval": 30
}
```

The installer backs up your existing `settings.json` to `settings.json.bak.pre-statusline`.

## Customize

Edit `~/.claude/statusline.py`. Each segment is a few lines appending to `parts1` or `parts2`; delete the ones you don't want. Changes apply on the next refresh without restarting Claude Code.
