# Apple Ads MCP Server (read + write)

An [MCP](https://modelcontextprotocol.io) server for the **Apple Ads Platform API**
(v1). Use it from Claude Code, Claude Desktop or any MCP client to look after App
Store campaigns: see how campaigns, ad groups and keywords are performing, find
search terms and keyword ideas, check impression share, and change budgets, bids,
keywords and ads, with a dry-run preview and an audit log for every change.

App developers can review and tune their App Store campaigns from the same
agent session as their app code. Apple Maps campaigns are covered too.

Part of the AI Shopping Feeds MCP family: [Google Ads](https://github.com/AI-Shopping-Feeds/google-ads-mcp) · [Google Merchant Centre](https://github.com/AI-Shopping-Feeds/google-merchant-centre-mcp) · [Google Analytics](https://github.com/AI-Shopping-Feeds/google-analytics-mcp) · [YouTube Studio](https://github.com/AI-Shopping-Feeds/youtube-studio-mcp) · **Apple Ads**.

> **Private repository, no licence yet.** This code is not licensed for use
> outside AI Shopping Feeds until a licence is chosen. It is an independent tool:
> it is not made, endorsed or supported by Apple. "Apple Ads" is used only to
> describe the API it talks to.

> **Which Apple API?** Apple's older Campaign Management API (v5, the "Search
> Ads" API at `api.searchads.apple.com`) is deprecated and is switched off on
> **26 January 2027**. This server uses its replacement, the
> [Apple Ads Platform API](https://developer.apple.com/documentation/apple-ads-platform-api)
> v1 (`api.ads.apple.com/v1`), released August 2026. API credentials (client
> ID, team ID, key ID) are created the same way for both.

## What it can do

89 tools in 13 groups (full list in [docs/tools.md](docs/tools.md)):

- **Accounts:** who the API user is, which ad accounts and roles it has.
- **Apps:** search the App Store, app details, ad eligibility, rejection
  reasons, custom product pages.
- **Campaigns, ad groups, keywords, negative keywords, ads, creatives:** list,
  read, create, update, pause, delete, with shortcuts for daily budgets, default
  bids and status.
- **Reports:** campaign, ad group, ad, keyword and search term reports with
  granularity, grouping and time zone, plus a one-call performance summary
  (spend, taps, installs, CPT, cost per install).
- **Insights:** impression share by search term, search term popularity.
- **Recommendations and suggestions:** Apple's budget and target CPA
  recommendations (apply or dismiss), keyword and phrase suggestions.
- **Budget orders, Apple Maps** (brands, locations, location groups, assets),
  **change history**.
- **`apple_ads_request`:** an escape hatch for any Platform API endpoint
  without its own tool.

## Set up (about 20 minutes)

You need: an Apple Ads account with admin access, a Mac with Python 3.10 or
later (or [uv](https://docs.astral.sh/uv/)), and Claude Code or Claude Desktop.

### 1. Create an API user in Apple Ads

Apple Ads API access belongs to a *user*, not to the account, so you invite a
user (it can be yourself on a second Apple Account) with an API role.

1. Go to [ads.apple.com](https://ads.apple.com), choose **Sign In > Advanced**,
   and sign in as an account administrator.
2. In the **Users** menu (top right), pick the account to give access to.
3. Choose **Account Settings > User Management**, then **Invite Users**.
4. Enter the person's first name, last name and Apple Account email.
5. Under **User Access and Role**, choose an API role:
   - **API Account Manager**: read and write (needed to change campaigns).
   - **API Account Read Only**: reports and reading only. A safe start.
6. Click **Send Invite**. The invited person gets an email with a secure code,
   opens the link, enters the code, and their API user is active.

### 2. Install the server

```bash
gh repo clone AI-Shopping-Feeds/apple-ads-mcp ~/code/apple-ads-mcp
cd ~/code/apple-ads-mcp
python3 -m venv .venv            # or: uv venv --python 3.12 .venv
.venv/bin/pip install -e .
```

### 3. Make a key pair

```bash
.venv/bin/apple-ads-mcp keygen
```

This creates `secrets/private-key.pem` (readable only by you, and ignored by
git) and `secrets/public-key.pem`, and prints the **public** key. The private
key never leaves your Mac and is never printed.

### 4. Upload the public key and copy your IDs

1. Sign in to [ads.apple.com](https://ads.apple.com) **as the API user** from
   step 1.
2. Choose **Account Settings > API**.
3. Paste the whole public key, including the `-----BEGIN PUBLIC KEY-----` and
   `-----END PUBLIC KEY-----` lines, into **Public Key**, and click **Save**.
4. Apple shows three values above the key. Copy them:
   - `clientId` (starts with `SEARCHADS.`)
   - `teamId` (also starts with `SEARCHADS.`)
   - `keyId`

### 5. Add the server to Claude

Replace the placeholders with your values and the real path to the folder.
Start with `APPLE_ADS_DRY_RUN=true` so nothing can change until you're happy.

**Claude Code** (one command; keeps your other servers):

```bash
claude mcp add --scope user apple-ads \
  --env APPLE_ADS_CLIENT_ID=SEARCHADS.your-client-id \
  --env APPLE_ADS_TEAM_ID=SEARCHADS.your-team-id \
  --env APPLE_ADS_KEY_ID=your-key-id \
  --env APPLE_ADS_PRIVATE_KEY_PATH=/abs/path/to/apple-ads-mcp/secrets/private-key.pem \
  --env APPLE_ADS_DRY_RUN=true \
  -- /abs/path/to/apple-ads-mcp/.venv/bin/apple-ads-mcp run
```

**Claude Desktop:** open Settings > Developer > Edit Config, and add this inside
`"mcpServers"` (keep the servers already there). Paths must be absolute.

```json
{
  "mcpServers": {
    "apple-ads": {
      "command": "/abs/path/to/apple-ads-mcp/.venv/bin/apple-ads-mcp",
      "args": ["run"],
      "env": {
        "APPLE_ADS_CLIENT_ID": "SEARCHADS.your-client-id",
        "APPLE_ADS_TEAM_ID": "SEARCHADS.your-team-id",
        "APPLE_ADS_KEY_ID": "your-key-id",
        "APPLE_ADS_PRIVATE_KEY_PATH": "/abs/path/to/apple-ads-mcp/secrets/private-key.pem",
        "APPLE_ADS_DRY_RUN": "true"
      }
    }
  }
}
```

Restart Claude Desktop afterwards.

### 6. Check it works and pick your ad account

Ask Claude: *"Run the Apple Ads health check."* It calls
`apple_ads_health_check`, which gets a token and lists every ad account the API
user can see, with its ID and role. Add the one you want as the default:

- Claude Code: run the `claude mcp add` command again with
  `--env APPLE_ADS_AD_ACCOUNT_ID=123456789` (remove the old entry first with
  `claude mcp remove apple-ads`).
- Claude Desktop: add `"APPLE_ADS_AD_ACCOUNT_ID": "123456789"` to `env`.

Any tool can also take `ad_account_id` to work on a different account for one
call. When you're ready to make real changes, set `APPLE_ADS_DRY_RUN=false`
(or ask Claude to turn dry-run off for the session).

If the health check fails with "token request failed", the client, team or key
ID doesn't match the uploaded public key: check them in Account Settings > API.

## Configuration

| Variable | Required | What it does |
|---|---|---|
| `APPLE_ADS_CLIENT_ID` | yes | `clientId` from Account Settings > API |
| `APPLE_ADS_TEAM_ID` | yes | `teamId` from Account Settings > API |
| `APPLE_ADS_KEY_ID` | yes | `keyId` from Account Settings > API |
| `APPLE_ADS_PRIVATE_KEY_PATH` | yes | Path to the private key from `apple-ads-mcp keygen` |
| `APPLE_ADS_AD_ACCOUNT_ID` | recommended | Default ad account (sent as `X-AP-Context: adAccountId=…`) |
| `APPLE_ADS_DRY_RUN` | no | `true` previews and logs writes without sending them |
| `APPLE_ADS_READ_ONLY` | no | `true` registers only read-only tools (plus the meta tools) |
| `APPLE_ADS_MAX_INCREASE_PCT` | no | Budget/bid rises above this % need `confirm='APPLY'` (default 20) |
| `APPLE_ADS_TOOL_GROUPS` | no | Comma-separated groups to register: `accounts`, `apps`, `geo`, `campaigns`, `adgroups`, `keywords`, `ads`, `budget_orders`, `reports`, `recommendations`, `maps`, `change_history`, `advanced` (default all). Unknown names stop the server |
| `APPLE_ADS_AUDIT_LOG` | no | Audit log path (default `~/.apple-ads-mcp/logs/audit.jsonl`) |
| `APPLE_ADS_AUDIT_RETENTION_DAYS` | no | Audit entries older than this are deleted at startup (default 30) |
| `APPLE_ADS_PAGE_SIZE` | no | Page size for `/query` calls, 1 to 1000 (default 100) |
| `APPLE_ADS_TIMEOUT` | no | Per-request timeout in seconds (default 30) |
| `APPLE_ADS_LOG_LEVEL` | no | `DEBUG`, `INFO`, `WARNING` or `ERROR` (logs go to stderr) |
| `APPLE_ADS_TRANSPORT` | no | `stdio` (default) or `streamable-http` (served at `http://HOST:PORT/mcp`; `sse` is deprecated) |
| `APPLE_ADS_HOST`, `APPLE_ADS_PORT` | no | Bind address for HTTP transports (default `127.0.0.1:8000`). There is no sign-in, so keep it on localhost |

CLI: `apple-ads-mcp run` (default), `keygen`, `purge`, `describe`, `version`.

## Safety

Writes change live campaigns and spend real money, so:

- **Dry-run.** `APPLE_ADS_DRY_RUN=true` or `apple_ads_set_dry_run(true)`: write
  tools return the exact request that would be sent and log it, but send
  nothing. Reads still work, so the agent can rehearse a whole change.
- **Confirm strings.** Deletes need `confirm='DELETE'`. Bulk changes (more than
  one keyword, say), applying Apple's recommendations, creating budget orders,
  raw writes through `apple_ads_request`, and any budget or bid **increase
  above `APPLE_ADS_MAX_INCREASE_PCT`** (or a bid set where the current one
  can't be read) need `confirm='APPLY'`. The server reads the current value
  first, so the refusal says exactly what would change, e.g.
  `dailyBudget: 10.00 -> 15.00 (+50%)`.
- **New campaigns start paused** unless you pass `start_paused=false`.
- **Audit log.** Every write and dry-run is appended to a JSONL file with the
  request, Apple's response and a `before` snapshot of the entity where it is
  cheap to read. `apple_ads_audit_tail` and `apple_ads_audit_lookup` show it.
- **Read-only mode and tool groups** limit what the agent can do at all.

The server's instructions tell the agent to rehearse in dry-run, show you
what will change, and only then run it for real.

Money in Apple Ads is an object with a decimal string, in the ad account's
currency: `{"amount": "1.50", "currency": "GBP"}`. Campaign daily budgets wrap
it: `{"dailyBudget": {"value": {"amount": "20.00", "currency": "GBP"}}}`.

## Terms and data handling

This is a summary of how the server is built to fit the
[Apple Ads Terms of Service](https://ads.apple.com/terms-of-service) (effective
28 July 2026). It isn't legal advice; read the terms themselves.

- **Reporting data is confidential.** Apple treats Apple Ads Reporting Metrics
  as Confidential Information, to be used only to exercise your rights under
  the terms and shared only with employees or consultants who need it. The
  server keeps report rows, insights and every other read response in memory
  only. The audit log holds write requests, `before` snapshots and write
  responses, never report data, and entries are deleted after
  `APPLE_ADS_AUDIT_RETENTION_DAYS` (30 by default). `apple-ads-mcp purge`
  deletes the audit log; access tokens and client secrets are never written
  to disk, so there is no token cache to delete.
- **Your AI provider sees what the agent sees.** Report data and campaign
  details returned to Claude (or any AI client) are sent to that AI provider.
  Use the server only under business or API terms that don't train on your
  inputs, and don't paste report data into consumer chat products.
- **Keys and secrets.** The private key lives in the git-ignored `secrets/`
  folder with mode 600. Keys, client secrets and access tokens are never
  logged, and they're stripped from error messages and audit entries.
- **Network.** The server calls only Apple: `appleid.apple.com` for tokens and
  `api.ads.apple.com` for the API. There is no telemetry. `apple_ads_request`
  accepts paths, not URLs, so it can't be pointed elsewhere.
- **Rate limits.** The client reads Apple's `RateLimit-Limit`,
  `RateLimit-Remaining` and `RateLimit-Reset` headers, pauses when the quota is
  nearly used, and on `429` waits for `Retry-After` (then `RateLimit-Reset`,
  then an exponential backoff up to 16 seconds), as Apple's rate limit guide
  describes.
- **Working on someone else's account.** The terms require that, when you use
  Apple Ads on behalf of a third party (for example a client's account), you
  are authorised by them and bind them to the Apple Ads terms. Apple's help
  page [Use the Apple Ads Platform API](https://ads.apple.com/app-store/help/campaigns/0022-use-the-apple-ads-platform-api)
  says third-party service providers should register a third-party OAuth 2
  application by contacting ads-registration@group.apple.com, and that the
  client's Account Admin or Campaign Group Manager then grants the provider
  access, with only one third-party provider per Apple Ads account at a time.
  The developer docs' "Managing Ad Accounts and API Access" page (checked 6
  November 2026) doesn't cover third-party providers. Before using this
  server on a client's account, get their written authorisation and check
  with Apple whether you need to register as a provider. For your own apps,
  the API user set up above is all you need.
- **Apple's marks.** No Apple logos or badges are used, and nothing here
  claims Apple's endorsement.

## Example prompts

```text
How did my App Store campaigns do over the last 7 days? Which one has the worst cost per install?
```

```text
Show the search terms for my UK search campaign last month and suggest negatives.
```

```text
Raise the daily budget of my US search campaign to £30. Use dry-run first and show me the change.
```

```text
Which keywords in the 442 campaign have impression share under 30%?
```

## How it's built

A small Python package (`src/apple_ads_mcp`) on the official MCP Python SDK:
`auth.py` signs the ES256 client secret and caches the access token,
`client.py` is a thin httpx client (account header, retries, rate limits,
pagination, dry-run, audit), `guard.py` holds the spend checks, and
`tools/` has one module per tool group.

Apple publishes an official Python client,
[`apple-ads-platform`](https://github.com/apple/apple-ads-platform-api-python)
(MIT). This server doesn't use it, because it needs Python 3.12 or later (this
package supports 3.10+), it is built on urllib3 (so the offline respx test
suite can't mock it), and dry-run, the audit log and the spend guards need
one request choke point that also serves the raw `apple_ads_request` tool.
The API calls here follow Apple's documentation for the same endpoints.

### Development

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[test]" ruff mypy
.venv/bin/ruff check src tests && .venv/bin/ruff format --check src tests
.venv/bin/mypy src/apple_ads_mcp
.venv/bin/pytest
```

Tests run offline with mocked Apple endpoints and a throwaway key.

## More docs

- [All tools](docs/tools.md)
- [Agent skill](skills/apple-ads-mcp/SKILL.md): setup and usage guide for agents
- [Changelog](CHANGELOG.md)
