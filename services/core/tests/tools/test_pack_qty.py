"""parse_pack_qty on real demo line names (price_check, internal-api.md §3)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.tools.domain.calculations import parse_pack_qty


@pytest.mark.parametrize(
    ("line_name", "pack_spec", "pack_qty_contract", "expected"),
    [
        # Inner pack ("hộp 1L") must not win over the contract's container ("thùng 12 hộp").
        ("Kem sữa Whipping Mây Trắng hộp 1L (thùng 12 hộp)", "thùng 12 hộp x 1L", "12", "12"),
        ("Kem sữa Whipping Mây Trắng hộp 1L (thùng 12 hộp x 1L)", "thùng 12 hộp x 1L", "12", "12"),
        # BRD_03 shrinkflation stays detectable.
        ("Ly nhựa PP 500ml đáy bằng in logo Lá Xanh (thùng 800 cái)", "thùng 1.000 cái", "1000", "800"),
        ("Cà phê hạt Robusta Đắk Nông rang mộc 1kg", "gói 1kg", "1", "1"),
        # Unstated count -> None, which the floor turns into PACK_SIZE_CHANGED.
        ("Hộp giấy kraft nắp gài 700ml Sông Xanh", "thùng 200 cái", "200", None),
    ],
)
def test_parse_pack_qty_prefers_contract_container(line_name, pack_spec, pack_qty_contract, expected):
    got = parse_pack_qty(
        line_name=line_name,
        line_unit="Thùng",
        base_unit="cái" if "cái" in pack_spec else ("hộp" if "hộp" in pack_spec else "kg"),
        pack_qty_contract=Decimal(pack_qty_contract),
        pack_spec=pack_spec,
    )
    assert got == (Decimal(expected) if expected is not None else None)
