"""Tests for the 6 system bot plugins (manifest.yaml + skill.md) and safety prompts."""

from __future__ import annotations

import json
import pathlib

import jsonschema
import yaml
from paymatch_contracts.internal import BotManifest, InvoiceType, V1ToolId
from referencing import Registry, Resource

from agent_runtime.plugins import (
    default_plugins_dir,
    load_all_system_bot_plugins,
    load_runtime_prompts,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCHEMAS_DIR = REPO_ROOT / "contracts" / "schemas"

EXPECTED_BOTS = {
    "procurement",
    "accounts-payable",
    "fraud-control",
    "tax",
    "branch-operations",
    "treasury",
}

EXPECTED_TOOLS_BY_BOT = {
    "procurement": ["invoices", "vendor_contracts", "price_check", "price_history"],
    "accounts-payable": [
        "invoices",
        "purchase_orders",
        "goods_receipts",
        "three_way_match",
        "payables_ledger",
    ],
    "fraud-control": [
        "invoices",
        "inbox",
        "chat_messages",
        "vendor_registry",
        "cross_alerts",
        "official_fraud_list",
    ],
    "tax": [
        "invoices",
        "vendor_registry",
        "einvoice_portal",
        "tax_id_lookup",
        "tax_risk_list",
    ],
    "branch-operations": ["utility_bills", "utility_baseline", "momo_revenue"],
    "treasury": [
        "account_balance",
        "spending_limits",
        "payables_ledger",
        "purchase_orders",
        "goods_receipts",
        "payment_policy_preview",
    ],
}

EXPECTED_REQUIRED_FOR = {
    "procurement": [InvoiceType.goods, InvoiceType.software],
    "accounts-payable": [InvoiceType.goods],
    "fraud-control": [InvoiceType.goods, InvoiceType.software],
    "tax": [InvoiceType.goods, InvoiceType.software],
    "branch-operations": [InvoiceType.utility],
    "treasury": [InvoiceType.goods, InvoiceType.software, InvoiceType.utility],
}

REQUIRED_SKILL_SECTIONS = [
    "## Khi nào dùng",
    "## Dữ liệu cần (tool)",
    "## Các bước",
    "## Cách kiểm chứng",
    "## Trả về (reason_codes dùng được)",
    "## Khi nào báo đỏ",
]


def _build_schema_registry() -> Registry:
    resources = []
    for p in sorted(SCHEMAS_DIR.glob("*.schema.json")):
        schema = json.loads(p.read_text(encoding="utf-8"))
        res = Resource.from_contents(schema)
        resources.append((p.resolve().as_uri(), res))
        if "$id" in schema:
            resources.append((schema["$id"], res))
    return Registry().with_resources(resources)


def test_all_six_system_bots_validate_against_contract_schema():
    plugins = load_all_system_bot_plugins()
    assert set(plugins.keys()) == EXPECTED_BOTS

    manifest_schema = json.loads((SCHEMAS_DIR / "bot-manifest.schema.json").read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(manifest_schema, registry=_build_schema_registry())
    v1_tools = {t.value for t in V1ToolId}

    for bot_id in sorted(EXPECTED_BOTS):
        raw_yaml = yaml.safe_load(
            (default_plugins_dir() / bot_id / "manifest.yaml").read_text(encoding="utf-8")
        )
        errors = list(validator.iter_errors(raw_yaml))
        assert not errors, f"{bot_id}/manifest.yaml schema errors: {errors}"

        manifest = BotManifest.model_validate(raw_yaml)
        assert manifest.id == bot_id
        assert manifest.tools == EXPECTED_TOOLS_BY_BOT[bot_id]
        assert set(manifest.tools) <= v1_tools
        assert manifest.required_for == EXPECTED_REQUIRED_FOR[bot_id]


def test_all_six_skill_files_follow_prompts_and_skills_spec():
    plugins = load_all_system_bot_plugins()
    for bot_id, plug in plugins.items():
        md = plug.skill.content_md
        for heading in REQUIRED_SKILL_SECTIONS:
            assert heading in md, f"{bot_id}/skill.md missing required section {heading!r}"
        assert plug.skill.prefetch, f"{bot_id}/skill.md should declare prefetch tools"
        assert set(plug.skill.prefetch) <= set(plug.manifest.tools), (
            f"{bot_id} prefetch {plug.skill.prefetch} not subset of manifest tools {plug.manifest.tools}"
        )


def test_runtime_prompts_contain_safety_boundaries():
    prompts = load_runtime_prompts()
    assert "<tool_result" in prompts.safety_frame
    assert "untrusted" in prompts.safety_frame
    assert "HIDDEN_INSTRUCTION" in prompts.safety_frame
    assert "chief-accountant" in prompts.chief_accountant
    assert "ask_<bot_id>" in prompts.chief_accountant
    assert "FindingForSupervisor" in prompts.chief_accountant


def test_env_example_has_api_key_slot_for_every_system_bot():
    """agent-runtime.md §7: every system bot (and the supervisor) has an LLM_API_KEY_<BOT_ID> slot."""
    env_keys = {
        line.split("=", 1)[0]
        for line in (REPO_ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }
    bot_ids = {p.parent.name for p in (REPO_ROOT / "plugins" / "bots").glob("*/manifest.yaml")}
    expected = {"LLM_API_KEY"} | {
        "LLM_API_KEY_" + bot_id.upper().replace("-", "_") for bot_id in bot_ids | {"chief-accountant"}
    }
    assert expected <= env_keys
