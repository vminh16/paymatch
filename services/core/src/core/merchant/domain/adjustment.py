"""Pure deterministic AdjustmentRequest template builder (code-filled from DB/tool numbers, never LLM)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from core.risk.domain.aggregation import REASON_CODE_RULES


def _fmt_vnd(amount: int | None) -> str:
    if amount is None:
        return "0 đ"
    return f"{amount:,}".replace(",", ".") + " đ"


def build_adjustment_request_template(
    *,
    adjustment_request_id: str,
    tenant_name: str,
    invoice: Mapping[str, Any],
    vendor: Mapping[str, Any] | None,
    reason_code: str,
    price_check_items: Sequence[Mapping[str, Any]] = (),
    three_way_match: Mapping[str, Any] | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Build trusted AdjustmentRequest purely from DB & tool-computed numbers (D3)."""
    vendor_id = vendor["vendor_id"] if vendor else None
    vendor_name = vendor["name"] if vendor else f"NCC MST {invoice.get('seller_tax_id', '')}"
    symbol = invoice.get("symbol") or ""
    number = invoice.get("number") or ""
    issued_on = invoice.get("issued_on") or ""
    total_str = _fmt_vnd(invoice.get("total_vnd"))

    rule = REASON_CODE_RULES.get(reason_code)
    reason_label = rule.label_vi if rule else "sai lệch dữ liệu hóa đơn"

    subject = f"Yêu cầu điều chỉnh HĐĐT {symbol} số {number} — {reason_label.lower()}"

    detail_lines: list[str] = []
    cited_lines: list[str] = []

    for item in price_check_items:
        lid = item.get("line_id")
        if lid:
            cited_lines.append(lid)
        detail_lines.append(
            f"- SKU {item.get('sku')}: Hợp đồng quy định quy cách {item.get('pack_qty_contract')} "
            f"(đơn giá {item.get('unit_price_contract')} đ/đơn vị), "
            f"hóa đơn ghi quy cách {item.get('pack_qty_parsed') or 'chưa rõ'} "
            f"(đơn giá {item.get('unit_price_invoice')} đ/đơn vị, chênh lệch {item.get('delta_pct')}%)."
        )

    if three_way_match and not detail_lines:
        for ln in three_way_match.get("lines") or []:
            if not ln.get("within_norm"):
                if ln.get("line_id"):
                    cited_lines.append(ln["line_id"])
                detail_lines.append(
                    f"- SKU {ln.get('sku') or 'N/A'}: Số lượng hóa đơn {ln.get('invoice_quantity')}, "
                    f"phiếu nhập kho {ln.get('grn_quantity')}, chênh lệch {ln.get('delta_quantity')}."
                )

    if not detail_lines:
        detail_lines.append(f"- Lý do từ chối: {reason_label}.")
    if note:
        detail_lines.append(f"- Ghi chú bổ sung từ chủ chuỗi: {note}")

    body = (
        f"Kính gửi {vendor_name},\n\n"
        f"{tenant_name} đề nghị Quý công ty kiểm tra và xuất hóa đơn điều chỉnh cho "
        f"HĐĐT ký hiệu {symbol} số {number} (ngày {issued_on}, tổng tiền {total_str}):\n"
        + "\n".join(detail_lines)
        + "\n\nĐề nghị Quý công ty phản hồi và xuất hóa đơn điều chỉnh theo đúng hợp đồng/chứng từ giao nhận.\n"
        "Trân trọng."
    )

    return {
        "adjustment_request_id": adjustment_request_id,
        "invoice_id": invoice["invoice_id"],
        "to_vendor_id": vendor_id,
        "channel_hint": "email",
        "subject": subject,
        "body": body,
        "cited_lines": list(dict.fromkeys(cited_lines)),
    }
