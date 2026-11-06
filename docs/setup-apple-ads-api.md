# Apple Ads API setup

Apple Ads MCP signs in to the Apple Ads Platform API with an **API user** and a
key pair you make yourself. The private key stays on your computer; Apple only
gets the public key. It takes about 15 minutes.

You need an Apple Ads account where you're an account administrator (or someone
who is to invite you), and [uv](https://docs.astral.sh/uv/getting-started/installation/).

## Which Apple API this uses

Apple's older Campaign Management API (v5, the "Search Ads" API at
`api.searchads.apple.com`) is deprecated and is switched off on
**26 January 2027**. This server uses its replacement, the
[Apple Ads Platform API](https://developer.apple.com/documentation/apple-ads-platform-api)
v1 (`https://api.ads.apple.com/v1`). API users and keys are set up the same way
for both, so an API user you already made for v5 works here too.

## 1. Create an API user

Apple Ads API access belongs to a *user*, not to the account. You invite a user
with an API role. It can be you, using a second Apple Account.

1. Go to [ads.apple.com](https://ads.apple.com), choose **Sign In > Advanced**,
   and sign in as an account administrator.
2. In the **Users** menu (top right), pick the account to give access to.
3. Choose **Account Settings > User Management**, then **Invite Users**.
4. Enter the person's first name, last name and Apple Account email.
5. Under **User Access and Role**, choose an API role:
   - **API Account Read Only**: reports and reading only. A safe start, and
     all you need for reporting.
   - **API Account Manager**: read and write. Needed to change campaigns,
     budgets, bids, keywords and ads.
6. Click **Send Invite**. The invited person gets an email with a secure code,
   opens the link, enters the code, and their API user is active.

## 2. Make a key pair

```shell
uvx --from git+https://github.com/AI-Shopping-Feeds/apple-ads-mcp.git apple-ads-mcp keygen
```

This creates `~/.apple-ads-mcp/secrets/private-key.pem` (readable only by you)
and `public-key.pem` next to it, and prints the **public** key and the path to
use for `APPLE_ADS_PRIVATE_KEY_PATH`. The private key is never printed. Use
`--dir /abs/path/folder` to keep the keys somewhere else, and `--force` to
replace an existing pair.

Keep the private key out of project folders and git repositories, and never
paste it into a chat.

## 3. Upload the public key and copy your IDs

1. Sign in to [ads.apple.com](https://ads.apple.com) **as the API user** from step 1.
2. Choose **Account Settings > API**.
3. Paste the whole public key, including the `-----BEGIN PUBLIC KEY-----` and
   `-----END PUBLIC KEY-----` lines, into **Public Key**, and click **Save**.
4. Apple shows three values above the key. Copy them into your MCP client's
   config (see the [README](../README.md#3-add-it-to-your-client)):
   - `clientId` (starts with `SEARCHADS.`) → `APPLE_ADS_CLIENT_ID`
   - `teamId` (also starts with `SEARCHADS.`) → `APPLE_ADS_TEAM_ID`
   - `keyId` → `APPLE_ADS_KEY_ID`

If you replace the key later, upload the new public key here and update
`APPLE_ADS_KEY_ID`.

## 4. Find your ad account ID

Add the server to your client with `APPLE_ADS_DRY_RUN=true`, restart the
client and ask it to "run the Apple Ads health check". It calls
`apple_ads_health_check`, which gets a token and lists every ad account the API
user can see, with its ID and role. `apple_ads_list_acls` and
`apple_ads_get_ad_account` show the same details.

Set the one you want as `APPLE_ADS_AD_ACCOUNT_ID`. It is sent on each call as
`X-AP-Context: adAccountId=...`. Any tool can also take `ad_account_id` to
work on a different account for one call.

When you're ready to make real changes, set `APPLE_ADS_DRY_RUN=false` (or ask
the agent to turn dry-run off for the session).

## Working on other people's accounts

If you run this server for clients, Apple's rules for third-party providers
apply. Apple's help page
[Use the Apple Ads Platform API](https://ads.apple.com/app-store/help/campaigns/0022-use-the-apple-ads-platform-api)
says:

- third-party service providers should register a third-party OAuth 2
  application by contacting ads-registration@group.apple.com;
- the client's Account Admin or Campaign Group Manager then grants the provider
  access;
- only one third-party provider can have access to an Apple Ads account at a
  time.

The [Apple Ads Terms of Service](https://ads.apple.com/terms-of-service) also
require that you are authorised by the account owner and bind them to the
terms. Before using this server on a client's account, get their written
authorisation and check with Apple whether you need to register as a provider.
For your own apps, the API user above is all you need. See
[terms-and-data.md](terms-and-data.md).

## Troubleshooting

- **"Apple token request failed (HTTP 400/401)":** the client, team or key ID
  doesn't match the uploaded public key, or the key was replaced. Check them in
  Account Settings > API.
- **"Missing Apple Ads API credentials":** one of the four required variables
  isn't set. `APPLE_ADS_PRIVATE_KEY_PATH` can be left out only if the key is at
  `~/.apple-ads-mcp/secrets/private-key.pem`.
- **"No ad account selected":** set `APPLE_ADS_AD_ACCOUNT_ID` or pass
  `ad_account_id` (see `apple_ads_list_acls`).
- **403 on a write:** the API user's role is read-only or limited. Budget order
  writes need organisation-level permissions.
- **Writes return `_dry_run: true`:** dry-run is on.
- **`apple-ads-mcp describe`** prints the settings the server would use, without
  secrets.
