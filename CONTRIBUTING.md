# Contributing

Thanks for helping improve Apple Ads MCP.

## Development setup

With [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/AI-Shopping-Feeds/apple-ads-mcp.git
cd apple-ads-mcp
uv venv && uv pip install -e ".[test,dev]"
.venv/bin/pre-commit install
```

Or with plain Python 3.11 or later:

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[test,dev]"
```

To try it against a real account, follow [docs/setup-apple-ads-api.md](docs/setup-apple-ads-api.md)
and start with `APPLE_ADS_DRY_RUN=true`. Use an account and API user you are
allowed to test with.

## Checks

```bash
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
.venv/bin/mypy src/apple_ads_mcp
.venv/bin/pytest
```

CI runs the same on Ubuntu, macOS and Windows with Python 3.11 to 3.15.
Tests run offline: Apple's token and API endpoints are mocked with `respx`
and the private key is a throwaway made per test run. They never touch a real
account, and they use a temporary home folder, so your own
`~/.apple-ads-mcp` is never read.

## Pull requests

- Keep keys, client IDs, tokens, ad account IDs and report data out of
  commits, issues and test fixtures. Use obviously fake values.
- New tools go in the matching module under `src/apple_ads_mcp/tools/` and use
  the `apple_ads_` prefix.
- Every tool needs an entry in `src/apple_ads_mcp/tool_catalog.py` (title and
  read-only/destructive/idempotent annotations) and a mention in
  [docs/tools.md](docs/tools.md). The tests fail if either is missing.
- Writes go through `AppleAdsClient.request`, so dry-run and the audit log
  apply. Deletes need `confirm='DELETE'`; bulk changes and budget or bid
  rises go through `guard.py` and need `confirm='APPLY'`.
- IDs that go into a URL path are integers or pass `client.path_segment`.
- Report rows and other read responses never go to the audit log or to disk.
- Don't paste Apple's API documentation, specs or sample files into the repo.
  Link to [Apple's documentation](https://developer.apple.com/documentation/apple-ads-platform-api)
  and write the code and docs in your own words.
- Update [docs/tools.md](docs/tools.md), the README and
  [CHANGELOG.md](CHANGELOG.md) when tools, settings or setup change.

## How it's built

A small Python package (`src/apple_ads_mcp`) on the official MCP Python SDK:

- `auth.py` signs the ES256 client secret and caches the access token in memory.
- `client.py` is a thin httpx client: ad account header, retries, rate
  limits, pagination, response size cap, dry-run and audit.
- `guard.py` holds the spend checks and confirm strings.
- `paths.py` holds the per-user file locations (`~/.apple-ads-mcp`).
- `tool_catalog.py` has every tool's title and annotations.
- `tools/` has one module per tool group.

Apple publishes an official Python client,
[`apple-ads-platform`](https://github.com/apple/apple-ads-platform-api-python)
(MIT). This server doesn't use it: it needs Python 3.12 or later, it is built
on urllib3 (so the offline respx test suite can't mock it), and dry-run, the
audit log and the spend guards need one request choke point that also serves
the raw `apple_ads_request` tool.
