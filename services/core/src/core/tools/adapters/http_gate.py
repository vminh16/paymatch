"""HTTP adapter implementing GateClientPort against Payment Gate (/gate/*)."""

from __future__ import annotations

from typing import Any

import httpx

from core.tools.ports import GateEvaluation, UpstreamToolError


class HttpGateAdapter:
    def __init__(
        self,
        gate_url: str,
        service_key: str = "",
        *,
        client: httpx.Client | None = None,
        eval_timeout_s: float = 2.0,
        execute_timeout_s: float = 10.0,
    ) -> None:
        self._gate_url = gate_url.rstrip("/")
        self._service_key = service_key
        self._client = client
        self._eval_timeout_s = eval_timeout_s
        self._execute_timeout_s = execute_timeout_s

    def _headers(self) -> dict[str, str]:
        return {"X-Service-Key": self._service_key} if self._service_key else {}

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        timeout_s: float | None = None,
    ) -> httpx.Response:
        url = f"{self._gate_url}{path}"
        to = timeout_s or self._eval_timeout_s
        try:
            if self._client is not None:
                return self._client.request(
                    method, url, params=params, json=json_body, headers=self._headers(), timeout=to
                )
            return httpx.request(
                method, url, params=params, json=json_body, headers=self._headers(), timeout=to
            )
        except httpx.TimeoutException as exc:
            raise UpstreamToolError("UPSTREAM_TIMEOUT", f"gate {path} timed out after {to:.1f}s") from exc
        except httpx.HTTPError as exc:
            raise UpstreamToolError("UPSTREAM_UNAVAILABLE", f"gate {path} unavailable: {exc}") from exc

    def evaluate_invoice(self, *, invoice_id: str, tenant_id: str) -> GateEvaluation:
        resp = self._request(
            "POST",
            "/evaluate",
            json_body={"invoice_id": invoice_id, "tenant_id": tenant_id},
            timeout_s=self._eval_timeout_s,
        )
        if resp.status_code >= 500:
            raise UpstreamToolError("UPSTREAM_UNAVAILABLE", f"gate /evaluate HTTP {resp.status_code}")
        resp.raise_for_status()
        d = resp.json()
        return GateEvaluation(
            decision=d["decision"],
            allowed_methods=list(d.get("allowed_methods", [])),
            verification_required=bool(d.get("verification_required", False)),
            intent_hash=d["intent_hash"],
            payee_account_id=d.get("payee_account_id"),
            amount_vnd=int(d["amount_vnd"]),
            channel=d["channel"],
            reasons=list(d.get("reasons", [])),
            evaluated_at=d["evaluated_at"],
        )

    def get_daily_budget(self, *, tenant_id: str, date_str: str) -> dict[str, Any]:
        resp = self._request(
            "GET",
            f"/budgets/{tenant_id}/{date_str}",
            timeout_s=self._eval_timeout_s,
        )
        if resp.status_code >= 500:
            raise UpstreamToolError("UPSTREAM_UNAVAILABLE", f"gate /budgets HTTP {resp.status_code}")
        resp.raise_for_status()
        return resp.json()

    def create_intent(self, *, invoice_id: str, approval_id: str) -> dict[str, Any]:
        resp = self._request(
            "POST",
            "/intents",
            json_body={"invoice_id": invoice_id, "approval_id": approval_id},
            timeout_s=self._execute_timeout_s,
        )
        if resp.status_code in {200, 201, 422}:
            return resp.json()
        raise UpstreamToolError("UPSTREAM_UNAVAILABLE", f"gate /intents HTTP {resp.status_code}")

    def get_intent(self, *, payment_intent_id: str) -> dict[str, Any] | None:
        resp = self._request(
            "GET",
            f"/intents/{payment_intent_id}",
            timeout_s=self._eval_timeout_s,
        )
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 404:
            return None
        raise UpstreamToolError("UPSTREAM_UNAVAILABLE", f"gate GET /intents/{payment_intent_id} HTTP {resp.status_code}")

    def execute_intent(self, *, payment_intent_id: str) -> dict[str, Any]:
        resp = self._request(
            "POST",
            f"/intents/{payment_intent_id}:execute",
            json_body={},
            timeout_s=self._execute_timeout_s,
        )
        if resp.status_code in {200, 422}:
            return resp.json()
        raise UpstreamToolError("UPSTREAM_UNAVAILABLE", f"gate :execute HTTP {resp.status_code}")

    def cancel_intent(self, *, payment_intent_id: str, reason: str) -> dict[str, Any]:
        resp = self._request(
            "POST",
            f"/intents/{payment_intent_id}:cancel",
            json_body={"reason": reason},
            timeout_s=self._eval_timeout_s,
        )
        if resp.status_code in {200, 409}:
            return resp.json()
        raise UpstreamToolError("UPSTREAM_UNAVAILABLE", f"gate :cancel HTTP {resp.status_code}")

    def list_intents(
        self, *, tenant_id: str, invoice_id: str | None = None, status: str | None = None
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"tenant_id": tenant_id}
        if invoice_id:
            params["invoice_id"] = invoice_id
        if status:
            params["status"] = status
        resp = self._request("GET", "/intents", params=params, timeout_s=self._eval_timeout_s)
        if resp.status_code >= 500:
            raise UpstreamToolError("UPSTREAM_UNAVAILABLE", f"gate GET /intents HTTP {resp.status_code}")
        resp.raise_for_status()
        body = resp.json()
        return list(body.get("items", [])) if isinstance(body, dict) else []
