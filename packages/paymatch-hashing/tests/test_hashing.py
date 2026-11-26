"""Tests for RFC 8785 (JCS) canonical JSON and PayMatch SHA-256 hashing."""

from __future__ import annotations

import json
import pathlib
from enum import Enum, StrEnum

import pytest
import yaml

import paymatch_contracts as pc
from paymatch_hashing import (
    MAX_SAFE_INT,
    MIN_SAFE_INT,
    action_hash,
    intent_hash_escrow,
    intent_hash_invoice,
    jcs_canonicalize,
    normalize_timestamp_utc,
    payload_hash_approval,
    payload_hash_batch,
    sha256_jcs,
)

ROOT = pathlib.Path(__file__).resolve().parents[3]
VECTORS_PATH = ROOT / "contracts" / "test-vectors" / "hashing.json"
MERCHANT_SPEC_PATH = ROOT / "contracts" / "openapi" / "core-merchant.yaml"
GATE_SPEC_PATH = ROOT / "contracts" / "openapi" / "gate.yaml"


def test_hashing_test_vectors_file():
    assert VECTORS_PATH.is_file(), f"Missing test vectors file at {VECTORS_PATH}"
    doc = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))
    assert doc["version"] == 1

    for vec in doc["jcs_vectors"]:
        actual_json = jcs_canonicalize(vec["input"])
        assert actual_json == vec["canonical_json"], f"JCS mismatch on {vec['name']}"
        assert sha256_jcs(vec["input"]) == vec["sha256"], f"SHA-256 mismatch on {vec['name']}"

    assert doc.get("jcs_reject_vectors"), "hashing.json must include jcs_reject_vectors"
    for vec in doc["jcs_reject_vectors"]:
        with pytest.raises((TypeError, ValueError)):
            jcs_canonicalize(vec["input"])

    fn_map = {
        "intent_hash_invoice": lambda a: intent_hash_invoice(**a),
        "intent_hash_escrow": lambda a: intent_hash_escrow(**a),
        "payload_hash_approval": lambda a: payload_hash_approval(**a),
        "payload_hash_batch": lambda a: payload_hash_batch(**a),
        "action_hash": lambda a: action_hash(**a),
    }

    covered_functions = set()
    for vec in doc["domain_vectors"]:
        fn = fn_map[vec["function"]]
        covered_functions.add(vec["function"])
        actual_canonical = jcs_canonicalize(vec["canonical_object"])
        assert actual_canonical == vec["canonical_json"], f"Canonical JSON mismatch on {vec['name']}"
        assert sha256_jcs(vec["canonical_object"]) == vec["expected_hash"]
        assert fn(vec["args"]) == vec["expected_hash"], f"Function output mismatch on {vec['name']}"

    assert covered_functions == set(fn_map.keys())


def test_rfc8785_utf16_code_unit_key_ordering():
    # U+1F600 (😀) is supplementary plane -> UTF-16 surrogate pair 0xD83D 0xDE00.
    # U+E000 is Private Use Area in BMP -> UTF-16 code unit 0xE000.
    # Code point order: 0xE000 < 0x1F600, so Python sorted() puts U+E000 first.
    # RFC 8785 UTF-16 code unit order: 0xD83D < 0xE000, so U+1F600 MUST come first!
    obj = {
        "\ue000": "bmp_pua",
        "\U0001f600": "supplementary_emoji",
        "\r": "cr",
        "1": "digit",
        "\u0080": "latin1_ctrl",
        "\u00f6": "o_umlaut",
    }
    assert jcs_canonicalize(obj) == (
        '{"\\r":"cr","1":"digit","\u0080":"latin1_ctrl","\u00f6":"o_umlaut",'
        '"\U0001f600":"supplementary_emoji","\ue000":"bmp_pua"}'
    )


def test_rfc8785_string_escaping_rules():
    raw = 'quote:" slash:/ backslash:\\ bs:\b ff:\f nl:\n cr:\r tab:\t nul:\x00 us:\x1f del:\x7f vn:Đã gọi'
    expected = (
        '"quote:\\" slash:/ backslash:\\\\ bs:\\b ff:\\f nl:\\n cr:\\r tab:\\t '
        'nul:\\u0000 us:\\u001f del:\x7f vn:Đã gọi"'
    )
    assert jcs_canonicalize(raw) == expected


def test_rejects_floats_non_string_keys_duplicate_enum_keys_and_surrogates():
    class KeyEnum(Enum):
        dup = "a"

    with pytest.raises(TypeError, match="Floats are forbidden"):
        jcs_canonicalize({"amount": 22400000.0})
    with pytest.raises(TypeError, match="Floats are forbidden"):
        jcs_canonicalize([1, 2.5])
    with pytest.raises(TypeError, match="keys must be strings"):
        jcs_canonicalize({1: "a"})
    with pytest.raises(ValueError, match="Duplicate object key"):
        jcs_canonicalize({KeyEnum.dup: 1, "a": 2})
    with pytest.raises(ValueError, match="surrogate"):
        jcs_canonicalize("\ud800")
    with pytest.raises(ValueError, match="surrogate"):
        jcs_canonicalize({"\udfff": 1})
    with pytest.raises(TypeError, match="integer"):
        intent_hash_invoice("inv_1", "sha", "vac_1", True, "bank_transfer")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="Escrow intent channel"):
        intent_hash_escrow("po_1", "vac_1", 1000, "bank_transfer")
    with pytest.raises(ValueError, match="verification keys mismatch"):
        payload_hash_approval("a" * 64, {"called_phone_on_file": True})


def test_safe_integer_bounds_and_timestamp_normalization():
    # Safe integer boundaries succeed
    assert jcs_canonicalize({"max": MAX_SAFE_INT, "min": MIN_SAFE_INT}) == (
        '{"max":9007199254740991,"min":-9007199254740991}'
    )
    # Outside IEEE-754 safe integer range must be rejected
    with pytest.raises(ValueError, match="safe integer"):
        jcs_canonicalize({"amount_vnd": MAX_SAFE_INT + 1})
    with pytest.raises(ValueError, match="safe integer"):
        jcs_canonicalize({"amount_vnd": MIN_SAFE_INT - 1})
    with pytest.raises(ValueError, match="safe integer"):
        intent_hash_invoice("inv_1", "sha", "vac_1", MAX_SAFE_INT + 1, "bank_transfer")
    with pytest.raises(ValueError, match="safe integer"):
        intent_hash_escrow("po_1", "vac_1", MAX_SAFE_INT + 1)

    # Timestamp normalization to UTC YYYY-MM-DDTHH:MM:SSZ (drop fractional seconds)
    variants = [
        "2026-11-26T08:30:00+07:00",
        "2026-11-26T01:30:00+00:00",
        "2026-11-26T01:30:00Z",
        "2026-11-26T01:30:00.000Z",
        "2026-11-26T01:30:00.987654Z",
        "2026-11-26T08:30:00.500+07:00",
    ]
    for ts in variants:
        assert normalize_timestamp_utc(ts) == "2026-11-26T01:30:00Z"

    ih = "7fe62bf514d7be8158c45f4f9a8c0c070629d068c55b20d4a3ae4a20fc2327fb"
    hashes = {
        payload_hash_approval(
            ih,
            {
                "called_phone_on_file": True,
                "result": "confirmed",
                "note": "OK",
                "at": ts,
            },
        )
        for ts in variants
    }
    assert len(hashes) == 1

    # Reject naive timestamps without offset
    with pytest.raises(ValueError, match="timezone"):
        normalize_timestamp_utc("2026-11-26T01:30:00")
    with pytest.raises(ValueError, match="timezone"):
        payload_hash_approval(
            ih,
            {
                "called_phone_on_file": True,
                "result": "confirmed",
                "note": None,
                "at": "2026-11-26T01:30:00",
            },
        )


def test_batch_sorting_and_verification_pydantic_normalization():
    ih_a = "a" * 64
    ih_b = "b" * 64
    ih_c = "c" * 64
    h1 = payload_hash_batch(
        "pvw_01M885AXP309SER6BAC46N5FJT",
        [
            ("inv_01M886J1WSC5HQBJABB31A9NB3", ih_c),
            ("inv_01M8808XXD8017SJ9NTGTNC48Y", ih_a),
            ("inv_01M882P8NTCDKGE2KVFMBTS5RK", ih_b),
        ],
    )
    h2 = payload_hash_batch(
        "pvw_01M885AXP309SER6BAC46N5FJT",
        [
            ["inv_01M8808XXD8017SJ9NTGTNC48Y", ih_a],
            ["inv_01M882P8NTCDKGE2KVFMBTS5RK", ih_b],
            ["inv_01M886J1WSC5HQBJABB31A9NB3", ih_c],
        ],
    )
    assert h1 == h2

    # Omitted note, explicit note=None, and generated Verification model must hash identically
    raw_without_note = {
        "called_phone_on_file": True,
        "result": "confirmed",
        "at": "2026-11-26T08:30:00+07:00",
    }
    raw_with_null_note = {
        "called_phone_on_file": True,
        "result": "confirmed",
        "note": None,
        "at": "2026-11-26T08:30:00+07:00",
    }
    ver_model = pc.Verification.model_validate(raw_without_note)
    assert payload_hash_approval(ih_a, raw_without_note) == payload_hash_approval(ih_a, raw_with_null_note)
    assert payload_hash_approval(ih_a, raw_without_note) == payload_hash_approval(ih_a, ver_model)


def test_enum_values_handled_transparently():
    class ChannelStrEnum(StrEnum):
        bank_transfer = "bank_transfer"

    class LegacyEnum(str, Enum):
        bank_transfer = "bank_transfer"

    h_plain = intent_hash_invoice(
        "inv_01M882P8NTCDKGE2KVFMBTS5RK",
        "7bd877246110eed1e0a0e70cc74ab73739ea96a2cfd558102668d2f425de9995",
        "vac_01M883RZCB3B6Y8WG7WQVC1BBY",
        22400000,
        "bank_transfer",
    )
    assert (
        intent_hash_invoice(
            "inv_01M882P8NTCDKGE2KVFMBTS5RK",
            "7bd877246110eed1e0a0e70cc74ab73739ea96a2cfd558102668d2f425de9995",
            "vac_01M883RZCB3B6Y8WG7WQVC1BBY",
            22400000,
            ChannelStrEnum.bank_transfer,
        )
        == h_plain
    )
    assert (
        intent_hash_invoice(
            "inv_01M882P8NTCDKGE2KVFMBTS5RK",
            "7bd877246110eed1e0a0e70cc74ab73739ea96a2cfd558102668d2f425de9995",
            "vac_01M883RZCB3B6Y8WG7WQVC1BBY",
            22400000,
            LegacyEnum.bank_transfer,
        )
        == h_plain
    )


def test_openapi_examples_match_paymatch_hashing():
    merchant_spec = yaml.safe_load(MERCHANT_SPEC_PATH.read_text(encoding="utf-8"))
    gate_spec = yaml.safe_load(GATE_SPEC_PATH.read_text(encoding="utf-8"))

    inv_examples = merchant_spec["paths"]["/m/invoices/{invoice_id}"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["examples"]
    preview_examples = merchant_spec["paths"]["/m/invoices/{invoice_id}/approval-preview"]["get"][
        "responses"
    ]["200"]["content"]["application/json"]["examples"]
    gate_eval_examples = gate_spec["paths"]["/gate/evaluate"]["post"]["responses"]["200"][
        "content"
    ]["application/json"]["examples"]

    yellow_inv = inv_examples["yellow_cups_shrinkflation"]["value"]
    yellow_preview = preview_examples["yellow_cups_require_approval"]["value"]
    computed_cups_ih = intent_hash_invoice(
        yellow_inv["invoice_id"],
        yellow_inv["document"]["sha256"],
        yellow_preview["payee"]["vendor_account_id"],
        yellow_preview["amount_vnd"],
        yellow_preview["channel"],
    )
    assert computed_cups_ih == yellow_preview["intent_hash"]
    assert computed_cups_ih == gate_eval_examples["require_approval_cups"]["value"]["intent_hash"]
    assert (
        action_hash(
            "approve_invoice",
            yellow_inv["invoice_id"],
            payload_hash_approval(computed_cups_ih, None),
        )
        == yellow_preview["action_hash"]
    )

    red_inv = inv_examples["red_syrup_new_vendor_fraud"]["value"]
    red_preview = preview_examples["red_syrup_denied"]["value"]
    computed_syrup_ih = intent_hash_invoice(
        red_inv["invoice_id"],
        red_inv["document"]["sha256"],
        None,
        red_preview["amount_vnd"],
        red_preview["channel"],
    )
    assert computed_syrup_ih == red_preview["intent_hash"]
    assert computed_syrup_ih == gate_eval_examples["deny_syrup_blocked"]["value"]["intent_hash"]
    assert (
        action_hash(
            "approve_invoice",
            red_inv["invoice_id"],
            payload_hash_approval(computed_syrup_ih, None),
        )
        == red_preview["action_hash"]
    )
