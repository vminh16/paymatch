"""HTTP adapter for sim-world endpoints used by read-only tools and demo reset (3s timeout)."""

from __future__ import annotations

from typing import Any

import httpx

from core.tools.ports import UpstreamToolError


class HttpSimWorldAdapter:
    def __init__(
        self,
        sim_url: str,
        service_key: str = "",
        *,
        client: httpx.Client | None = None,
        timeout_s: float = 3.0,
    ) -> None:
        self._sim_url = sim_url.rstrip("/")
        self._service_key = service_key
        self._client = client
        self._timeout_s = timeout_s

    def _headers(self) -> dict[str, str]:
        return {"X-Service-Key": self._service_key} if self._service_key else {}

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        allow_404: bool = False,
    ) -> dict[str, Any] | list[Any] | None:
        url = f"{self._sim_url}{path}"
        try:
            if self._client is not None:
                resp = self._client.request(
                    method, url, params=params, json=json_body, headers=self._headers(), timeout=self._timeout_s
                )
            else:
                resp = httpx.request(
                    method, url, params=params, json=json_body, headers=self._headers(), timeout=self._timeout_s
                )
        except httpx.TimeoutException as exc:
            raise UpstreamToolError(
                "UPSTREAM_TIMEOUT", f"sim-world {path} timed out after {self._timeout_s:.1f}s"
            ) from exc
        except httpx.HTTPError as exc:
            raise UpstreamToolError("UPSTREAM_UNAVAILABLE", f"sim-world {path} error: {exc}") from exc

        if allow_404 and resp.status_code == 404:
            return None
        if resp.status_code >= 500:
            raise UpstreamToolError(
                "UPSTREAM_UNAVAILABLE", f"sim-world {path} returned HTTP {resp.status_code}"
            )
        if resp.status_code >= 400:
            raise UpstreamToolError(
                "NOT_FOUND" if resp.status_code == 404 else "UPSTREAM_UNAVAILABLE",
                f"sim-world {path} returned HTTP {resp.status_code}: {resp.text[:200]}",
            )
        return resp.json()

    def get_inbox_messages(
        self, *, mailbox: str, from_address: str | None = None, since: str | None = None
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"mailbox": mailbox}
        if from_address:
            params["from"] = from_address
        data = self._request("GET", "/inbox/messages", params=params)
        items = data.get("items", []) if isinstance(data, dict) else []
        if since:
            items = [m for m in items if (m.get("received_at") or "") >= since]
        return items

    def get_chat_threads(
        self, *, tenant_ref: str, counterparty_phone: str | None = None
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"tenant_ref": tenant_ref}
        if counterparty_phone:
            params["counterparty_phone"] = counterparty_phone
        data = self._request("GET", "/chat/threads", params=params)
        return data if isinstance(data, list) else []

    def get_chat_messages(
        self, *, thread_id: str, since: str | None = None
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if since:
            params["since"] = since
        data = self._request("GET", f"/chat/threads/{thread_id}/messages", params=params)
        return data if isinstance(data, list) else []

    def check_simo_indicator(self, *, kind: str, value_hash: str) -> dict[str, Any]:
        data = self._request(
            "GET",
            "/simo/indicators:check",
            params={"kind": kind, "value_hash": value_hash},
        )
        assert isinstance(data, dict)
        return data

    def lookup_einvoice_portal(
        self, *, seller_tax_id: str, symbol: str, number: str
    ) -> dict[str, Any]:
        data = self._request(
            "GET",
            "/einvoice/invoices",
            params={"seller_tax_id": seller_tax_id, "symbol": symbol, "number": number},
        )
        assert isinstance(data, dict)
        return data

    def lookup_taxpayer(self, *, tax_id: str) -> dict[str, Any] | None:
        data = self._request("GET", f"/tax/taxpayers/{tax_id}", allow_404=True)
        return data if isinstance(data, dict) else None

    def lookup_tax_risk_list(self, *, tax_id: str) -> dict[str, Any]:
        data = self._request("GET", f"/tax/risk-list/{tax_id}")
        assert isinstance(data, dict)
        return data

    def get_momo_revenue(self, *, wallet_id: str, store_ref: str, month: str) -> dict[str, Any]:
        data = self._request(
            "GET",
            "/revenue",
            params={"wallet_id": wallet_id, "store_ref": store_ref, "month": month},
        )
        assert isinstance(data, dict)
        return data

    def get_wallet_balance(self, *, wallet_id: str) -> dict[str, Any]:
        data = self._request("GET", f"/rails/wallets/{wallet_id}")
        assert isinstance(data, dict)
        return data

    def reset_scenario(self, *, dataset: str = "demo", seed: int = 42) -> dict[str, Any]:
        data = self._request(
            "POST",
            "/scenario:reset",
            json_body={"dataset": dataset, "seed": seed},
        )
        assert isinstance(data, dict)
        return data
