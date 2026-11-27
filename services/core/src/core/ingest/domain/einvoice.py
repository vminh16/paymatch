"""Vietnamese e-invoice (QĐ 1233/QĐ-CT & prior TT78/QĐ 1450/1510/1271) XML parser and domain checks.

Spec references:
- docs/04-data/einvoice-xml.md §1–§4
- docs/05-api/schemas.md §1–§2
- docs/03-agents/agent-runtime.md §5a

Pure Python domain module using stdlib only (no I/O, no DB, no network).
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import re
from typing import Literal
import unicodedata
import xml.etree.ElementTree as ET
import xml.parsers.expat as expat_mod

ALLOWED_PBAN: frozenset[str] = frozenset({"2.0.0", "2.0.1", "2.1.0", "2.1.1"})
SUPPORTED_CURRENCY = "VND"

REASON_AMOUNT_MISMATCH = "AMOUNT_MISMATCH"
REASON_DUPLICATE_INVOICE = "DUPLICATE_INVOICE"
REASON_UNKNOWN_VENDOR = "UNKNOWN_VENDOR"

LineKind = Literal["goods_service", "promotion", "trade_discount", "note", "special_goods"]
UntrustedSource = Literal["invoice_xml", "email_body", "chat_message", "bot_reason", "ocr"]
BankAccountSource = Literal["nban_field", "ttkhac", "dlqrcode"]

_TCHAT_TO_KIND: dict[str, LineKind] = {
    "1": "goods_service",
    "2": "promotion",
    "3": "trade_discount",
    "4": "note",
    "5": "special_goods",
}

_TCHDON_TO_RELATION: dict[str, str] = {
    "1": "replace",
    "2": "adjust",
    "3": "replace_multiple",
    "4": "adjust_multiple",
    "5": "trade_discount",
}

_ADJUSTMENT_CODES: frozenset[str] = frozenset({"2", "4"})

# Normalized TTruong tokens indicating seller bank account number / bank name (einvoice-xml.md §4).
_BANK_ACCOUNT_NUMBER_KEYS: frozenset[str] = frozenset(
    {
        "sellerbankaccount",
        "sellerbankaccountno",
        "sellerbankaccountnumber",
        "bankaccount",
        "bankaccountno",
        "bankaccountnumber",
        "accountnumber",
        "accountno",
        "stk",
        "stknhang",
        "stknban",
        "sotk",
        "sotaikhoan",
        "sotaikhoannganhang",
        "sotaikhoannguoiban",
        "taikhoannganhang",
        "tknganhang",
    }
)

_BANK_NAME_KEYS: frozenset[str] = frozenset(
    {
        "sellerbankname",
        "bankname",
        "tnhang",
        "tennganhang",
        "tennganhangnguoiban",
        "nganhang",
    }
)

_BUYER_KEY_MARKERS: tuple[str, ...] = ("buyer", "nmua", "nguoimua", "customer", "khachhang")

_VAT_PERCENT_RE = re.compile(r"^(?:KHAC:)?\s*(\d+(?:\.\d+)?)%\s*$", re.IGNORECASE)
_UTF8_BOM = b"\xef\xbb\xbf"
_PLAIN_DECIMAL_RE = re.compile(r"[+-]?\d{1,15}(\.\d+)?")  # integer-part bound of schemas.md Decimal
_LINE_TOLERANCE_RATE = Decimal("0.0005")  # 0.05% per einvoice-xml.md §4 Tier 1
_ONE_VND = Decimal("1")
_HUNDRED = Decimal("100")


class InvoiceUnparseable(Exception):
    """Raised for 422 XML_UNPARSEABLE ingest rejections (einvoice-xml.md §4)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class UntrustedText:
    """Text authored by the seller or an external party (schemas.md §1)."""

    text: str
    provenance: Literal["untrusted"] = "untrusted"
    source: UntrustedSource = "invoice_xml"


@dataclass(frozen=True)
class BankAccountOnInvoice:
    """Bank account extracted from invoice XML — always untrusted, never a payee."""

    number: str
    bank_name: str
    source: BankAccountSource
    provenance: Literal["untrusted"] = "untrusted"


@dataclass(frozen=True)
class OtherInfoEntry:
    """Single TTKhac/TTin entry with parent scope context (einvoice-xml.md §3a, §4)."""

    scope: str
    field: str
    value: UntrustedText
    data_type: str | None = None
    line_position: int | None = None


@dataclass(frozen=True)
class VatBreakdownItem:
    """Single THTTLTSuat/LTSuat entry (schemas.md §2)."""

    vat_rate: str
    taxable_vnd: int
    vat_vnd: int | None


@dataclass(frozen=True)
class RelatedInvoice:
    """Related invoice reference from TTHDLQuan (einvoice-xml.md §3, §4; schemas.md §2)."""

    relation: str
    relation_code: str
    symbol: str | None
    number: str | None
    issued_on: str | None
    related_tax_id: str | None = None
    reason_code: str | None = None
    invoice_kind_code: str | None = None
    statement_number: str | None = None
    statement_date: str | None = None
    note: UntrustedText | None = None


@dataclass
class InvoiceLine:
    """Normalized invoice line (schemas.md §2)."""

    position: int
    kind: LineKind
    item_code: UntrustedText | None
    name: UntrustedText
    unit: UntrustedText | None
    quantity: str | None
    unit_price: str | None
    discount_vnd: int | None
    amount_vnd: int | None
    vat_rate: str | None
    arithmetic_ok: bool = True
    discount_rate: str | None = None
    _raw_discount: Decimal | None = field(default=None, repr=False, compare=False)
    _raw_amount: Decimal | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class UntrustedInvoiceData:
    """All seller-authored / untrusted fields separated from trusted numbers (schemas.md §2, einvoice-xml.md §4)."""

    seller_name: UntrustedText
    seller_address: UntrustedText
    seller_bank_account: BankAccountOnInvoice | None
    bank_accounts: list[BankAccountOnInvoice]
    payment_terms: UntrustedText | None
    other_info: list[OtherInfoEntry]
    related_invoice_note: UntrustedText | None = None
    store_hint: list[UntrustedText] = field(default_factory=list)
    item_names: list[UntrustedText] = field(default_factory=list)
    units: list[UntrustedText | None] = field(default_factory=list)


@dataclass(frozen=True)
class ArithmeticIssue:
    """Single arithmetic rule failure from tiers 1–3 (einvoice-xml.md §4)."""

    tier: Literal[1, 2, 3]
    code: str
    detail: str
    line_position: int | None = None
    vat_rate: str | None = None


@dataclass
class ParsedInvoice:
    """Structured invoice parsed from e-invoice XML with trusted numbers separated from untrusted text."""

    schema_version: str
    template_code: str
    series: str
    symbol: str
    number: str
    issued_on: str | None
    currency: str
    seller_tax_id: str
    buyer_tax_id: str
    subtotal_vnd: int | None
    vat_total_vnd: int | None
    total_vnd: int | None
    vat_breakdown: list[VatBreakdownItem]
    tax_authority_code: str | None
    einvoice_provider_tax_id: str | None
    related_invoice: RelatedInvoice | None
    lines: list[InvoiceLine]
    untrusted: UntrustedInvoiceData
    document_sha256: str
    total_discount_vnd: int = 0
    fees_total_vnd: int = 0
    non_taxable_deduction_vnd: int = 0
    other_deduction_vnd: int = 0
    has_totals: bool = True
    has_lines: bool = True
    has_subtotal: bool = True
    has_vat_total: bool = True


def document_sha256(xml_bytes: bytes) -> str:
    """Return lowercase hex SHA-256 of the raw immutable document bytes (einvoice-xml.md §4)."""
    return hashlib.sha256(xml_bytes).hexdigest()


def is_same_document(xml_bytes: bytes, existing_sha256s: Collection[str]) -> bool:
    """Pure idempotency check by raw file sha256 (einvoice-xml.md §4)."""
    return document_sha256(xml_bytes) in existing_sha256s


def duplicate_key(parsed: ParsedInvoice) -> tuple[str, str, str]:
    """Compute normalized business duplicate key (einvoice-xml.md §4).

    - seller_tax_id_norm: keep leading zeros and branch suffix -NNN.
    - symbol_norm: KHMSHDon + KHHDon uppercase without whitespace.
    - number_norm: integer-normalized SHDon ("00001234" == "1234"), fallback to stripped text.
    """
    seller_tax_id_norm = parsed.seller_tax_id.strip()
    symbol_norm = _normalize_symbol(parsed.template_code, parsed.series)
    number_raw = parsed.number.strip()
    if number_raw.isdigit():
        number_norm = str(int(number_raw))
    else:
        number_norm = number_raw
    return (seller_tax_id_norm, symbol_norm, number_norm)


def is_duplicate(
    parsed: ParsedInvoice,
    existing_keys: Collection[tuple[str, str, str]],
) -> bool:
    """Return True if parsed invoice's normalized duplicate key already exists in the tenant."""
    return duplicate_key(parsed) in existing_keys


def check_duplicate(
    parsed: ParsedInvoice,
    existing_keys: Collection[tuple[str, str, str]],
) -> str | None:
    """Pure duplicate check returning DUPLICATE_INVOICE or None (einvoice-xml.md §4)."""
    return REASON_DUPLICATE_INVOICE if is_duplicate(parsed, existing_keys) else None


def is_unknown_vendor(
    parsed: ParsedInvoice,
    known_vendor_tax_ids: Collection[str],
) -> bool:
    """Return True if seller_tax_id is not present in the tenant's vendor registry."""
    normalized_known = {tax_id.strip() for tax_id in known_vendor_tax_ids}
    return parsed.seller_tax_id.strip() not in normalized_known


def check_unknown_vendor(
    parsed: ParsedInvoice,
    known_vendor_tax_ids: Collection[str],
) -> str | None:
    """Pure unknown-vendor check returning UNKNOWN_VENDOR or None (einvoice-xml.md §4)."""
    return REASON_UNKNOWN_VENDOR if is_unknown_vendor(parsed, known_vendor_tax_ids) else None


def parse_einvoice(xml_bytes: bytes) -> ParsedInvoice:
    """Parse Vietnamese e-invoice XML bytes into a ParsedInvoice (einvoice-xml.md §3a, §4).

    Raises InvoiceUnparseable for all 422 XML_UNPARSEABLE cases in einvoice-xml.md §4.
    """
    if not xml_bytes:
        raise InvoiceUnparseable("empty XML payload")

    raw_sha256 = document_sha256(xml_bytes)
    cleaned_bytes = xml_bytes[len(_UTF8_BOM) :] if xml_bytes.startswith(_UTF8_BOM) else xml_bytes

    root = _parse_xml_strict(cleaned_bytes)

    hdon = _find_hdon(root)
    if hdon is None:
        raise InvoiceUnparseable("missing HDon element")

    dlhdon = _find_dlhdon(hdon)
    if dlhdon is None:
        raise InvoiceUnparseable("missing DLHDon element")

    ttchung = _child(dlhdon, "TTChung")
    if ttchung is None:
        raise InvoiceUnparseable("missing TTChung element")

    ndhdon = _child(dlhdon, "NDHDon")
    if ndhdon is None:
        raise InvoiceUnparseable("missing NDHDon element")

    schema_version = _child_text(ttchung, "PBan")
    if not schema_version or schema_version not in ALLOWED_PBAN:
        raise InvoiceUnparseable(f"unsupported PBan: {schema_version!r}")

    currency = _child_text(ttchung, "DVTTe")
    if currency != SUPPORTED_CURRENCY:
        raise InvoiceUnparseable(f"unsupported currency DVTTe: {currency!r}")

    template_code = _child_text(ttchung, "KHMSHDon")
    if not template_code:
        raise InvoiceUnparseable("missing KHMSHDon")

    series_raw = _child_text(ttchung, "KHHDon")
    if not series_raw:
        raise InvoiceUnparseable("missing KHHDon")
    series = re.sub(r"\s+", "", series_raw).upper()
    symbol = _normalize_symbol(template_code, series)

    number = _child_text(ttchung, "SHDon")
    if not number:
        raise InvoiceUnparseable("missing SHDon")

    issued_on = _child_text(ttchung, "NLap") or None
    payment_terms_text = _child_text(ttchung, "HTTToan")
    payment_terms = _untrusted(payment_terms_text) if payment_terms_text else None
    einvoice_provider_tax_id = _child_text(ttchung, "MSTTCGP") or None

    related_invoice = _parse_related_invoice(_child(ttchung, "TTHDLQuan"))
    is_adjustment = (
        related_invoice is not None and related_invoice.relation_code in _ADJUSTMENT_CODES
    )

    nban = _child(ndhdon, "NBan")
    if nban is None:
        raise InvoiceUnparseable("missing NBan element")

    seller_tax_id = _child_text(nban, "MST")
    if not seller_tax_id:
        raise InvoiceUnparseable("missing NBan/MST")

    seller_name = _untrusted(_child_text(nban, "Ten") or "")
    seller_address = _untrusted(_child_text(nban, "DChi") or "")

    nmua = _child(ndhdon, "NMua")
    buyer_tax_id = _child_text(nmua, "MST") if nmua is not None else ""
    buyer_tax_id = buyer_tax_id or ""

    other_info: list[OtherInfoEntry] = []
    other_info.extend(_collect_ttkhac(ttchung, scope="TTChung"))
    other_info.extend(_collect_ttkhac(nban, scope="NBan"))
    if nmua is not None:
        other_info.extend(_collect_ttkhac(nmua, scope="NMua"))

    dshhdvu = _child(ndhdon, "DSHHDVu")
    lines, line_other_info = _parse_lines(dshhdvu)
    other_info.extend(line_other_info)

    ttoan = _child(ndhdon, "TToan")
    if ttoan is not None:
        other_info.extend(_collect_ttkhac(ttoan, scope="TToan"))
    other_info.extend(_collect_ttkhac(dlhdon, scope="DLHDon"))

    (
        subtotal_vnd,
        vat_total_vnd,
        total_vnd,
        vat_breakdown,
        total_discount_vnd,
        fees_total_vnd,
        non_taxable_deduction_vnd,
        other_deduction_vnd,
        has_totals,
        has_subtotal,
        has_vat_total,
    ) = _parse_totals(ttoan, template_code=template_code, is_adjustment=is_adjustment)

    mccqt_text = _child_text(hdon, "MCCQT")
    tax_authority_code = mccqt_text or None

    dlqrcode_text = _child_text(hdon, "DLQRCode")

    bank_accounts = _extract_bank_accounts(
        nban=nban,
        other_info=other_info,
        dlqrcode=dlqrcode_text,
    )
    store_hint = _extract_store_hint(nmua=nmua, other_info=other_info)

    untrusted = UntrustedInvoiceData(
        seller_name=seller_name,
        seller_address=seller_address,
        seller_bank_account=bank_accounts[0] if bank_accounts else None,
        bank_accounts=bank_accounts,
        payment_terms=payment_terms,
        other_info=other_info,
        related_invoice_note=related_invoice.note if related_invoice is not None else None,
        store_hint=store_hint,
        item_names=[line.name for line in lines],
        units=[line.unit for line in lines],
    )

    parsed = ParsedInvoice(
        schema_version=schema_version,
        template_code=template_code,
        series=series,
        symbol=symbol,
        number=number,
        issued_on=issued_on,
        currency=currency,
        seller_tax_id=seller_tax_id,
        buyer_tax_id=buyer_tax_id,
        subtotal_vnd=subtotal_vnd,
        vat_total_vnd=vat_total_vnd,
        total_vnd=total_vnd,
        vat_breakdown=vat_breakdown,
        tax_authority_code=tax_authority_code,
        einvoice_provider_tax_id=einvoice_provider_tax_id,
        related_invoice=related_invoice,
        lines=lines,
        untrusted=untrusted,
        document_sha256=raw_sha256,
        total_discount_vnd=total_discount_vnd,
        fees_total_vnd=fees_total_vnd,
        non_taxable_deduction_vnd=non_taxable_deduction_vnd,
        other_deduction_vnd=other_deduction_vnd,
        has_totals=has_totals,
        has_lines=dshhdvu is not None and len(lines) > 0,
        has_subtotal=has_subtotal,
        has_vat_total=has_vat_total,
    )
    check_arithmetic(parsed)
    return parsed


def check_arithmetic(parsed: ParsedInvoice) -> list[ArithmeticIssue]:
    """Run tiers 1–3 Decimal arithmetic verification and update line.arithmetic_ok (einvoice-xml.md §4)."""
    issues: list[ArithmeticIssue] = []
    issues.extend(_check_tier1_lines(parsed))
    issues.extend(_check_tier2_vat_breakdown(parsed))
    issues.extend(_check_tier3_totals(parsed))
    return issues


def ingest_reason_codes(
    parsed: ParsedInvoice,
    *,
    known_vendor_tax_ids: Collection[str] | None = None,
    existing_duplicate_keys: Collection[tuple[str, str, str]] | None = None,
) -> list[str]:
    """Map ingest domain checks to ReasonCode values from agent-runtime.md §5a."""
    codes: list[str] = []
    if check_arithmetic(parsed):
        codes.append(REASON_AMOUNT_MISMATCH)
    if existing_duplicate_keys is not None and is_duplicate(parsed, existing_duplicate_keys):
        codes.append(REASON_DUPLICATE_INVOICE)
    if known_vendor_tax_ids is not None and is_unknown_vendor(parsed, known_vendor_tax_ids):
        codes.append(REASON_UNKNOWN_VENDOR)
    return codes


# ---------------------------------------------------------------------------
# XML navigation helpers (always by local-name, ignoring namespaces/prefixes)
# ---------------------------------------------------------------------------


def _forbid_doctype(*_args: object) -> None:
    raise InvoiceUnparseable("DOCTYPE declarations are forbidden")


def _forbid_entity(*_args: object) -> None:
    raise InvoiceUnparseable("ENTITY declarations are forbidden")


def _fix_expat_name(name: str) -> str:
    return f"{{{name}" if "}" in name else name


def _parse_xml_strict(xml_bytes: bytes) -> ET.Element:
    """Parse XML via expat + TreeBuilder with DTD/entity handlers disabled across all encodings."""
    builder = ET.TreeBuilder()
    parser = expat_mod.ParserCreate(namespace_separator="}")
    parser.buffer_text = True

    def _start(name: str, attrs: dict[str, str]) -> None:
        fixed_attrs = {_fix_expat_name(k): v for k, v in attrs.items()} if attrs else {}
        builder.start(_fix_expat_name(name), fixed_attrs)

    def _end(name: str) -> None:
        builder.end(_fix_expat_name(name))

    parser.StartElementHandler = _start
    parser.EndElementHandler = _end
    parser.CharacterDataHandler = builder.data
    parser.StartDoctypeDeclHandler = _forbid_doctype
    parser.EntityDeclHandler = _forbid_entity
    parser.UnparsedEntityDeclHandler = _forbid_entity
    parser.ExternalEntityRefHandler = _forbid_entity
    parser.NotationDeclHandler = _forbid_doctype

    try:
        parser.Parse(xml_bytes, True)
    except InvoiceUnparseable:
        raise
    except expat_mod.ExpatError as exc:
        raise InvoiceUnparseable(f"malformed XML: {exc}") from exc

    root = builder.close()
    if root is None:
        raise InvoiceUnparseable("malformed XML: empty document")
    return root


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    if ":" in tag:
        return tag.rsplit(":", 1)[1]
    return tag


def _child(parent: ET.Element, name: str) -> ET.Element | None:
    for el in parent:
        if _local_name(el.tag) == name:
            return el
    return None


def _children(parent: ET.Element, name: str) -> list[ET.Element]:
    return [el for el in parent if _local_name(el.tag) == name]


def _child_text(parent: ET.Element, name: str) -> str:
    el = _child(parent, name)
    if el is None or el.text is None:
        return ""
    return el.text.strip()


def _find_hdon(root: ET.Element) -> ET.Element | None:
    if _local_name(root.tag) == "HDon":
        return root
    # Support TDiep/DLieu/HDon envelope (QĐ 1233 Part I §IV.5) or nested wrapper.
    for el in root.iter():
        if _local_name(el.tag) == "HDon":
            return el
    return None


def _find_dlhdon(hdon: ET.Element) -> ET.Element | None:
    direct = _child(hdon, "DLHDon")
    if direct is not None:
        return direct
    dlieu = _child(hdon, "DLieu")
    if dlieu is not None:
        return _child(dlieu, "DLHDon")
    return None


def _untrusted(text: str) -> UntrustedText:
    return UntrustedText(text=text, provenance="untrusted", source="invoice_xml")


def _normalize_symbol(template_code: str, series: str) -> str:
    return re.sub(r"\s+", "", f"{template_code}{series}").upper()


# ---------------------------------------------------------------------------
# Decimal / money parsing helpers
# ---------------------------------------------------------------------------


def _parse_decimal(text: str, *, field_name: str) -> Decimal:
    # Decimal() also accepts "1E100" / "1_000"; those overflow quantize() and would escape as a 500, not a 422.
    if not _PLAIN_DECIMAL_RE.fullmatch(text):
        raise InvoiceUnparseable(f"invalid decimal in {field_name}: {text!r}")
    return Decimal(text)


def _optional_decimal(parent: ET.Element, name: str) -> Decimal | None:
    text = _child_text(parent, name)
    if not text:
        return None
    return _parse_decimal(text, field_name=name)


def _round_vnd(value: Decimal) -> int:
    return int(value.quantize(_ONE_VND, rounding=ROUND_HALF_UP))


def _format_decimal(value: Decimal) -> str:
    """Format Decimal as plain string matching schemas.md §1 without scientific notation."""
    if value == 0:
        return "0"
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


# ---------------------------------------------------------------------------
# Section parsers
# ---------------------------------------------------------------------------


def _parse_related_invoice(el: ET.Element | None) -> RelatedInvoice | None:
    if el is None:
        return None
    tchdon = _child_text(el, "TCHDon")
    if not tchdon:
        return None
    relation = _TCHDON_TO_RELATION.get(tchdon, f"unknown_{tchdon}")
    rel_template = _child_text(el, "KHMSHDCLQuan")
    rel_series = _child_text(el, "KHHDCLQuan")
    rel_symbol = _normalize_symbol(rel_template, rel_series) if (rel_template or rel_series) else None
    gchu_text = _child_text(el, "GChu")
    return RelatedInvoice(
        relation=relation,
        relation_code=tchdon,
        symbol=rel_symbol,
        number=_child_text(el, "SHDCLQuan") or None,
        issued_on=_child_text(el, "NLHDCLQuan") or None,
        related_tax_id=_child_text(el, "MSTCLQuan") or None,
        reason_code=_child_text(el, "LDDCTThe") or None,
        invoice_kind_code=_child_text(el, "LHDCLQuan") or None,
        statement_number=_child_text(el, "SBKCLQuan") or None,
        statement_date=_child_text(el, "NBKCLQuan") or None,
        note=_untrusted(gchu_text) if gchu_text else None,
    )


def _parse_lines(dshhdvu: ET.Element | None) -> tuple[list[InvoiceLine], list[OtherInfoEntry]]:
    if dshhdvu is None:
        return [], []

    lines: list[InvoiceLine] = []
    other_info: list[OtherInfoEntry] = []

    for index, hhdvu in enumerate(_children(dshhdvu, "HHDVu"), start=1):
        stt_text = _child_text(hhdvu, "STT")
        if stt_text and stt_text.isdigit():
            position = int(stt_text)
        else:
            position = index

        tchat_text = _child_text(hhdvu, "TChat")
        kind: LineKind = _TCHAT_TO_KIND.get(tchat_text, "goods_service")

        item_code_text = _child_text(hhdvu, "MHHDVu")
        name_text = _child_text(hhdvu, "THHDVu")
        unit_text = _child_text(hhdvu, "DVTinh")

        qty_dec = _optional_decimal(hhdvu, "SLuong")
        price_dec = _optional_decimal(hhdvu, "DGia")
        discount_rate_dec = _optional_decimal(hhdvu, "TLCKhau")
        discount_dec = _optional_decimal(hhdvu, "STCKhau")
        amount_dec = _optional_decimal(hhdvu, "ThTien")

        if kind == "note":
            amount_vnd = None
            raw_amount = None
        elif amount_dec is not None:
            amount_vnd = _round_vnd(amount_dec)
            raw_amount = amount_dec
        else:
            amount_vnd = None
            raw_amount = None

        discount_vnd = _round_vnd(discount_dec) if discount_dec is not None else None
        vat_rate = _child_text(hhdvu, "TSuat") or None

        lines.append(
            InvoiceLine(
                position=position,
                kind=kind,
                item_code=_untrusted(item_code_text) if item_code_text else None,
                name=_untrusted(name_text),
                unit=_untrusted(unit_text) if unit_text else None,
                quantity=_format_decimal(qty_dec) if qty_dec is not None else None,
                unit_price=_format_decimal(price_dec) if price_dec is not None else None,
                discount_vnd=discount_vnd,
                amount_vnd=amount_vnd,
                vat_rate=vat_rate,
                arithmetic_ok=True,
                discount_rate=_format_decimal(discount_rate_dec) if discount_rate_dec is not None else None,
                _raw_discount=discount_dec,
                _raw_amount=raw_amount,
            )
        )
        other_info.extend(_collect_ttkhac(hhdvu, scope="HHDVu", line_position=position))

    return lines, other_info


def _parse_totals(
    ttoan: ET.Element | None,
    *,
    template_code: str,
    is_adjustment: bool,
) -> tuple[
    int | None,
    int | None,
    int | None,
    list[VatBreakdownItem],
    int,
    int,
    int,
    int,
    bool,
    bool,
    bool,
]:
    if ttoan is None:
        if is_adjustment:
            return None, None, None, [], 0, 0, 0, 0, False, False, False
        raise InvoiceUnparseable("missing TToan/TgTTTBSo")

    total_dec = _optional_decimal(ttoan, "TgTTTBSo")
    if total_dec is None:
        if is_adjustment:
            return None, None, None, [], 0, 0, 0, 0, False, False, False
        raise InvoiceUnparseable("missing TToan/TgTTTBSo")
    total_vnd = _round_vnd(total_dec)

    total_discount_dec = _optional_decimal(ttoan, "TTCKTMai")
    total_discount_vnd = _round_vnd(total_discount_dec) if total_discount_dec is not None else 0

    non_taxable_deduction_dec = _optional_decimal(ttoan, "TGTKCThue")
    non_taxable_deduction_vnd = (
        _round_vnd(non_taxable_deduction_dec) if non_taxable_deduction_dec is not None else 0
    )

    other_deduction_dec = _optional_decimal(ttoan, "TGTKhac")
    other_deduction_vnd = _round_vnd(other_deduction_dec) if other_deduction_dec is not None else 0

    fees_total_dec = Decimal("0")
    dslphi = _child(ttoan, "DSLPhi")
    if dslphi is not None:
        for lphi in _children(dslphi, "LPhi"):
            tphi = _optional_decimal(lphi, "TPhi")
            if tphi is not None:
                fees_total_dec += tphi
    fees_total_vnd = _round_vnd(fees_total_dec)

    if template_code == "2":
        # Sales invoice (KHMSHDon = 2): no TgTCThue/TgTThue/THTTLTSuat per einvoice-xml.md §3a #9 & §4.
        return (
            total_vnd,
            0,
            total_vnd,
            [],
            total_discount_vnd,
            fees_total_vnd,
            non_taxable_deduction_vnd,
            other_deduction_vnd,
            True,
            False,
            False,
        )

    subtotal_dec = _optional_decimal(ttoan, "TgTCThue")
    vat_total_dec = _optional_decimal(ttoan, "TgTThue")
    has_subtotal = subtotal_dec is not None
    has_vat_total = vat_total_dec is not None
    subtotal_vnd = _round_vnd(subtotal_dec) if subtotal_dec is not None else None
    vat_total_vnd = _round_vnd(vat_total_dec) if vat_total_dec is not None else None

    vat_breakdown: list[VatBreakdownItem] = []
    thttltsuat = _child(ttoan, "THTTLTSuat")
    if thttltsuat is not None:
        for ltsuat in _children(thttltsuat, "LTSuat"):
            rate_text = _child_text(ltsuat, "TSuat")
            taxable_dec = _optional_decimal(ltsuat, "ThTien")
            vat_dec = _optional_decimal(ltsuat, "TThue")
            if taxable_dec is None:
                continue
            vat_breakdown.append(
                VatBreakdownItem(
                    vat_rate=rate_text,
                    taxable_vnd=_round_vnd(taxable_dec),
                    vat_vnd=_round_vnd(vat_dec) if vat_dec is not None else None,
                )
            )

    return (
        subtotal_vnd,
        vat_total_vnd,
        total_vnd,
        vat_breakdown,
        total_discount_vnd,
        fees_total_vnd,
        non_taxable_deduction_vnd,
        other_deduction_vnd,
        True,
        has_subtotal,
        has_vat_total,
    )


def _collect_ttkhac(
    parent: ET.Element,
    *,
    scope: str,
    line_position: int | None = None,
) -> list[OtherInfoEntry]:
    entries: list[OtherInfoEntry] = []
    for ttkhac in _children(parent, "TTKhac"):
        for ttin in _children(ttkhac, "TTin"):
            field_name = _child_text(ttin, "TTruong")
            data_type = _child_text(ttin, "KDLieu") or None
            value_text = _child_text(ttin, "DLieu")
            if not field_name and not value_text:
                continue
            entries.append(
                OtherInfoEntry(
                    scope=scope,
                    field=field_name,
                    value=_untrusted(value_text),
                    data_type=data_type,
                    line_position=line_position,
                )
            )
    return entries


# ---------------------------------------------------------------------------
# Untrusted bank account & store hint extraction (einvoice-xml.md §4)
# ---------------------------------------------------------------------------


def _normalize_key(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    ascii_only = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]", "", ascii_only.lower())


def _is_buyer_key(norm_key: str) -> bool:
    return any(marker in norm_key for marker in _BUYER_KEY_MARKERS)


def _extract_bank_accounts(
    *,
    nban: ET.Element,
    other_info: list[OtherInfoEntry],
    dlqrcode: str,
) -> list[BankAccountOnInvoice]:
    accounts: list[BankAccountOnInvoice] = []
    seen_numbers: dict[str, int] = {}

    def _add(number: str, bank_name: str, source: BankAccountSource) -> None:
        cleaned_number = number.strip()
        cleaned_bank = bank_name.strip()
        if not cleaned_number:
            return
        dedup_key = re.sub(r"\s+", "", cleaned_number)
        existing_idx = seen_numbers.get(dedup_key)
        if existing_idx is not None:
            # Prefer a populated bank_name if the earlier occurrence lacked one.
            if not accounts[existing_idx].bank_name and cleaned_bank:
                prev = accounts[existing_idx]
                accounts[existing_idx] = BankAccountOnInvoice(
                    number=prev.number,
                    bank_name=cleaned_bank,
                    source=prev.source,
                )
            return
        seen_numbers[dedup_key] = len(accounts)
        accounts.append(
            BankAccountOnInvoice(
                number=cleaned_number,
                bank_name=cleaned_bank,
                source=source,
            )
        )

    # Source 1: NBan/STKNHang + NBan/TNHang
    nban_stk = _child_text(nban, "STKNHang")
    nban_bank = _child_text(nban, "TNHang")
    if nban_stk:
        _add(nban_stk, nban_bank, "nban_field")

    # Source 2: Non-NMua TTKhac/TTin entries indicating seller bank account
    grouped_by_scope: dict[tuple[str, int | None], list[OtherInfoEntry]] = {}
    for entry in other_info:
        if entry.scope == "NMua":
            continue
        grouped_by_scope.setdefault((entry.scope, entry.line_position), []).append(entry)

    for scope_entries in grouped_by_scope.values():
        scope_bank_name = ""
        for entry in scope_entries:
            norm = _normalize_key(entry.field)
            if not _is_buyer_key(norm) and norm in _BANK_NAME_KEYS and entry.value.text:
                scope_bank_name = entry.value.text
                break
        for entry in scope_entries:
            norm = _normalize_key(entry.field)
            if not _is_buyer_key(norm) and norm in _BANK_ACCOUNT_NUMBER_KEYS and entry.value.text:
                _add(entry.value.text, scope_bank_name, "ttkhac")

    # Source 3: DLQRCode EMV/VietQR TLV payment fields (26-xx / 38-xx)
    for number, bank_name in _extract_qr_bank_accounts(dlqrcode):
        _add(number, bank_name, "dlqrcode")

    return accounts


def _parse_tlv(payload: str) -> dict[str, str] | None:
    """Parse an EMVCo / VietQR TLV string strictly; return None if not valid TLV."""
    if len(payload) < 4:
        return None
    pos = 0
    total_len = len(payload)
    parsed: dict[str, str] = {}
    while pos < total_len:
        if pos + 4 > total_len:
            return None
        tag = payload[pos : pos + 2]
        length_str = payload[pos + 2 : pos + 4]
        if not (tag.isdigit() and length_str.isdigit()):
            return None
        length = int(length_str)
        val_start = pos + 4
        val_end = val_start + length
        if val_end > total_len:
            return None
        parsed[tag] = payload[val_start:val_end]
        pos = val_end
    return parsed if parsed else None


def _extract_qr_bank_accounts(dlqrcode: str) -> list[tuple[str, str]]:
    """Extract (account_number, bank_bin_or_name) from EMV/VietQR TLV tags 26 and 38."""
    if not dlqrcode:
        return []
    top = _parse_tlv(dlqrcode.strip())
    if not top:
        return []

    found: list[tuple[str, str]] = []
    for tag in ("38", "26"):
        block = top.get(tag)
        if not block:
            continue
        sub = _parse_tlv(block)
        if not sub:
            continue
        beneficiary = sub.get("01")
        if not beneficiary:
            continue
        nested = _parse_tlv(beneficiary)
        if nested and nested.get("01"):
            # Standard VietQR 38 -> 01 -> {00: bank BIN, 01: account number}
            found.append((nested["01"], nested.get("00", "")))
        else:
            # Flat payment tag 26/38 -> {00: bank/AID, 01: account number}
            found.append((beneficiary, sub.get("00", "")))
    return found


def _extract_store_hint(
    *,
    nmua: ET.Element | None,
    other_info: list[OtherInfoEntry],
) -> list[UntrustedText]:
    hints: list[UntrustedText] = []
    if nmua is not None:
        buyer_addr = _child_text(nmua, "DChi")
        if buyer_addr:
            hints.append(_untrusted(buyer_addr))
    for entry in other_info:
        if entry.scope == "NMua" and entry.value.text:
            hints.append(entry.value)
    return hints


# ---------------------------------------------------------------------------
# Arithmetic verification: Tiers 1–3 (einvoice-xml.md §4)
# ---------------------------------------------------------------------------


def _parse_vat_rate_fraction(vat_rate: str | None) -> Decimal | None:
    if not vat_rate:
        return None
    match = _VAT_PERCENT_RE.match(vat_rate.strip())
    if not match:
        return None
    return Decimal(match.group(1)) / _HUNDRED


def _check_tier1_lines(parsed: ParsedInvoice) -> list[ArithmeticIssue]:
    issues: list[ArithmeticIssue] = []
    is_adjustment = (
        parsed.related_invoice is not None
        and parsed.related_invoice.relation_code in _ADJUSTMENT_CODES
    )

    for line in parsed.lines:
        # Skip conditions (einvoice-xml.md §4 Tier 1)
        if line.kind in ("promotion", "note"):
            line.arithmetic_ok = True
            continue
        if line.quantity is None or line.unit_price is None:
            line.arithmetic_ok = True
            continue

        qty = Decimal(line.quantity)
        price = Decimal(line.unit_price)
        actual = (
            line._raw_amount
            if line._raw_amount is not None
            else (Decimal(line.amount_vnd) if line.amount_vnd is not None else None)
        )

        if actual is None:
            line.arithmetic_ok = False
            issues.append(
                ArithmeticIssue(
                    tier=1,
                    code="LINE_AMOUNT_MISSING",
                    detail=f"line {line.position}: missing ThTien",
                    line_position=line.position,
                )
            )
            continue

        if is_adjustment and qty == 0 and price == 0 and actual != 0:
            line.arithmetic_ok = True
            continue

        gross = qty * price
        if line._raw_discount is not None:
            discount = line._raw_discount
        elif line.discount_vnd is not None:
            discount = Decimal(line.discount_vnd)
        elif line.discount_rate is not None:
            discount = gross * Decimal(line.discount_rate) / _HUNDRED
        else:
            discount = Decimal("0")

        expected = gross - discount
        tolerance = max(_ONE_VND, _LINE_TOLERANCE_RATE * abs(actual))
        diff = abs(expected - actual)
        if diff > tolerance:
            line.arithmetic_ok = False
            issues.append(
                ArithmeticIssue(
                    tier=1,
                    code="LINE_AMOUNT_MISMATCH",
                    detail=(
                        f"line {line.position}: expected {expected}, got {actual} "
                        f"(diff {diff} > tolerance {tolerance})"
                    ),
                    line_position=line.position,
                )
            )
        else:
            line.arithmetic_ok = True

    return issues


def _check_tier2_vat_breakdown(parsed: ParsedInvoice) -> list[ArithmeticIssue]:
    issues: list[ArithmeticIssue] = []
    if not parsed.vat_breakdown or parsed.template_code == "2" or not parsed.has_totals:
        return issues

    has_trade_discount_line = any(line.kind == "trade_discount" for line in parsed.lines)
    check_line_sums = (
        parsed.has_lines
        and parsed.total_discount_vnd == 0
        and not has_trade_discount_line
    )

    line_sums_by_rate: dict[str, Decimal] = {}
    if check_line_sums:
        for line in parsed.lines:
            if line.amount_vnd is None:
                continue
            rate_key = (line.vat_rate or "").strip().upper()
            line_amount = (
                line._raw_amount if line._raw_amount is not None else Decimal(line.amount_vnd)
            )
            line_sums_by_rate[rate_key] = line_sums_by_rate.get(rate_key, Decimal("0")) + line_amount

    total_taxable = Decimal("0")
    total_vat = Decimal("0")
    for entry in parsed.vat_breakdown:
        taxable = Decimal(entry.taxable_vnd)
        total_taxable += taxable
        if entry.vat_vnd is not None:
            total_vat += Decimal(entry.vat_vnd)

        rate_fraction = _parse_vat_rate_fraction(entry.vat_rate)
        if rate_fraction is not None and entry.vat_vnd is not None:
            expected_vat = (taxable * rate_fraction).quantize(_ONE_VND, rounding=ROUND_HALF_UP)
            actual_vat = Decimal(entry.vat_vnd)
            if abs(expected_vat - actual_vat) > _ONE_VND:
                issues.append(
                    ArithmeticIssue(
                        tier=2,
                        code="VAT_RATE_TAX_MISMATCH",
                        detail=(
                            f"vat_rate {entry.vat_rate!r}: expected tax {expected_vat}, "
                            f"got {actual_vat}"
                        ),
                        vat_rate=entry.vat_rate,
                    )
                )

        if check_line_sums:
            rate_key = entry.vat_rate.strip().upper()
            lines_sum = line_sums_by_rate.get(rate_key, Decimal("0"))
            if abs(lines_sum - taxable) > _ONE_VND:
                issues.append(
                    ArithmeticIssue(
                        tier=2,
                        code="VAT_RATE_LINE_SUM_MISMATCH",
                        detail=(
                            f"vat_rate {entry.vat_rate!r}: line sum {lines_sum}, "
                            f"LTSuat ThTien {taxable}"
                        ),
                        vat_rate=entry.vat_rate,
                    )
                )

    if parsed.subtotal_vnd is not None and abs(total_taxable - Decimal(parsed.subtotal_vnd)) > _ONE_VND:
        issues.append(
            ArithmeticIssue(
                tier=2,
                code="VAT_BREAKDOWN_SUBTOTAL_MISMATCH",
                detail=f"sum(LTSuat/ThTien)={total_taxable} != TgTCThue={parsed.subtotal_vnd}",
            )
        )

    if (
        parsed.has_vat_total
        and parsed.vat_total_vnd is not None
        and abs(total_vat - Decimal(parsed.vat_total_vnd)) > _ONE_VND
    ):
        issues.append(
            ArithmeticIssue(
                tier=2,
                code="VAT_BREAKDOWN_TAX_MISMATCH",
                detail=f"sum(LTSuat/TThue)={total_vat} != TgTThue={parsed.vat_total_vnd}",
            )
        )

    return issues


def _check_tier3_totals(parsed: ParsedInvoice) -> list[ArithmeticIssue]:
    issues: list[ArithmeticIssue] = []
    is_adjustment = (
        parsed.related_invoice is not None
        and parsed.related_invoice.relation_code in _ADJUSTMENT_CODES
    )

    if not parsed.has_totals or parsed.total_vnd is None:
        if is_adjustment:
            return issues
        issues.append(
            ArithmeticIssue(
                tier=3,
                code="TOTAL_MISSING",
                detail="missing TToan/TgTTTBSo",
            )
        )
        return issues

    total = Decimal(parsed.total_vnd)

    # Sales invoice (KHMSHDon = 2): no TgTCThue/TgTThue
    if parsed.template_code == "2":
        if (
            parsed.has_lines
            and parsed.total_discount_vnd == 0
            and parsed.fees_total_vnd == 0
            and parsed.other_deduction_vnd == 0
        ):
            line_sum = sum(
                (
                    line._raw_amount if line._raw_amount is not None else Decimal(line.amount_vnd)
                    for line in parsed.lines
                    if line.amount_vnd is not None
                ),
                Decimal("0"),
            )
            if abs(line_sum - total) > _ONE_VND:
                issues.append(
                    ArithmeticIssue(
                        tier=3,
                        code="SALES_TOTAL_MISMATCH",
                        detail=f"sum(ThTien)={line_sum} != TgTTTBSo={total}",
                    )
                )
        return issues

    # VAT and other invoices that carry TgTCThue & TgTThue (e.g. KHMSHDon = 1, 5, ...)
    if parsed.subtotal_vnd is None or parsed.vat_total_vnd is None:
        issues.append(
            ArithmeticIssue(
                tier=3,
                code="SUBTOTAL_OR_VAT_MISSING",
                detail="missing TgTCThue or TgTThue on VAT invoice",
            )
        )
        return issues

    subtotal = Decimal(parsed.subtotal_vnd)
    vat_total = Decimal(parsed.vat_total_vnd)
    total_discount = Decimal(parsed.total_discount_vnd)
    fees = Decimal(parsed.fees_total_vnd)
    non_taxable_deduction = Decimal(parsed.non_taxable_deduction_vnd)
    other_deduction = Decimal(parsed.other_deduction_vnd)

    has_adjustments = any(
        val != 0 for val in (total_discount, fees, non_taxable_deduction, other_deduction)
    )

    if not has_adjustments:
        # Exact 0-dong tolerance per einvoice-xml.md §4 Tier 3
        if subtotal + vat_total != total:
            issues.append(
                ArithmeticIssue(
                    tier=3,
                    code="TOTAL_MISMATCH",
                    detail=f"TgTCThue({subtotal}) + TgTThue({vat_total}) != TgTTTBSo({total})",
                )
            )
        return issues

    branch_a = subtotal + vat_total + fees - non_taxable_deduction - other_deduction
    if abs(branch_a - total) <= _ONE_VND:
        return issues

    if total_discount > 0:
        branch_b = (
            subtotal - total_discount + vat_total + fees - non_taxable_deduction - other_deduction
        )
        if abs(branch_b - total) <= _ONE_VND:
            return issues

    issues.append(
        ArithmeticIssue(
            tier=3,
            code="TOTAL_MISMATCH",
            detail=(
                f"total mismatch with adjustments: subtotal={subtotal}, vat={vat_total}, "
                f"discount={total_discount}, fees={fees}, "
                f"non_taxable_deduction={non_taxable_deduction}, "
                f"other_deduction={other_deduction}, total={total}"
            ),
        )
    )
    return issues
