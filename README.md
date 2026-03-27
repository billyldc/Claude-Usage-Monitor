# Claude Usage Monitor - Alfred Workflow

An Alfred workflow to quickly check your Claude (claude.ai) account usage, including 5-hour / 7-day limits, per-model breakdown, and real-time service status.

## Features

- **5-Hour / 7-Day usage** with progress bars and reset timers
- **Per-model breakdown**: Opus, Sonnet, OAuth Apps weekly usage
- **Live service status** from [status.claude.com](https://status.claude.com) with active incident details
- **Multi-auth fallback**: Session Key → OAuth Token → Keychain → credentials file
- **Bilingual UI**: Chinese / English switchable in settings
- **Smart caching**: 60s usage cache, 2min status cache, stale-cache fallback on rate limits

## Installation

1. Download [`Claude-Usage-Monitor.alfredworkflow`](https://github.com/billyldc/Claude-Usage-Monitor/releases/latest)
2. Double-click to install in Alfred
3. Configure authentication (see below)

## Authentication

The workflow supports multiple auth methods (in priority order):

### 1. Session Key (Recommended - most stable)

Session keys from the browser last much longer than OAuth tokens.

1. Open [claude.ai](https://claude.ai) and log in
2. Open the **EditThisCookie** browser extension (or DevTools → Application → Cookies)
3. Find the `sessionKey` cookie (starts with `sk-ant-sid...`)
4. Paste it into the **Session Key** field in the workflow configuration

Alternatively, save it to `~/.claude-session-key`:
```bash
echo "sk-ant-sid..." > ~/.claude-session-key
chmod 600 ~/.claude-session-key
```

### 2. OAuth Token (Fallback)

- **Auto-detect**: If you've run `claude auth login` (Claude Code CLI), the token is read from macOS Keychain automatically.
- **Manual**: Paste your OAuth token in the workflow configuration.

### 3. Credentials File

The workflow also reads from `~/.claude/.credentials.json` as a last resort.

## Usage

Type `claude` in Alfred to see:

| Item | Description |
|------|-------------|
| 5-Hour Usage | Rolling 5-hour utilization with reset timer |
| 7-Day Usage | Weekly utilization with reset timer |
| Model Usage | Opus / Sonnet / OAuth Apps weekly breakdown |
| Service Status | Live status from status.claude.com |

- **Enter** on usage rows → opens [claude.ai/settings/usage](https://claude.ai/settings/usage)
- **Enter** on status row → opens [status.claude.com](https://status.claude.com)
- **Cmd+Enter** on status row → copies raw JSON to clipboard

## Settings

Open the workflow configuration in Alfred to set:

| Setting | Description |
|---------|-------------|
| **Language** | `中文` or `English` |
| **Session Key** | Browser sessionKey cookie (recommended) |
| **OAuth Token** | Manual OAuth token (fallback) |

## Requirements

- macOS
- [Alfred 5](https://www.alfredapp.com/) with Powerpack
- Python 3 (built-in on macOS)

## License

MIT
