"""Who am I, which ad accounts can I use: /me, /acls, /orgs, /ad-accounts."""

from __future__ import annotations

from typing import Any

from ..client import AppleAdsClient


def register(mcp, client: AppleAdsClient) -> None:
    @mcp.tool()
    def apple_ads_get_me() -> dict[str, Any]:
        """The API user's userId and orgId (GET /v1/me). Needs no ad account."""
        return client.get_result("me", context="none")

    @mcp.tool()
    def apple_ads_list_acls() -> dict[str, Any]:
        """Every ad account this API user can access, with its roles (GET /v1/acls).

        Use it to find the ad_account_id to pass to other tools. Roles: Admin,
        API Account Manager (read/write), API Account Read Only, and the two
        Limited Access roles.
        """
        return client.get_result("acls", context="none")

    @mcp.tool()
    def apple_ads_get_org(org_id: str) -> dict[str, Any]:
        """An organization's name, currency, time zone, payment model and status (GET /v1/orgs/{id})."""
        return client.get_result(f"orgs/{int(org_id)}", context="none")

    @mcp.tool()
    def apple_ads_get_ad_account(ad_account_id: str | None = None) -> dict[str, Any]:
        """An ad account's details: currency, time zone, product features
        (APPSTORE_APP_MANUAL for App Store, BUSINESS_BRAND_MANUAL for Apple Maps),
        delegations and status (GET /v1/ad-accounts/{id}).

        ad_account_id: defaults to APPLE_ADS_AD_ACCOUNT_ID.
        """
        account = client.resolve_account(ad_account_id)
        if account is None:
            raise ValueError("Pass ad_account_id (see apple_ads_list_acls).")
        return client.get_result(f"ad-accounts/{account}", ad_account_id=account)

    @mcp.tool()
    def apple_ads_get_advertiser_resources(resource_type: str) -> dict[str, Any]:
        """Advertiser resources in the org that can be delegated to an ad account
        (GET /v1/advertiser-resources).

        resource_type: CONTENT_PROVIDER (App Store apps) or BUSINESS_BRAND (Apple Maps).
        """
        return client.get_result(
            "advertiser-resources",
            params={"resourceType": resource_type.strip().upper()},
            context="none",
        )
