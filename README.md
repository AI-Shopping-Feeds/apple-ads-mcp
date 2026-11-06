# Apple Ads MCP Server (read + write)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE) [![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/downloads/)

An [MCP](https://modelcontextprotocol.io) server for [Apple Ads](https://ads.apple.com),
built on the [Apple Ads Platform API](https://developer.apple.com/documentation/apple-ads-platform-api)
v1. Use it from Claude, ChatGPT, Cursor, Codex or any MCP client to report on App
Store and Apple Maps campaigns, find search terms, keyword ideas and impression
share, and change budgets, bids, keywords and ads.

Maintained by [AI Shopping Feeds](https://github.com/AI-Shopping-Feeds). It offers:

- **nearly every Platform API v1 endpoint**: campaigns, ad groups, keywords and negative keywords, ads and creatives, reports, impression share, search term popularity, recommendations, budget orders, Apple Maps and change history
- **spend safety**: dry-run, confirm words for deletes and bulk changes, a limit on budget and bid rises, paused new campaigns and an audit log
- **every other endpoint** through a generic `apple_ads_request` tool
- **the current API**: Apple switches off the older Campaign Management API v5 on 26 January 2027

Not affiliated with or endorsed by Apple.

Part of the AI Shopping Feeds MCP family: [Google Ads](https://github.com/AI-Shopping-Feeds/google-ads-mcp) · [Google Merchant Centre](https://github.com/AI-Shopping-Feeds/google-merchant-centre-mcp) · [Google Analytics](https://github.com/AI-Shopping-Feeds/google-analytics-mcp) · [YouTube Studio](https://github.com/AI-Shopping-Feeds/youtube-studio-mcp) · [Amazon Ads](https://github.com/AI-Shopping-Feeds/amazon-ads-mcp) · **Apple Ads** · [Microsoft Ads](https://github.com/AI-Shopping-Feeds/microsoft-ads-mcp) · [TikTok Ads](https://github.com/AI-Shopping-Feeds/tiktok-ads-mcp) · [Pinterest Ads](https://github.com/AI-Shopping-Feeds/pinterest-ads-mcp) · [Snapchat Ads](https://github.com/AI-Shopping-Feeds/snapchat-ads-mcp) · [OpenAI Ads](https://github.com/AI-Shopping-Feeds/openai-ads-mcp) · [AppLovin](https://github.com/AI-Shopping-Feeds/applovin-mcp).

## Let your agent set it up

Paste this into Claude Code, Codex, Cursor or any agent that can read web pages and edit files:

```text
Set up the Apple Ads MCP server for me by following https://raw.githubusercontent.com/AI-Shopping-Feeds/apple-ads-mcp/main/skills/apple-ads-mcp/SKILL.md
```

The agent checks whether it's already connected, installs the runner if you
agree, walks you through the Apple Ads API user, key pair and IDs, adds the server to your
client's config without touching your other servers, and checks it works by
calling `apple_ads_health_check`.

The same file is an [Agent Skill](https://agentskills.io), so your agent can keep it as a guide to using the tools well. For Claude Code, copy the folder into your skills:

```bash
git clone --depth 1 https://github.com/AI-Shopping-Feeds/apple-ads-mcp.git /tmp/apple-ads-mcp
cp -r /tmp/apple-ads-mcp/skills/apple-ads-mcp ~/.claude/skills/
```

Other agents that support skills load the same `skills/apple-ads-mcp` folder from their own skills directory.

## What it can do

89 tools, all prefixed `apple_ads_`. The full list is in [docs/tools.md](docs/tools.md).

### Read

| Area | Tools |
|---|---|
| Accounts | `get_me`, `list_acls` (ad account IDs and roles), `get_org`, `get_ad_account`, `get_advertiser_resources` |
| Apps | `search_apps`, `get_app`, `check_app_eligibility`, rejection reasons, supported languages, custom product pages |
| Structure | `query_campaigns`, `get_campaign`, `query_adgroups`, `query_keywords`, `query_negative_keywords`, `query_ads`, `query_creatives` |
| Reports | `report` (campaigns, ad groups, ads, keywords, search terms), `performance_summary` (spend, taps, installs, CPT, cost per install) |
| Insights and ideas | `impression_share`, `search_term_popularity`, `keyword_suggestions`, `suggestions`, `query_recommendations` |
| More | budget orders, Apple Maps brands, locations and assets, `query_change_history`, `search_geo` |
| Server | `describe_server`, `health_check`, `audit_tail`, `audit_lookup` |

### Write

| Area | Tools |
|---|---|
| Campaigns | `create_campaign` (starts paused), `update_campaign`, `set_campaign_status`, `set_campaign_daily_budget`, `delete_campaign` |
| Ad groups | `create_adgroup`, `update_adgroup`, `set_adgroup_status`, `set_adgroup_bid`, `delete_adgroup` |
| Keywords | `add_keywords`, `update_keywords`, `delete_keywords`, and the same for negative keywords |
| Ads and creatives | `create_ad`, `update_ad`, `delete_ad`, `create_creative`, `update_creative`, `delete_creative` |
| Recommendations | `apply_recommendations`, `dismiss_recommendations` |
| Budget orders and Apple Maps | `create_budget_order`, `update_budget_order`, `delete_budget_order`, location groups, `delete_asset` |
| Any endpoint | `request` |

### Safety

- Dry-run (`APPLE_ADS_DRY_RUN=true` or `apple_ads_set_dry_run`) previews and logs writes without sending them. Reads and reports still work.
- Deletes need `confirm='DELETE'`. Bulk changes, applying recommendations, budget orders and raw writes need `confirm='APPLY'`.
- Budget and bid rises above `APPLE_ADS_MAX_INCREASE_PCT` (default 20%) need `confirm='APPLY'`, and the refusal shows the change, e.g. `dailyBudget: 10.00 -> 15.00 (+50%)`. New campaigns start paused.
- Every write and dry-run is recorded in an append-only audit log (`~/.apple-ads-mcp/logs/audit.jsonl`) with a `before` snapshot. Entries older than `APPLE_ADS_AUDIT_RETENTION_DAYS` (default 30) are deleted at startup, and `apple-ads-mcp purge` deletes the log.
- `APPLE_ADS_READ_ONLY=true` hides every tool that can change the account; `APPLE_ADS_TOOL_GROUPS` exposes only the groups you need. Every tool carries a title and MCP read-only/destructive hints.
- The HTTP transports have no sign-in, so the server refuses to listen on anything but localhost unless you set `APPLE_ADS_ALLOW_REMOTE=true`.
- Report data stays in memory and is never written to disk. How the server fits Apple's terms: [docs/terms-and-data.md](docs/terms-and-data.md).

## Supported clients

| Client | Works? | How |
|---|---|---|
| Claude Code | ✅ | Local server, `claude mcp add` (below) |
| Claude Desktop | ✅ | Local server, `claude_desktop_config.json` |
| Cursor | ✅ | Local server, `~/.cursor/mcp.json` |
| VS Code (Copilot) | ✅ | Local server, `.vscode/mcp.json` (uses `servers` instead of `mcpServers`) |
| Codex | ✅ | Local server, `~/.codex/config.toml` |
| Gemini CLI | ✅ | Local server, `~/.gemini/settings.json` |
| Windsurf and other local clients | ✅ | Local server, same JSON entry |
| Claude.ai and ChatGPT | ❌ not yet | These need a remote server with sign-in. This server's HTTP transports have no sign-in, so don't expose them publicly. Use a local client. |

## Setup

### 1. Install uv

The server runs with `uvx` from [uv](https://docs.astral.sh/uv/getting-started/installation/)
(`brew install uv` on macOS) and needs Python 3.11 or later. It installs straight
from this repository:

```shell
uvx --from git+https://github.com/AI-Shopping-Feeds/apple-ads-mcp.git apple-ads-mcp
```

Pin a release by adding `@vX.Y.Z` to the URL.

### 2. Get credentials

1. **API user:** in [Apple Ads](https://ads.apple.com), an account administrator
   invites a user under **Account Settings > User Management** with the
   **API Account Read Only** or **API Account Manager** (read and write) role.
2. **Key pair:** make one on your computer. The private key stays in
   `~/.apple-ads-mcp/secrets/`; the command prints the public key:

   ```shell
   uvx --from git+https://github.com/AI-Shopping-Feeds/apple-ads-mcp.git apple-ads-mcp keygen
   ```

3. **Upload and copy your IDs:** signed in as the API user, paste the public key
   into **Account Settings > API** and copy the `clientId`, `teamId` and `keyId`
   Apple shows.

Step by step, including how to find your ad account ID and the rules for
working on clients' accounts: [docs/setup-apple-ads-api.md](docs/setup-apple-ads-api.md).

### 3. Add it to your client

Replace the placeholders. Keep your other servers in each file. Start with
`APPLE_ADS_DRY_RUN=true` so nothing changes until you're happy.

**Claude Code**

```bash
claude mcp add --scope user apple-ads \
  --env APPLE_ADS_CLIENT_ID=SEARCHADS.your-client-id \
  --env APPLE_ADS_TEAM_ID=SEARCHADS.your-team-id \
  --env APPLE_ADS_KEY_ID=your-key-id \
  --env APPLE_ADS_PRIVATE_KEY_PATH=/abs/path/private-key.pem \
  --env APPLE_ADS_DRY_RUN=true \
  -- uvx --from git+https://github.com/AI-Shopping-Feeds/apple-ads-mcp.git apple-ads-mcp
```

**Claude Desktop, Cursor, Gemini CLI, Windsurf** (and VS Code under `servers`)

```json
{
  "mcpServers": {
    "apple-ads": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/AI-Shopping-Feeds/apple-ads-mcp.git", "apple-ads-mcp"],
      "env": {
        "APPLE_ADS_CLIENT_ID": "SEARCHADS.your-client-id",
        "APPLE_ADS_TEAM_ID": "SEARCHADS.your-team-id",
        "APPLE_ADS_KEY_ID": "your-key-id",
        "APPLE_ADS_PRIVATE_KEY_PATH": "/abs/path/private-key.pem",
        "APPLE_ADS_DRY_RUN": "true"
      }
    }
  }
}
```

Desktop apps often can't find `uvx` on the PATH; if the server doesn't start, use
the full path from `which uvx` as the `command`.

**Codex** (`~/.codex/config.toml`)

```toml
[mcp_servers.apple-ads]
command = "uvx"
args = ["--from", "git+https://github.com/AI-Shopping-Feeds/apple-ads-mcp.git", "apple-ads-mcp"]
env = { APPLE_ADS_CLIENT_ID = "SEARCHADS.your-client-id", APPLE_ADS_TEAM_ID = "SEARCHADS.your-team-id", APPLE_ADS_KEY_ID = "your-key-id", APPLE_ADS_PRIVATE_KEY_PATH = "/abs/path/private-key.pem", APPLE_ADS_DRY_RUN = "true" }
```

### 4. Check it works

Restart or reload the client, then ask it to "run the Apple Ads health check". It should
call `apple_ads_health_check` and list the ad accounts your API user can see. Add the one
you want as `APPLE_ADS_AD_ACCOUNT_ID`, and set `APPLE_ADS_DRY_RUN=false` when you're ready
to make real changes.

## Configuration

| Variable | Required | What it does |
|---|---|---|
| `APPLE_ADS_CLIENT_ID` | yes | `clientId` from Account Settings > API |
| `APPLE_ADS_TEAM_ID` | yes | `teamId` from Account Settings > API |
| `APPLE_ADS_KEY_ID` | yes | `keyId` from Account Settings > API |
| `APPLE_ADS_PRIVATE_KEY_PATH` | yes | Path to the private key from `apple-ads-mcp keygen`. Can be left out if it's at `~/.apple-ads-mcp/secrets/private-key.pem` |
| `APPLE_ADS_AD_ACCOUNT_ID` | recommended | Default ad account (sent as `X-AP-Context: adAccountId=…`). Any tool can override it with `ad_account_id` |
| `APPLE_ADS_DRY_RUN` | no | `true` previews and logs writes without sending them |
| `APPLE_ADS_READ_ONLY` | no | `true` registers only read-only tools (plus the meta tools) |
| `APPLE_ADS_TOOL_GROUPS` | no | Comma-separated groups to register (default all): `accounts`, `apps`, `geo`, `campaigns`, `adgroups`, `keywords`, `ads`, `budget_orders`, `reports`, `recommendations`, `maps`, `change_history`, `advanced`. Unknown names stop the server |
| `APPLE_ADS_MAX_INCREASE_PCT` | no | Budget and bid rises above this % need `confirm='APPLY'` (default 20) |
| `APPLE_ADS_AUDIT_LOG` | no | Audit log path (default `~/.apple-ads-mcp/logs/audit.jsonl`) |
| `APPLE_ADS_AUDIT_RETENTION_DAYS` | no | Audit entries older than this are deleted at startup (default 30) |
| `APPLE_ADS_PAGE_SIZE`, `APPLE_ADS_TIMEOUT`, `APPLE_ADS_LOG_LEVEL` | no | `/query` page size (1 to 1000, default 100), request timeout in seconds (default 30) and log level |
| `APPLE_ADS_TRANSPORT`, `APPLE_ADS_HOST`, `APPLE_ADS_PORT` | no | `stdio` (default), `streamable-http` (served at `http://HOST:PORT/mcp`) or `sse` (deprecated by the MCP spec; logs a warning), and its bind address (default `127.0.0.1:8000`) |
| `APPLE_ADS_ALLOW_REMOTE` | no | `true` (or `--allow-remote`) lets the HTTP transports bind to a non-loopback host. Off by default: there is no sign-in |

Settings can also go in `~/.apple-ads-mcp/.env`, `./.env` or a file passed with `--env`.
See [docs/mcp-client-config.md](docs/mcp-client-config.md) for the order, file locations
and the command line (`run`, `keygen`, `purge`, `describe`, `version`).

## Example prompts

```text
How did my App Store campaigns do over the last 7 days? Which one has the worst cost per install?
```

```text
Show last month's search terms for my US campaign and suggest negative keywords for the ones with spend and no installs.
```

```text
Raise the daily budget of my UK campaign to £30. Use dry-run first and show me the change.
```

```text
Which keywords in my main campaign have impression share under 30%?
```

## More docs

- [All tools](docs/tools.md)
- [Apple Ads API setup](docs/setup-apple-ads-api.md): API user, key pair, IDs, ad account and third-party rules
- [MCP client configuration and every environment variable](docs/mcp-client-config.md)
- [Terms and data handling](docs/terms-and-data.md)
- [Agent skill](skills/apple-ads-mcp/SKILL.md): setup and usage guide for agents
- [Changelog](CHANGELOG.md) and [security policy](SECURITY.md)

## Contributing and licence

Issues and pull requests are welcome on [this repository](https://github.com/AI-Shopping-Feeds/apple-ads-mcp). See
[CONTRIBUTING.md](CONTRIBUTING.md).

Licensed under the [MIT License](LICENSE).

---

Try out [AI Shopping Feeds](https://aishoppingfeeds.com/), our shopping feed management tool (including Google Shopping feeds).
