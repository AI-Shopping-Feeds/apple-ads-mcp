# Terms and data handling

This is a summary of how the server is built to fit the
[Apple Ads Terms of Service](https://ads.apple.com/terms-of-service) (effective
28 July 2026). It isn't legal advice; read the terms themselves. You are
responsible for using the server, and the data it returns, in line with the
terms that apply to your account.

This project is not affiliated with or endorsed by Apple. "Apple Ads" is used
only to describe the API it talks to.

## Reporting data is confidential

Apple treats Apple Ads Reporting Metrics as Confidential Information, to be used
only to exercise your rights under the terms and shared only with employees or
consultants who need it.

- The server keeps report rows, insights and every other read response in
  memory only.
- The audit log holds write requests, `before` snapshots and Apple's responses
  to writes, never report data. Entries are deleted after
  `APPLE_ADS_AUDIT_RETENTION_DAYS` (30 by default) when the server starts.
- `apple-ads-mcp purge` deletes the audit log. Access tokens and client secrets
  are never written to disk, so there is no token cache to delete.

## Your AI provider sees what the agent sees

Report data and campaign details returned to Claude, ChatGPT or any other AI
client are sent to that AI provider. Use the server only under business or API
terms that don't train on your inputs, and don't paste report data into
consumer chat products.

## Keys and secrets

- The private key lives in `~/.apple-ads-mcp/secrets/` by default: the folder
  is mode 700 and the key mode 600 on macOS and Linux.
- Keys, client secrets and access tokens are never logged, and they're stripped
  from error messages and audit entries.
- See [SECURITY.md](../SECURITY.md) for revoking access.

## Files on disk

| What | Where (default) | Contains |
|---|---|---|
| Private and public key | `~/.apple-ads-mcp/secrets/` | The key pair from `apple-ads-mcp keygen` |
| Audit log | `~/.apple-ads-mcp/logs/audit.jsonl` | Write requests, responses and `before` snapshots; no report data |
| Settings (optional) | `~/.apple-ads-mcp/.env` | Whatever you put there |

Nothing else is written.

## Network

The server calls only Apple: `appleid.apple.com` for tokens and
`api.ads.apple.com` for the API. There is no telemetry. `apple_ads_request`
accepts paths, not URLs, so it can't be pointed elsewhere, and paths can't
carry query strings or `..`. A single response is capped at 200 MB and one
query or report at 100,000 rows.

The HTTP transports have no sign-in, so the server refuses to listen on
anything but localhost unless `APPLE_ADS_ALLOW_REMOTE=true` is set.

## Rate limits

The client reads Apple's `RateLimit-Limit`, `RateLimit-Remaining` and
`RateLimit-Reset` headers, pauses when the quota is nearly used, and on `429`
waits for `Retry-After` (then `RateLimit-Reset`, then an exponential backoff up
to 16 seconds), as Apple's rate limit guide describes.

## Working on someone else's account

The terms require that, when you use Apple Ads on behalf of a third party (for
example a client's account), you are authorised by them and bind them to the
Apple Ads terms. Apple's help page
[Use the Apple Ads Platform API](https://ads.apple.com/app-store/help/campaigns/0022-use-the-apple-ads-platform-api)
says third-party service providers should register a third-party OAuth 2
application by contacting ads-registration@group.apple.com, and that the
client's Account Admin or Campaign Group Manager then grants the provider
access, with only one third-party provider per Apple Ads account at a time.
The developer docs' "Managing Ad Accounts and API Access" page (checked 6
November 2026) doesn't cover third-party providers.

Before using this server on a client's account, get their written authorisation
and check with Apple whether you need to register as a provider. For your own
apps, the API user described in [setup-apple-ads-api.md](setup-apple-ads-api.md)
is all you need.

## Apple's marks

No Apple logos or badges are used, and nothing here claims Apple's endorsement.
