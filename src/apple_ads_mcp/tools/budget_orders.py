"""Budget orders (Apple calls the resource shared-budgets): /v1/shared-budgets.

Budget orders belong to the organization, not an ad account. Create, update
and delete need organization-level permissions and must be sent WITHOUT the
X-AP-Context header (Apple returns 403 if it is present). Query and get work
without it for org-level users; users limited to some ad accounts must send it.
"""

from __future__ import annotations

from typing import Any

from .. import guard
from ..client import AppleAdsClient
from ._common import guarded_delete, guarded_update, query_body


def register(mcp, client: AppleAdsClient) -> None:
    @mcp.tool()
    def apple_ads_query_budget_orders(
        filters: list[dict[str, Any]] | None = None,
        max_items: int = 200,
        send_ad_account_context: bool = False,
        ad_account_id: str | None = None,
    ) -> dict[str, Any]:
        """List budget orders (POST /v1/shared-budgets/query).

        send_ad_account_context: set true if your API user is limited to specific
        ad accounts (otherwise Apple returns 403).
        """
        return client.query(
            "shared-budgets/query",
            query_body(filters),
            max_items=max_items,
            ad_account_id=ad_account_id,
            context="account" if send_ad_account_context else "none",
        )

    @mcp.tool()
    def apple_ads_get_budget_order(
        budget_order_id: str,
        send_ad_account_context: bool = False,
        ad_account_id: str | None = None,
    ) -> dict[str, Any]:
        """One budget order (GET /v1/shared-budgets/{id})."""
        return client.get_result(
            f"shared-budgets/{int(budget_order_id)}",
            ad_account_id=ad_account_id,
            context="account" if send_ad_account_context else "none",
        )

    @mcp.tool()
    def apple_ads_create_budget_order(
        budget_order: dict[str, Any], confirm: str = ""
    ) -> dict[str, Any]:
        """Create a budget order (POST /v1/shared-budgets). Commits spend: confirm must be 'APPLY'.

        budget_order: {"name": "Q1 2027", "startTime": "2027-01-01T00:00:00.000",
          "endTime": "2027-03-31T23:59:59.000",
          "value": {"amount": "5000.00", "currency": "GBP"}, "adAccountIds": [123],
          "invoiceDetail": {...}}
        Needs organization-level permissions.
        """
        amount = guard.amount_of(budget_order.get("value"))
        note = guard.require(
            confirm,
            guard.CONFIRM_APPLY,
            [
                f"creates a budget order worth {amount if amount is not None else 'an unknown amount'}"
            ],
            dry_run=client.config.dry_run,
        )
        out = client.request(
            "POST",
            "shared-budgets",
            json_body=budget_order,
            op="create_budget_order",
            context="none",
        )
        return {**out, **note} if isinstance(out, dict) else out

    @mcp.tool()
    def apple_ads_update_budget_order(
        budget_order_id: str, update: dict[str, Any], confirm: str = ""
    ) -> dict[str, Any]:
        """Partially update a budget order (PUT /v1/shared-budgets/{id}).

        Raising its value by more than APPLE_ADS_MAX_INCREASE_PCT needs confirm='APPLY'.
        """
        bid = int(budget_order_id)
        return guarded_update(
            client,
            get_path=f"shared-budgets/{bid}",
            put_path=f"shared-budgets/{bid}",
            update=update,
            confirm=confirm,
            op="update_budget_order",
            ad_account_id=None,
            context="none",
        )

    @mcp.tool()
    def apple_ads_delete_budget_order(budget_order_id: str, confirm: str = "") -> dict[str, Any]:
        """Delete a budget order (DELETE /v1/shared-budgets/{id}). confirm: must be 'DELETE'."""
        bid = int(budget_order_id)
        return guarded_delete(
            client,
            path=f"shared-budgets/{bid}",
            confirm=confirm,
            op="delete_budget_order",
            what=f"budget order {bid}",
            ad_account_id=None,
            context="none",
        )
