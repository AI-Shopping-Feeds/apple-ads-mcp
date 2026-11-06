# Security

This server acts on Apple Ads accounts with the permissions of the API user you
set it up with. With an **API Account Manager** role it can create, enable and
delete campaigns, ad groups, keywords and ads, raise budgets and bids, and
create budget orders: it can **spend real money**. With either role it reads
Apple Ads reporting data, which Apple's terms treat as confidential.

## Protect your credentials

- The private key lives in `~/.apple-ads-mcp/secrets/private-key.pem` by default
  (the folder is mode 700, the key mode 600). Don't move it into a project
  folder or a git repository, and never paste it into a chat. Only the public
  key goes to Apple.
- Access tokens and client secrets are kept in memory only. They are never
  logged, written to disk or returned by a tool, and they're stripped from
  error messages and the audit log.
- Use the **API Account Read Only** role, or `APPLE_ADS_READ_ONLY=true`, when
  you only need reports. Start with `APPLE_ADS_DRY_RUN=true`, and keep
  `APPLE_ADS_MAX_INCREASE_PCT` low.
- **Revoking access:** an account administrator can remove the API user, or
  change its role, in Apple Ads under **Account Settings > User Management**.
  Signed in as the API user, you can replace the public key in **Account
  Settings > API**; the old private key then stops working. Do one of these
  straight away if a machine or key is lost, then delete the old key file.

## Never expose the HTTP transport

The `streamable-http` and `sse` transports have no sign-in. Anyone who can
reach the port can use your Apple Ads credentials. The server binds to
`127.0.0.1` by default and refuses any other host unless you set
`APPLE_ADS_ALLOW_REMOTE=true` (or pass `--allow-remote`). Only do that behind
your own authenticating proxy on a private network. For local clients, use
`stdio` (the default).

## Data on disk

The only files the server writes are the key pair (`apple-ads-mcp keygen`) and
the audit log (`~/.apple-ads-mcp/logs/audit.jsonl`, mode 600). The audit log
holds write requests, Apple's responses to them and `before` snapshots, never
report data, and entries older than `APPLE_ADS_AUDIT_RETENTION_DAYS` (30 by
default) are deleted at startup. `apple-ads-mcp purge` deletes it. See
[docs/terms-and-data.md](docs/terms-and-data.md).

## Reporting a vulnerability or suspected misuse

Report privately through a
[GitHub security advisory](https://github.com/AI-Shopping-Feeds/apple-ads-mcp/security/advisories/new)
on this repository. Use the same form to report suspected misuse of Apple Ads
data or credentials involving this software, for example a server exposed to
the internet, a leaked key, or report data sent somewhere it shouldn't go.

Include what you found, how to reproduce it and the version or commit. Don't
include working credentials, private keys, access tokens or real account data,
and don't post exploits or leaked credentials in a public issue.

If your own Apple Ads account may be affected, revoke access as described
above and contact Apple through [Apple Ads Help](https://ads.apple.com/app-store/help).

Security fixes go into the latest version on `main`.
