"""Pure domain numerical calculations for price_check, three_way_match, and utility_baseline.

All money/price/quantity math uses Decimal (never float), ensuring invariant #7 (money/numbers computed by code).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

_QUANT6 = Decimal("0.000001")
_ONE = Decimal("1")
_HUNDRED = Decimal("100")

# Patterns to extract pack quantity from Vietnamese invoice line text / unit, e.g.:
# "thùng 800 cái", "800 cái/thùng", "gói 1kg", "chai 750ml", "bao 20kg", "lốc 12 hộp", "hộp 24 gói"
_PACK_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(thùng|hộp|lốc|túi|bịch|bao|két|cây|vỉ|cuộn|set|bộ|xô|can)\s*[:x×]?\s*(\d+(?:[.,]\d+)?)\s*(?:cái|ly|chiếc|ống|hộp|gói|chai|lon|kg|g|gr|gam|ml|l|lít|tờ|cuộn|viên|bịch|túi)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"(\d+(?:[.,]\d+)?)\s*(?:cái|ly|chiếc|ống|hộp|gói|chai|lon|tờ|viên)\s*/\s*(?:thùng|hộp|lốc|túi|bịch|bao|két|cây|vỉ|cuộn|set|bộ)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:quy\s*cách|qc)\s*[:=]?\s*(\d+(?:[.,]\d+)?)",
        re.IGNORECASE,
    ),
)


def _pick_pack_match(pattern: re.Pattern[str], text: str, pack_spec: str) -> re.Match[str] | None:
    """Prefer the match on the same container as the contract ("thùng" in "thùng 12 hộp x 1L"), else the first.

    shortcut: keyword regexes over seller free text; replace with the general line-spec parser (see
    docs/03-agents/tools.md price_check) before onboarding vendors outside the demo dataset.
    """
    matches = list(pattern.finditer(text))
    if not matches:
        return None
    container = (pack_spec.split() or [""])[0].lower()
    if pattern.groups >= 2 and container:
        for m in matches:
            if m.group(1).lower() == container:
                return m
    return matches[0]


def fmt_dec6(value: Decimal) -> str:
    q = value.quantize(_QUANT6, rounding=ROUND_HALF_UP)
    return format(q, "f")


def _to_dec(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def parse_pack_qty(
    *,
    line_name: str,
    line_unit: str | None,
    base_unit: str,
    pack_qty_contract: Decimal,
    pack_spec: str = "",
) -> Decimal | None:
    """Parse pack quantity from invoice line name/unit using deterministic regexes.

    If contract pack_qty == 1 and unit matches base_unit (e.g. 'kg' == 'kg'), return 1.
    If an explicit pack count (e.g. 'thùng 800 cái') is found in text, return that Decimal.
    """
    combined = f"{line_name or ''} {line_unit or ''}"
    for pattern in _PACK_PATTERNS:
        m = _pick_pack_match(pattern, combined, pack_spec)
        if m:
            raw = m.group(m.lastindex or 1)
            # Handle Vietnamese thousands separator like "1.000" when 3 digits follow dot
            if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", raw):
                raw = raw.replace(".", "")
            else:
                raw = raw.replace(",", ".")
            parsed = _to_dec(raw)
            if parsed is not None and parsed > 0:
                return parsed

    # If contract is per single base unit (pack_qty == 1) and unit matches base_unit or no container unit
    unit_norm = (line_unit or "").strip().lower()
    base_norm = (base_unit or "").strip().lower()
    if pack_qty_contract == _ONE:
        if not unit_norm or unit_norm == base_norm or base_norm in unit_norm:
            return _ONE
    # A count stated next to the base unit (e.g. "1.000 cái", "12 hộp"); an unstated count stays None, which the
    # floor treats as PACK_SIZE_CHANGED (internal-api.md §3).
    m_base = re.search(rf"(\d+(?:[.,]\d+)?)\s*{re.escape(base_norm)}\b", combined, re.IGNORECASE)
    if m_base and base_norm:
        raw = m_base.group(1)
        if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", raw):
            raw = raw.replace(".", "")
        else:
            raw = raw.replace(",", ".")
        parsed = _to_dec(raw)
        if parsed is not None and parsed > 0:
            return parsed

    if pack_qty_contract == _ONE:
        return _ONE
    return None


def compute_price_check_item(
    *,
    line_id: str,
    sku: str,
    contract_item_id: str | None,
    line_name: str,
    line_unit: str | None,
    line_quantity: str | None,
    line_unit_price: str | None,
    line_amount_vnd: int | None,
    base_unit: str,
    pack_qty_contract_str: str,
    unit_price_contract_str: str,
    pack_spec: str = "",
) -> dict[str, Any]:
    """Compute exact Decimal unit_price_invoice (per base unit), unit_price_contract, delta_pct, and pack_qty_parsed."""
    pack_contract = _to_dec(pack_qty_contract_str) or _ONE
    price_contract = _to_dec(unit_price_contract_str) or Decimal("0")
    qty = _to_dec(line_quantity)
    raw_unit_price = _to_dec(line_unit_price)

    pack_parsed = parse_pack_qty(
        line_name=line_name,
        line_unit=line_unit,
        base_unit=base_unit,
        pack_qty_contract=pack_contract,
        pack_spec=pack_spec,
    )

    # Effective invoice price per pack/line unit
    if raw_unit_price is not None:
        line_price = raw_unit_price
    elif line_amount_vnd is not None and qty is not None and qty != 0:
        line_price = Decimal(line_amount_vnd) / qty
    else:
        line_price = Decimal("0")

    divisor = pack_parsed if (pack_parsed is not None and pack_parsed > 0) else pack_contract
    unit_price_invoice = line_price / divisor if divisor > 0 else line_price
    unit_price_contract = price_contract / pack_contract if pack_contract > 0 else price_contract

    if unit_price_contract > 0:
        delta_pct = ((unit_price_invoice - unit_price_contract) / unit_price_contract) * _HUNDRED
    else:
        delta_pct = Decimal("0")

    # Small rounding noise <= 0.01% treated as 0.000000 so legitimate VND rounding never triggers false PRICE_ABOVE_CONTRACT
    if abs(delta_pct) <= Decimal("0.01"):
        delta_pct = Decimal("0")

    return {
        "line_id": line_id,
        "sku": sku,
        "contract_item_id": contract_item_id,
        "unit_price_invoice": fmt_dec6(unit_price_invoice),
        "unit_price_contract": fmt_dec6(unit_price_contract),
        "delta_pct": fmt_dec6(delta_pct),
        "pack_qty_contract": fmt_dec6(pack_contract),
        "pack_qty_parsed": fmt_dec6(pack_parsed) if pack_parsed is not None else None,
    }


def compute_three_way_match(
    *,
    invoice_lines: Sequence[Mapping[str, Any]],
    purchase_order: Mapping[str, Any] | None,
    goods_receipts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Deterministic PO <-> GRN <-> Invoice 3-way match."""
    if purchase_order is None:
        return {
            "matched": False,
            "missing_goods_receipt": len(goods_receipts) == 0,
            "quantity_above_norm": False,
            "purchase_order_id": None,
            "goods_receipt_ids": [g["goods_receipt_id"] for g in goods_receipts],
            "lines": [
                {
                    "line_id": ln["line_id"],
                    "sku": (ln.get("item_code") or {}).get("text") if isinstance(ln.get("item_code"), Mapping) else None,
                    "po_quantity": None,
                    "grn_quantity": None,
                    "invoice_quantity": ln.get("quantity"),
                    "delta_quantity": None,
                    "within_norm": False,
                }
                for ln in invoice_lines
                if ln.get("kind") in {"goods_service", "special_goods"}
            ],
        }

    po_by_sku: dict[str, Decimal] = {}
    for pl in purchase_order.get("lines") or []:
        sku = pl.get("sku")
        q = _to_dec(pl.get("quantity")) or Decimal("0")
        if sku:
            po_by_sku[sku] = po_by_sku.get(sku, Decimal("0")) + q

    grn_by_sku: dict[str, Decimal] = {}
    for grn in goods_receipts:
        for gl in grn.get("lines") or []:
            sku = gl.get("sku")
            q = _to_dec(gl.get("quantity_received")) or Decimal("0")
            if sku:
                grn_by_sku[sku] = grn_by_sku.get(sku, Decimal("0")) + q

    missing_grn = len(goods_receipts) == 0
    qty_above = False
    out_lines: list[dict[str, Any]] = []
    po_skus = list(po_by_sku.keys())

    for idx, ln in enumerate(invoice_lines):
        if ln.get("kind") not in {"goods_service", "special_goods"}:
            continue
        item_code_obj = ln.get("item_code")
        sku = item_code_obj.get("text") if isinstance(item_code_obj, Mapping) else None
        if not sku and len(po_skus) == 1:
            sku = po_skus[0]
        elif not sku and idx < len(po_skus):
            sku = po_skus[idx]

        inv_qty = _to_dec(ln.get("quantity"))
        po_qty = po_by_sku.get(sku) if sku else None
        grn_qty = grn_by_sku.get(sku) if (sku and not missing_grn) else None

        delta: Decimal | None = None
        within_norm = True
        if inv_qty is not None:
            ref_qty = grn_qty if grn_qty is not None else po_qty
            if ref_qty is not None:
                delta = inv_qty - ref_qty
                if delta > Decimal("0"):
                    within_norm = False
                    qty_above = True
            elif missing_grn:
                within_norm = False

        out_lines.append(
            {
                "line_id": ln["line_id"],
                "sku": sku,
                "po_quantity": fmt_dec6(po_qty) if po_qty is not None else None,
                "grn_quantity": fmt_dec6(grn_qty) if grn_qty is not None else None,
                "invoice_quantity": fmt_dec6(inv_qty) if inv_qty is not None else None,
                "delta_quantity": fmt_dec6(delta) if delta is not None else None,
                "within_norm": within_norm,
            }
        )

    matched = (not missing_grn) and (not qty_above) and all(x["within_norm"] for x in out_lines)
    return {
        "matched": matched,
        "missing_goods_receipt": missing_grn,
        "quantity_above_norm": qty_above,
        "purchase_order_id": purchase_order["purchase_order_id"],
        "goods_receipt_ids": [g["goods_receipt_id"] for g in goods_receipts],
        "lines": out_lines,
    }


def _median_decimal(values: list[Decimal]) -> Decimal:
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2 == 1:
        return s[mid]
    return (s[mid - 1] + s[mid]) / Decimal("2")


def compute_utility_baseline(
    *,
    store_id: str | None,
    utility_type: str | None,
    months: int,
    historical_readings: Sequence[Mapping[str, Any]],
    current_usage_str: str | None,
    current_amount_vnd: int | None,
) -> dict[str, Any]:
    """Compute 12-month median and normal range [0.6x..1.5x median] for utility bills."""
    reading_ids = [r["reading_id"] for r in historical_readings]
    if not historical_readings:
        return {
            "store_id": store_id,
            "utility_type": utility_type,
            "months": months,
            "median_usage": None,
            "normal_min_usage": None,
            "normal_max_usage": None,
            "median_amount_vnd": None,
            "normal_min_vnd": None,
            "normal_max_vnd": None,
            "current_usage": fmt_dec6(_to_dec(current_usage_str)) if _to_dec(current_usage_str) is not None else None,
            "current_amount_vnd": current_amount_vnd,
            "ratio_to_median": None,
            "out_of_range": False,
            "reading_ids": reading_ids,
        }

    usages = [_to_dec(r["total_usage"]) or Decimal("0") for r in historical_readings]
    amounts = [Decimal(int(r["total_vnd"])) for r in historical_readings]

    med_usage = _median_decimal(usages)
    med_amount = _median_decimal(amounts)

    low_factor = Decimal("0.60")
    high_factor = Decimal("1.50")

    min_usage = med_usage * low_factor
    max_usage = med_usage * high_factor
    min_vnd = int((med_amount * low_factor).quantize(_ONE, rounding=ROUND_HALF_UP))
    max_vnd = int((med_amount * high_factor).quantize(_ONE, rounding=ROUND_HALF_UP))
    med_vnd_int = int(med_amount.quantize(_ONE, rounding=ROUND_HALF_UP))

    cur_usage = _to_dec(current_usage_str)
    ratio: Decimal | None = None
    out_of_range = False

    if cur_usage is not None and med_usage > 0:
        ratio = cur_usage / med_usage
        if cur_usage > max_usage or cur_usage < min_usage:
            out_of_range = True
    elif current_amount_vnd is not None and med_amount > 0:
        ratio = Decimal(current_amount_vnd) / med_amount
        if current_amount_vnd > max_vnd or current_amount_vnd < min_vnd:
            out_of_range = True

    return {
        "store_id": store_id,
        "utility_type": utility_type,
        "months": months,
        "median_usage": fmt_dec6(med_usage),
        "normal_min_usage": fmt_dec6(min_usage),
        "normal_max_usage": fmt_dec6(max_usage),
        "median_amount_vnd": med_vnd_int,
        "normal_min_vnd": min_vnd,
        "normal_max_vnd": max_vnd,
        "current_usage": fmt_dec6(cur_usage) if cur_usage is not None else None,
        "current_amount_vnd": current_amount_vnd,
        "ratio_to_median": fmt_dec6(ratio) if ratio is not None else None,
        "out_of_range": out_of_range,
        "reading_ids": reading_ids,
    }
