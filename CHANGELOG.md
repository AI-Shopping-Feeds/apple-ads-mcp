# Changelog: Apple Ads MCP (`apple-ads-mcp`)

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- MIT licence, security policy, contributing guide, issue and pull request
  templates, Dependabot and a pre-commit config.
- `APPLE_ADS_ALLOW_REMOTE` and `--allow-remote`.
- `~/.apple-ads-mcp/.env` is read after `./.env` (or only the `--env` file).
- Docs: Apple Ads API setup, MCP client configuration and terms and data
  handling, moved out of the README and expanded.

### Changed
- HTTP transports now **refuse** a non-loopback host unless
  `APPLE_ADS_ALLOW_REMOTE=true` (or `--allow-remote`); they used to only warn.
- `keygen` writes to `~/.apple-ads-mcp/secrets/` (folder 700, key 600) instead
  of `./secrets/`, and `APPLE_ADS_PRIVATE_KEY_PATH` defaults to the key there
  when it exists. The audit log folders are created owner-only.
- `.env` lookup no longer depends on where the package is installed.
- Setup uses `uvx` from git instead of a clone and virtual environment.
- Python 3.11 or later (3.10 is end of life); tested on 3.11 to 3.15 on Linux,
  macOS and Windows. Minimum versions raised to current releases.

### Security
- `apple_ads_request` paths may only contain letters, digits, `-`, `_`, `.`,
  `~` and `/`, with no `.`, `..` or empty segments, and the final URL must be
  on `api.ads.apple.com`. String IDs must be a single path segment.
- Responses over 200 MB are refused, and one query or report collects at most
  100,000 rows.

## [0.1.0] - 2026-11-06

### Added
- First version, on the Apple Ads Platform API v1 (`https://api.ads.apple.com/v1`).
  The older Campaign Management API v5 is deprecated and sunsets on
  26 January 2027, so it isn't used.
- OAuth 2 client credentials: ES256-signed client secret (short-lived,
  re-signed before expiry), access token cached in memory and refreshed
  before it expires or after a 401.
- `X-AP-Context: adAccountId=…` from `APPLE_ADS_AD_ACCOUNT_ID`, overridable
  per call with `ad_account_id`; omitted for `/me`, `/acls`, `/orgs` and
  budget order writes.
- 89 tools in 13 groups: accounts, apps, geo, campaigns, ad groups, keywords
  and negative keywords (bulk endpoints), ads and creatives, budget orders,
  reports (with a performance summary), impression share and search term
  popularity, recommendations and suggestions, Apple Maps, change history,
  and the `apple_ads_request` escape hatch.
- Safety: dry-run (`APPLE_ADS_DRY_RUN`, `apple_ads_set_dry_run`), JSONL audit
  log of writes with `before` snapshots, `confirm` for deletes, bulk changes
  and budget/bid rises over `APPLE_ADS_MAX_INCREASE_PCT`, new campaigns start
  paused, `APPLE_ADS_READ_ONLY`, `APPLE_ADS_TOOL_GROUPS`.
- Data handling: report data is never written to disk; audit entries are
  pruned after `APPLE_ADS_AUDIT_RETENTION_DAYS` (default 30); keys, secrets
  and tokens are redacted from logs, errors and the audit log.
- Rate limits: honours `RateLimit-*` headers and `Retry-After`, with backoff
  capped at 16 seconds.
- CLI: `run` (stdio or streamable HTTP), `keygen`, `purge`, `describe`, `version`.
- Tool titles and MCP annotations for every tool, server instructions, an
  agent skill, and an offline test suite (respx).
