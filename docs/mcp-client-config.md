# MCP client configuration

The server runs locally over stdio. The examples use `uvx` from [uv](https://docs.astral.sh/uv/);
`pipx run --spec git+https://github.com/AI-Shopping-Feeds/apple-ads-mcp.git apple-ads-mcp` works too.
Replace the placeholders with the values from Apple Ads > Account Settings > API
(see [setup-apple-ads-api.md](setup-apple-ads-api.md)), and keep your other servers in each file.

## Claude Code

```bash
claude mcp add --scope user apple-ads \
  --env APPLE_ADS_CLIENT_ID=SEARCHADS.your-client-id \
  --env APPLE_ADS_TEAM_ID=SEARCHADS.your-team-id \
  --env APPLE_ADS_KEY_ID=your-key-id \
  --env APPLE_ADS_PRIVATE_KEY_PATH=/abs/path/private-key.pem \
  --env APPLE_ADS_DRY_RUN=true \
  -- uvx --from git+https://github.com/AI-Shopping-Feeds/apple-ads-mcp.git apple-ads-mcp
```

To change a setting later, remove the entry with `claude mcp remove apple-ads` and add it again.

## Claude Desktop, Cursor and other JSON configs

```json
"apple-ads": {
  "command": "/full/path/to/uvx",
  "args": ["--from", "git+https://github.com/AI-Shopping-Feeds/apple-ads-mcp.git", "apple-ads-mcp"],
  "env": {
    "APPLE_ADS_CLIENT_ID": "SEARCHADS.your-client-id",
    "APPLE_ADS_TEAM_ID": "SEARCHADS.your-team-id",
    "APPLE_ADS_KEY_ID": "your-key-id",
    "APPLE_ADS_PRIVATE_KEY_PATH": "/abs/path/private-key.pem",
    "APPLE_ADS_AD_ACCOUNT_ID": "123456789",
    "APPLE_ADS_DRY_RUN": "true"
  }
}
```

Claude Desktop: `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or
`%APPDATA%\Claude\claude_desktop_config.json` (Windows). Cursor: `~/.cursor/mcp.json`.
VS Code uses the same entry under `servers` in `.vscode/mcp.json`. Desktop apps often can't
find `uvx` on the PATH, so use the full path from `which uvx` (`where uvx` on Windows).

## Codex

```toml
[mcp_servers.apple-ads]
command = "uvx"
args = ["--from", "git+https://github.com/AI-Shopping-Feeds/apple-ads-mcp.git", "apple-ads-mcp"]
env = { APPLE_ADS_CLIENT_ID = "SEARCHADS.your-client-id", APPLE_ADS_TEAM_ID = "SEARCHADS.your-team-id", APPLE_ADS_KEY_ID = "your-key-id", APPLE_ADS_PRIVATE_KEY_PATH = "/abs/path/private-key.pem", APPLE_ADS_DRY_RUN = "true" }
```

## Settings in a .env file

Instead of putting settings in the client config, you can keep them in a `.env` file
(see [.env.example](../.env.example)). The server reads, in order:

1. variables already set in the environment (for example by the client config);
2. the file given with `--env /abs/path/.env`, if any; otherwise
3. `./.env` in the folder the server starts in, then `~/.apple-ads-mcp/.env`.

The first place to set a variable wins. Desktop clients often start servers in `/`, so
`~/.apple-ads-mcp/.env` is the reliable place for a per-user file.

## File locations

Defaults don't depend on where the package is installed or where the server starts:

| What | Default | Override |
|---|---|---|
| Private key | `~/.apple-ads-mcp/secrets/private-key.pem` (used when `APPLE_ADS_PRIVATE_KEY_PATH` isn't set and the file exists) | `APPLE_ADS_PRIVATE_KEY_PATH`; `keygen --dir` |
| Audit log | `~/.apple-ads-mcp/logs/audit.jsonl` | `APPLE_ADS_AUDIT_LOG` |
| Optional settings | `~/.apple-ads-mcp/.env` | `--env` |

On macOS and Linux the folders the server creates are mode 700, and the key and audit log
mode 600. On Windows they live in your user profile (`%USERPROFILE%\.apple-ads-mcp`).

## Running over HTTP (streamable-http)

stdio is the simplest setup for a single local client. To serve the tools over HTTP, use the
`streamable-http` transport, the current MCP standard:

```bash
uvx --from git+https://github.com/AI-Shopping-Feeds/apple-ads-mcp.git \
  apple-ads-mcp --transport streamable-http --port 8000 run
# Claude Code:
claude mcp add --transport http apple-ads http://127.0.0.1:8000/mcp
```

The server has no sign-in of its own. It binds to `127.0.0.1` by default and **refuses to
start** on any other host unless you set `APPLE_ADS_ALLOW_REMOTE=true` or pass
`--allow-remote`, and even then it logs a warning. Only do that behind your own
authenticating proxy on a private network.

The `sse` transport (HTTP+SSE) still works for older clients but is deprecated by the MCP
specification; the server logs a warning when it is used. Prefer `streamable-http`.

## Limiting the tool list

Large tool lists cost context and make tool choice harder. Expose only what you need:

- `APPLE_ADS_TOOL_GROUPS=campaigns,adgroups,keywords,reports` registers only those groups.
  Groups: `accounts`, `apps`, `geo`, `campaigns`, `adgroups`, `keywords`, `ads`,
  `budget_orders`, `reports`, `recommendations`, `maps`, `change_history`, `advanced`.
  An unknown group stops the server at startup with the list of valid groups.
- `APPLE_ADS_READ_ONLY=true` registers only read-only tools, for reporting agents that must
  not change anything.

The meta tools (`apple_ads_describe_server`, `apple_ads_health_check`, the audit tools and
`apple_ads_set_dry_run`) are always registered.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `APPLE_ADS_CLIENT_ID` | required | `clientId` from Account Settings > API (starts with `SEARCHADS.`) |
| `APPLE_ADS_TEAM_ID` | required | `teamId` from Account Settings > API |
| `APPLE_ADS_KEY_ID` | required | `keyId` from Account Settings > API |
| `APPLE_ADS_PRIVATE_KEY_PATH` | `~/.apple-ads-mcp/secrets/private-key.pem` if it exists | Private key from `apple-ads-mcp keygen` |
| `APPLE_ADS_AD_ACCOUNT_ID` | unset | Default ad account, sent as `X-AP-Context: adAccountId=…` |
| `APPLE_ADS_DRY_RUN` | `false` | Preview and log writes without sending them |
| `APPLE_ADS_READ_ONLY` | `false` | Register only read-only tools (plus the meta tools) |
| `APPLE_ADS_TOOL_GROUPS` | unset (all) | Comma-separated tool groups to register |
| `APPLE_ADS_MAX_INCREASE_PCT` | `20` | Budget and bid rises above this % need `confirm='APPLY'` |
| `APPLE_ADS_AUDIT_LOG` | `~/.apple-ads-mcp/logs/audit.jsonl` | Where writes are recorded |
| `APPLE_ADS_AUDIT_RETENTION_DAYS` | `30` | Audit entries older than this are deleted at startup |
| `APPLE_ADS_PAGE_SIZE` | `100` | Page size for `/query` calls, 1 to 1000 |
| `APPLE_ADS_TIMEOUT` | `30` | Per-request timeout in seconds |
| `APPLE_ADS_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING` or `ERROR` (logs go to stderr) |
| `APPLE_ADS_TRANSPORT` | `stdio` | `stdio`, `streamable-http` (served at `/mcp`) or `sse` (deprecated) |
| `APPLE_ADS_HOST` | `127.0.0.1` | Bind host for HTTP transports |
| `APPLE_ADS_PORT` | `8000` | Bind port for HTTP transports |
| `APPLE_ADS_ALLOW_REMOTE` | `false` | `true` lets HTTP transports bind to a non-loopback host. There is no sign-in: don't, unless it's behind your own authentication |

## Command line

`apple-ads-mcp [--env FILE] [--transport T] [--host H] [--port P] [--allow-remote] COMMAND`

| Command | What it does |
|---|---|
| `run` (default) | Start the server |
| `keygen [--dir DIR] [--force]` | Make the key pair (default `~/.apple-ads-mcp/secrets`) and print the public key |
| `describe` | Print the settings the server would use, without secrets |
| `purge [--yes]` | Delete the audit log |
| `version` | Print the version |
