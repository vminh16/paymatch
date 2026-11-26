"""HTTP adapter implementing InvoiceSourcePort against sim-world (/sim/inbox, /sim/bills)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import httpx

from core.ingest.application.poller import InboxAttachment, InboxMessage, UtilityBill
from core.shared.errors import ProblemError


class SimWorldInvoiceSourceAdapter:
    """Reads /sim/inbox/messages and /sim/bills over HTTP using X-Service-Key with bounded streaming downloads (I10)."""

    def __init__(
        self,
        sim_url: str,
        service_key: str = "",
        *,
        client: httpx.Client | None = None,
        timeout_s: float = 3.0,
        max_invoice_bytes: int = 5 * 1024 * 1024,
    ) -> None:
        self._sim_url = sim_url.rstrip("/")
        self._service_key = service_key
        self._client = client
        self._timeout_s = timeout_s
        self._max_invoice_bytes = max_invoice_bytes

    def _headers(self) -> dict[str, str]:
        return {"X-Service-Key": self._service_key} if self._service_key else {}

    def _get(self, path: str, params: dict[str, Any] | None = None) -> httpx.Response:
        url = f"{self._sim_url}{path}"
        if self._client is not None:
            resp = self._client.get(url, params=params, headers=self._headers(), timeout=self._timeout_s)
        else:
            resp = httpx.get(url, params=params, headers=self._headers(), timeout=self._timeout_s)
        resp.raise_for_status()
        return resp

    def _get_bytes_bounded(self, path: str) -> bytes:
        url = f"{self._sim_url}{path}"
        limit = self._max_invoice_bytes
        buf = bytearray()
        stream_ctx = (
            self._client.stream("GET", url, headers=self._headers(), timeout=self._timeout_s)
            if self._client is not None
            else httpx.stream("GET", url, headers=self._headers(), timeout=self._timeout_s)
        )
        with stream_ctx as resp:
            resp.raise_for_status()
            for chunk in resp.iter_bytes(chunk_size=65536):
                buf.extend(chunk)
                if len(buf) > limit:
                    raise ProblemError(
                        413,
                        "PAYLOAD_TOO_LARGE",
                        "Attachment exceeds maximum size",
                        f"Tệp đính kèm từ sim-world vượt quá {limit} bytes.",
                    )
        return bytes(buf)

    def list_inbox_messages(
        self, mailbox: str, after: str | None = None
    ) -> tuple[list[InboxMessage], str | None]:
        params: dict[str, Any] = {"mailbox": mailbox}
        if after:
            params["after"] = after
        data = self._get("/inbox/messages", params=params).json()
        out: list[InboxMessage] = []
        for item in data.get("items", []):
            attachments: list[InboxAttachment] = []
            for att in item.get("attachments", []):
                try:
                    raw = self._get_bytes_bounded(
                        f"/inbox/messages/{item['message_id']}/attachments/{att['attachment_id']}"
                    )
                except ProblemError:
                    # Skip oversized attachment without stalling other messages
                    continue
                attachments.append(
                    InboxAttachment(
                        attachment_id=att["attachment_id"],
                        filename=att["filename"],
                        content_type=att["content_type"],
                        raw_bytes=raw,
                    )
                )
            out.append(
                InboxMessage(
                    message_id=item["message_id"],
                    from_address=item["from"],
                    subject=item["subject"],
                    body_text=item["body_text"],
                    received_at=datetime.fromisoformat(item["received_at"].replace("Z", "+00:00")),
                    attachments=tuple(attachments),
                )
            )
        return out, data.get("next_cursor")

    def list_bills(
        self, wallet_id: str, after: str | None = None
    ) -> tuple[list[UtilityBill], str | None]:
        params: dict[str, Any] = {"wallet_id": wallet_id}
        if after:
            params["after"] = after
        data = self._get("/bills", params=params).json()
        out: list[UtilityBill] = []
        for item in data.get("items", []):
            out.append(
                UtilityBill(
                    bill_id=item["bill_id"],
                    provider=item["provider"],
                    customer_code=item["customer_code"],
                    store_ref=item["store_ref"],
                    period=item["period"],
                    amount_vnd=int(item["amount_vnd"]),
                    readings=item.get("readings") or {},
                    xml_attachment_id=item.get("xml_attachment_id"),
                    due_date=date.fromisoformat(item["due_date"]) if item.get("due_date") else None,
                    period_start=(
                        date.fromisoformat(item["period_start"]) if item.get("period_start") else None
                    ),
                    period_end=(
                        date.fromisoformat(item["period_end"]) if item.get("period_end") else None
                    ),
                    total_usage=item.get("total_usage"),
                    usage_unit=item.get("usage_unit"),
                    subtotal_vnd=item.get("subtotal_vnd"),
                    vat_total_vnd=item.get("vat_total_vnd"),
                    statement_no=item.get("statement_no"),
                )
            )
        return out, data.get("next_cursor")

    def fetch_bill_document(self, bill_id: str) -> bytes | None:
        try:
            return self._get_bytes_bounded(f"/bills/{bill_id}/document")
        except ProblemError:
            return None
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise
