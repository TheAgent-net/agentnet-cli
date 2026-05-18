from __future__ import annotations

from typing import Any

import httpx

from ..payments.link import LinkClient
from ..payments.mpp_client import MppPaymentClient
from ..payments.spend_controls import SpendController
from ..platform.client import PlatformClient


class ToolHandlers:
    def __init__(
        self,
        *,
        platform_url: str,
        api_token: str,
        agent_id: str,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._client = PlatformClient(
            base_url=platform_url,
            api_token=api_token,
            http_client=http_client or httpx.Client(timeout=30.0),
        )
        self._agent_id = agent_id

    def discover(
        self,
        *,
        query: str,
        category: str | None = None,
        max_results: int = 20,
        max_price: int | None = None,
    ) -> dict[str, Any]:
        return self._client.discover(
            query=query, category=category, max_results=max_results, max_price=max_price,
        )

    def discover_agents(self, *, query: str, limit: int = 20) -> dict[str, Any]:
        return self._client.discover_agents(query=query, limit=limit)

    def get_agent(self, *, agent_id: str) -> dict[str, Any]:
        return self._client.get_agent(agent_id=agent_id)

    def use_agent(
        self, *, agent_id: str, task: str, max_amount: float = 0, quote_id: str | None = None,
    ) -> dict[str, Any]:
        if max_amount < 0 or max_amount > 1000:
            raise ValueError("max_amount must be between 0 and 1000")
        return self._client.use_agent(agent_id=agent_id, task=task, max_amount=max_amount, quote_id=quote_id)

    def continue_session(self, *, session_id: str, message: str) -> dict[str, Any]:
        return self._client.continue_session(session_id=session_id, message=message)

    def settle_session(self, *, session_id: str) -> dict[str, Any]:
        return self._client.settle_session(session_id=session_id)

    def wallet(self, *, action: str, limit: int = 50) -> dict[str, Any]:
        if action not in ("balance", "history"):
            raise ValueError("Invalid action: must be 'balance' or 'history'")
        if action == "balance":
            return self._client.wallet_balance(agent_id=self._agent_id)
        return self._client.wallet_history(agent_id=self._agent_id, limit=limit)

    def wallet_topup(self, *, amount: float) -> dict[str, Any]:
        if amount <= 0 or amount > 10000:
            raise ValueError("amount must be between 0 (exclusive) and 10000")
        return self._client.wallet_topup(agent_id=self._agent_id, amount=amount)

    def link_auth(self, *, client_name: str = "agentnet") -> dict[str, Any]:
        return LinkClient().auth_login(client_name=client_name)

    def link_status(self) -> dict[str, Any]:
        return LinkClient().auth_status()

    def pay(
        self,
        *,
        url: str,
        method: str = "GET",
        data: str | None = None,
        max_amount: float = 25.0,
    ) -> dict[str, Any]:
        from ..payments.link import LinkError

        mpp = MppPaymentClient()
        ctrl = SpendController(single_tx_limit_usd=max_amount)

        probe_result = mpp.probe(url, method=method, data=data)

        if not probe_result["requires_payment"]:
            return probe_result

        body = probe_result.get("body", {})
        amount_minor = body.get("amount_minor", 0) if isinstance(body, dict) else 0
        amount_usd = amount_minor / 100.0

        if not ctrl.check_allowed(amount_usd=amount_usd):
            raise ValueError(
                f"Payment of ${amount_usd:.2f} exceeds spend limit (max ${max_amount:.2f})"
            )

        protocol = mpp.detect_protocol(probe_result.get("headers", {}))

        if protocol == "x402":
            raise ValueError("x402 crypto payments not yet supported via MCP tool")

        if protocol != "mpp":
            raise ValueError(f"Unsupported payment protocol: {protocol}")

        link = LinkClient()
        spend_request_id = None

        methods_resp = link.list_payment_methods()
        pm_list = methods_resp if isinstance(methods_resp, list) else methods_resp.get("data", methods_resp.get("payment_methods", []))
        if not pm_list:
            raise ValueError("No Stripe Link payment methods found. Run link_auth first.")
        payment_method_id = pm_list[0].get("id", pm_list[0].get("payment_method_id", ""))

        agent_name = body.get("agent_name", "Unknown") if isinstance(body, dict) else "Unknown"
        description = body.get("description", "") if isinstance(body, dict) else ""
        context = f"Payment of ${amount_usd:.2f} to {agent_name} ({description}) via AgentNet MCP at {url}"
        if len(context) < 100:
            context = context + " " + description[:100]

        sr = link.spend_request_create(
            amount_cents=amount_minor,
            merchant_name=agent_name,
            merchant_url=url,
            context=context[:500],
            payment_method_id=payment_method_id,
            credential_type="shared_payment_token",
        )
        spend_request_id = sr.get("id", sr.get("spend_request_id", ""))

        link.spend_request_approve(spend_request_id)

        try:
            link.spend_request_retrieve(spend_request_id, interval=5, max_attempts=60)
        except LinkError:
            try:
                link.spend_request_cancel(spend_request_id)
            except LinkError:
                pass
            raise ValueError("Payment approval timed out. Spend request cancelled.")

        result = link.mpp_pay(
            url=url,
            spend_request_id=spend_request_id,
            method=method,
            data=data or "{}",
        )

        ctrl.record_spend(amount_usd=amount_usd, receipt_ref=result.get("receipt_ref", "mpp_pay"))
        return result
