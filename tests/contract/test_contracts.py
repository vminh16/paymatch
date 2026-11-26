"""Contract tests for JSON Schemas, Event Schemas, OpenAPI specs, doc parity, and generated Pydantic v2 models."""

from __future__ import annotations

import json
import pathlib
import re
from typing import Any

import jsonschema
import yaml
from openapi_spec_validator import validate as validate_openapi
from openapi_spec_validator.readers import read_from_filename
from pydantic import BaseModel, TypeAdapter
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCHEMAS_DIR = ROOT / "contracts" / "schemas"
EVENTS_DIR = ROOT / "contracts" / "events"
OPENAPI_DIR = ROOT / "contracts" / "openapi"
MERCHANT_SPEC_PATH = OPENAPI_DIR / "core-merchant.yaml"
INTERNAL_SPEC_PATH = OPENAPI_DIR / "core-internal.yaml"
GATE_SPEC_PATH = OPENAPI_DIR / "gate.yaml"
SIM_SPEC_PATH = OPENAPI_DIR / "sim-world.yaml"

AGENT_RUNTIME_DOC = ROOT / "docs" / "03-agents" / "agent-runtime.md"
INTERNAL_API_DOC = ROOT / "docs" / "05-api" / "internal-api.md"
EVENTS_DOC = ROOT / "docs" / "05-api" / "events.md"
SCHEMAS_DOC = ROOT / "docs" / "05-api" / "schemas.md"
CONTRACTS_PY_SRC = ROOT / "packages" / "contracts-py" / "src" / "paymatch_contracts"

EXPECTED_MERCHANT_PATHS = {
    "/m/healthz",
    "/m/readyz",
    "/m/auth/session",
    "/m/me",
    "/m/invoices",
    "/m/invoices/{invoice_id}",
    "/m/invoices/{invoice_id}/findings",
    "/m/invoices/{invoice_id}/approval-preview",
    "/m/invoices/{invoice_id}:approve",
    "/m/invoices/{invoice_id}:reject",
    "/m/invoices/{invoice_id}/adjustment-request",
    "/m/invoices:upload",
    "/m/jobs/{job_id}",
    "/m/jobs/{job_id}/events",
    "/m/events",
    "/m/approval-queue",
    "/m/notifications",
    "/m/demo:reset",
}

EXPECTED_INTERNAL_PATHS = {
    "/internal/healthz",
    "/internal/readyz",
    "/internal/jobs:claim",
    "/internal/jobs/{job_id}/session",
    "/internal/jobs/{job_id}/heartbeat",
    "/internal/jobs/{job_id}/progress",
    "/internal/jobs/{job_id}/findings",
    "/internal/jobs/{job_id}/bot-answers",
    "/internal/jobs/{job_id}:complete",
    "/internal/jobs/{job_id}:fail",
    "/internal/model-configs",
    "/internal/tools",
    "/internal/tools/{tool_id}:invoke",
    "/internal/webhooks/rails",
}

EXPECTED_GATE_PATHS = {
    "/gate/healthz",
    "/gate/readyz",
    "/gate/evaluate",
    "/gate/budgets/{tenant_id}/{date}",
    "/gate/intents",
    "/gate/intents/{payment_intent_id}",
    "/gate/intents/{payment_intent_id}:execute",
    "/gate/intents/{payment_intent_id}:cancel",
    "/gate/escrows",
    "/gate/escrows/{escrow_id}",
    "/gate/escrows/{escrow_id}:release",
    "/gate/escrows/{escrow_id}:refund",
}

EVENT_ENVELOPE_REQUIRED = {
    "event_id",
    "type",
    "schema_version",
    "occurred_at",
    "tenant_id",
    "trace_id",
    "data",
}


def _snake_to_pascal(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_"))


def _build_registry() -> Registry:
    resources: list[tuple[str, Resource]] = []
    for schema_path in sorted(SCHEMAS_DIR.glob("*.schema.json")):
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        resource = Resource.from_contents(schema)
        resources.append((schema_path.resolve().as_uri(), resource))
        if "$id" in schema:
            resources.append((schema["$id"], resource))
    for event_path in sorted(EVENTS_DIR.glob("*.schema.json")):
        event_schema = json.loads(event_path.read_text(encoding="utf-8"))
        resource = Resource.from_contents(event_schema)
        resources.append((event_path.resolve().as_uri(), resource))
        if "$id" in event_schema:
            resources.append((event_schema["$id"], resource))
    for spec_path in sorted(OPENAPI_DIR.glob("*.yaml")):
        spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
        resource = Resource.from_contents(spec, default_specification=DRAFT202012)
        resources.append((spec_path.resolve().as_uri(), resource))
    return Registry().with_resources(resources)


def _extract_reason_codes_from_doc() -> set[str]:
    text = AGENT_RUNTIME_DOC.read_text(encoding="utf-8")
    match = re.search(r"^## 5a\..*?(?=^## 6\.)", text, flags=re.MULTILINE | re.DOTALL)
    assert match is not None, "Section 5a not found in docs/03-agents/agent-runtime.md"
    section = match.group(0)
    codes: set[str] = set()
    for line in section.splitlines():
        if not line.startswith("| `"):
            continue
        first_col = line.split("|")[1]
        for code in re.findall(r"`([A-Z][A-Z0-9_]+)`", first_col):
            codes.add(code)
    return codes


def _extract_v1_tools_from_internal_api_doc() -> set[str]:
    text = INTERNAL_API_DOC.read_text(encoding="utf-8")
    match = re.search(r"^## 2\. Tool.*?(?=^## 3\.)", text, flags=re.MULTILINE | re.DOTALL)
    assert match is not None, "Section 2 not found in docs/05-api/internal-api.md"
    section = match.group(0)
    tools: set[str] = set()
    for line in section.splitlines():
        if not line.startswith("| `"):
            continue
        first_col = line.split("|")[1]
        for tool_id in re.findall(r"`([a-z][a-z0-9_]*)`", first_col):
            tools.add(tool_id)
    return tools


def _extract_event_types_from_events_doc() -> set[str]:
    text = EVENTS_DOC.read_text(encoding="utf-8")
    match = re.search(r"^## 2\..*?(?=^## 3\.)", text, flags=re.MULTILINE | re.DOTALL)
    assert match is not None, "Section 2 not found in docs/05-api/events.md"
    section = match.group(0)
    event_types: set[str] = set()
    for line in section.splitlines():
        if not line.startswith("| `"):
            continue
        first_col = line.split("|")[1]
        for ev_type in re.findall(r"`([a-z][a-z0-9_]*\.[a-z][a-z0-9_]*)`", first_col):
            event_types.add(ev_type)
    return event_types


def _extract_gate_reason_codes_from_schemas_doc() -> set[str]:
    text = SCHEMAS_DOC.read_text(encoding="utf-8")
    match = re.search(
        r"^GateReason:\n.*?(?=^PaymentIntentStatus:)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match is not None, "GateReason block not found in docs/05-api/schemas.md"
    block = match.group(0)
    return set(re.findall(r"\b([A-Z][A-Z0-9_]{2,})\b", block))


def test_every_openapi_file_validates():
    spec_files = sorted(
        p for p in OPENAPI_DIR.iterdir() if p.suffix in {".yaml", ".yml", ".json"}
    )
    assert len(spec_files) >= 4
    for spec_path in spec_files:
        spec_dict, base_uri = read_from_filename(str(spec_path))
        validate_openapi(spec_dict, base_uri=base_uri)


def test_openapi_scopes_metadata_and_auth_boundaries():
    merchant_spec = yaml.safe_load(MERCHANT_SPEC_PATH.read_text(encoding="utf-8"))
    assert merchant_spec["openapi"] == "3.1.0"
    assert merchant_spec["info"]["version"] == "0.1.0"
    assert set(merchant_spec["paths"].keys()) == EXPECTED_MERCHANT_PATHS

    internal_spec = yaml.safe_load(INTERNAL_SPEC_PATH.read_text(encoding="utf-8"))
    assert internal_spec["openapi"] == "3.1.0"
    assert internal_spec["info"]["version"] == "0.1.0"
    assert internal_spec["servers"][0]["url"] == "http://localhost:8003"
    assert set(internal_spec["paths"].keys()) == EXPECTED_INTERNAL_PATHS
    assert all(p.startswith("/internal/") for p in internal_spec["paths"])

    # Verify two auth schemes in core-internal.yaml are never mixed on the same operation
    capability_ops = {
        ("post", "/internal/jobs/{job_id}/findings"),
        ("post", "/internal/jobs/{job_id}/bot-answers"),
        ("get", "/internal/tools"),
        ("post", "/internal/tools/{tool_id}:invoke"),
    }
    probe_ops = {
        ("get", "/internal/healthz"),
        ("get", "/internal/readyz"),
    }
    for path, path_item in internal_spec["paths"].items():
        for method, op in path_item.items():
            if method not in {"get", "post", "patch", "put", "delete"}:
                continue
            sec = op.get("security")
            assert sec is not None, f"{method.upper()} {path} must declare explicit security"
            if (method, path) in probe_ops:
                assert sec == []
            elif (method, path) in capability_ops:
                assert sec == [{"CapabilityBearerAuth": []}]
            else:
                assert sec == [{"ServiceKeyAuth": []}]

    gate_spec = yaml.safe_load(GATE_SPEC_PATH.read_text(encoding="utf-8"))
    assert gate_spec["openapi"] == "3.1.0"
    assert gate_spec["info"]["version"] == "0.1.0"
    assert gate_spec["servers"][0]["url"] == "http://localhost:8100"
    assert set(gate_spec["paths"].keys()) == EXPECTED_GATE_PATHS
    assert all(p.startswith("/gate/") for p in gate_spec["paths"])
    assert gate_spec["security"] == [{"ServiceKeyAuth": []}]

    # Coordinator decision #7: GET /gate/intents requires tenant_id query parameter
    list_intents_params = {
        p["name"]: p
        for p in gate_spec["paths"]["/gate/intents"]["get"]["parameters"]
        if "name" in p
    }
    assert "tenant_id" in list_intents_params
    assert list_intents_params["tenant_id"]["in"] == "query"
    assert list_intents_params["tenant_id"]["required"] is True

    # Coordinator decision #6: EvaluateResponse.payee_account_id is nullable (null only on DENY)
    eval_payee = gate_spec["components"]["schemas"]["EvaluateResponse"]["properties"][
        "payee_account_id"
    ]
    assert eval_payee["type"] == ["string", "null"]


def test_healthz_and_readyz_have_empty_security_in_all_openapi_specs():
    expected_prefixes = {
        "core-merchant.yaml": "/m",
        "core-internal.yaml": "/internal",
        "gate.yaml": "/gate",
        "sim-world.yaml": "/sim",
    }
    for filename, prefix in expected_prefixes.items():
        spec = yaml.safe_load((OPENAPI_DIR / filename).read_text(encoding="utf-8"))
        for probe in (f"{prefix}/healthz", f"{prefix}/readyz"):
            assert probe in spec["paths"], f"{filename} missing {probe}"
            assert spec["paths"][probe]["get"].get("security") == [], (
                f"{filename} {probe} must have security: []"
            )


def test_every_json_schema_is_valid_2020_12():
    schema_files = sorted(SCHEMAS_DIR.glob("*.schema.json"))
    assert len(schema_files) >= 50
    for schema_path in schema_files:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        assert schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema", (
            f"{schema_path.name} must declare JSON Schema 2020-12"
        )
        jsonschema.Draft202012Validator.check_schema(schema)


def test_every_event_schema_matches_events_doc_and_validates_examples():
    from paymatch_contracts import events as pc_events

    doc_event_types = _extract_event_types_from_events_doc()
    assert len(doc_event_types) == 27

    event_files = sorted(EVENTS_DIR.glob("*.schema.json"))
    file_event_types = {p.name[: -len(".schema.json")] for p in event_files}
    assert file_event_types == doc_event_types, (
        f"Event schema files vs events.md mismatch. "
        f"Extra files: {file_event_types - doc_event_types}, "
        f"missing files: {doc_event_types - file_event_types}"
    )

    registry = _build_registry()
    format_checker = jsonschema.Draft202012Validator.FORMAT_CHECKER

    for event_path in event_files:
        ev_type = event_path.name[: -len(".schema.json")]
        schema = json.loads(event_path.read_text(encoding="utf-8"))
        assert schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema"
        jsonschema.Draft202012Validator.check_schema(schema)

        assert set(schema["required"]) == EVENT_ENVELOPE_REQUIRED
        assert set(schema["properties"].keys()) == EVENT_ENVELOPE_REQUIRED
        assert schema["properties"]["type"]["const"] == ev_type

        examples = schema.get("examples", [])
        assert examples, f"{event_path.name} must include at least one example"

        validator = jsonschema.Draft202012Validator(
            schema, registry=registry, format_checker=format_checker
        )
        model_cls = getattr(pc_events, schema["title"])

        for idx, example in enumerate(examples):
            errors = list(validator.iter_errors(example))
            assert not errors, (
                f"{event_path.name} example[{idx}] failed validation: "
                + "; ".join(e.message for e in errors)
            )
            inst = model_cls.model_validate(example)
            dumped = inst.model_dump(mode="json", by_alias=True)
            assert dumped == example or model_cls.model_validate(dumped) == inst
            assert model_cls.model_validate(dumped) == inst

    # Coordinator decision #3 & #8 checks on event schemas
    progressed = json.loads((EVENTS_DIR / "job.progressed.schema.json").read_text(encoding="utf-8"))
    progressed_props = set(progressed["properties"]["data"]["properties"].keys())
    assert {"step", "severity", "reason_code"} <= progressed_props

    for indicator_ev in (
        "indicator.flagged.schema.json",
        "cross_alert.published.schema.json",
        "hard_block.applied.schema.json",
    ):
        ev_schema = json.loads((EVENTS_DIR / indicator_ev).read_text(encoding="utf-8"))
        item_schema = ev_schema["properties"]["data"]["properties"]["indicators"]["items"]
        assert set(item_schema["required"]) == {"kind", "value_hash"}
        assert set(item_schema["properties"].keys()) == {"kind", "value_hash"}


def test_every_openapi_example_validates_against_its_schema():
    registry = _build_registry()
    format_checker = jsonschema.Draft202012Validator.FORMAT_CHECKER
    spec_paths = [MERCHANT_SPEC_PATH, INTERNAL_SPEC_PATH, GATE_SPEC_PATH, SIM_SPEC_PATH]

    total_validated = 0
    for spec_path in spec_paths:
        spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
        validator_id = f"{spec_path.parent.resolve().as_uri()}/__{spec_path.stem}_validator__.json"

        def _validate(schema_obj: dict[str, Any], value: Any, label: str) -> None:
            wrapped = {
                "$id": validator_id,
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "components": spec.get("components", {}),
                **schema_obj,
            }
            validator = jsonschema.Draft202012Validator(
                wrapped,
                registry=registry,
                format_checker=format_checker,
            )
            errors = sorted(validator.iter_errors(value), key=lambda e: list(e.path))
            assert not errors, (
                f"{spec_path.name} example {label} failed schema validation:\n"
                + "\n".join(f"  - {list(e.path)}: {e.message}" for e in errors)
            )

        spec_validated = 0
        for path, path_item in spec["paths"].items():
            for method, operation in path_item.items():
                if method not in {"get", "post", "patch", "put", "delete"}:
                    continue

                req_body = operation.get("requestBody", {})
                for media_type, media_obj in req_body.get("content", {}).items():
                    if media_type != "application/json":
                        continue
                    schema_obj = media_obj["schema"]
                    if "example" in media_obj:
                        _validate(
                            schema_obj,
                            media_obj["example"],
                            f"{method.upper()} {path} req:example",
                        )
                        spec_validated += 1
                    for ex_name, ex_obj in media_obj.get("examples", {}).items():
                        _validate(
                            schema_obj,
                            ex_obj["value"],
                            f"{method.upper()} {path} req:{ex_name}",
                        )
                        spec_validated += 1

                for status_code, resp_obj in operation.get("responses", {}).items():
                    if "$ref" in resp_obj:
                        ref_name = resp_obj["$ref"].split("/")[-1]
                        resp_obj = spec["components"]["responses"][ref_name]
                    for media_type, media_obj in resp_obj.get("content", {}).items():
                        if media_type in {"application/json", "application/problem+json"}:
                            schema_obj = media_obj["schema"]
                            if "example" in media_obj:
                                _validate(
                                    schema_obj,
                                    media_obj["example"],
                                    f"{method.upper()} {path} {status_code} resp:example",
                                )
                                spec_validated += 1
                            for ex_name, ex_obj in media_obj.get("examples", {}).items():
                                _validate(
                                    schema_obj,
                                    ex_obj["value"],
                                    f"{method.upper()} {path} {status_code} resp:{ex_name}",
                                )
                                spec_validated += 1
                        elif media_type == "text/event-stream":
                            sse_schema_name = (
                                "JobSseEventData" if "jobs" in path else "TenantSseEventData"
                            )
                            sse_schema = spec["components"]["schemas"][sse_schema_name]
                            for ex_name, ex_obj in media_obj.get("examples", {}).items():
                                data_lines = [
                                    line[len("data:") :].strip()
                                    for line in ex_obj["value"].splitlines()
                                    if line.startswith("data:")
                                ]
                                assert data_lines, f"SSE example {path}:{ex_name} has no data lines"
                                for idx, raw_json in enumerate(data_lines):
                                    _validate(
                                        sse_schema,
                                        json.loads(raw_json),
                                        f"{method.upper()} {path} sse:{ex_name}[{idx}]",
                                    )
                                    spec_validated += 1

        assert spec_validated >= 10, (
            f"Expected >= 10 validated examples in {spec_path.name}, got {spec_validated}"
        )
        total_validated += spec_validated

    assert total_validated >= 90


def test_every_v1_tool_in_internal_api_doc_has_input_output_schemas():
    from paymatch_contracts import internal

    doc_tools = _extract_v1_tools_from_internal_api_doc()
    assert len(doc_tools) == 30

    internal_spec = yaml.safe_load(INTERNAL_SPEC_PATH.read_text(encoding="utf-8"))
    schemas = internal_spec["components"]["schemas"]

    spec_tool_enum = set(schemas["V1ToolId"]["enum"])
    model_tool_enum = {member.value for member in internal.V1ToolId}
    assert spec_tool_enum == doc_tools
    assert model_tool_enum == doc_tools

    for tool_id in sorted(doc_tools):
        pascal = _snake_to_pascal(tool_id)
        in_name = f"{pascal}Input"
        out_name = f"{pascal}Output"
        assert in_name in schemas, f"Missing {in_name} in core-internal.yaml components.schemas"
        assert out_name in schemas, f"Missing {out_name} in core-internal.yaml components.schemas"
        jsonschema.Draft202012Validator.check_schema(schemas[in_name])
        jsonschema.Draft202012Validator.check_schema(schemas[out_name])
        assert hasattr(internal, in_name), f"Missing generated model internal.{in_name}"
        assert hasattr(internal, out_name), f"Missing generated model internal.{out_name}"


def test_reason_code_enum_matches_agent_runtime_doc():
    from paymatch_contracts import ReasonCode

    doc_codes = _extract_reason_codes_from_doc()
    schema = json.loads((SCHEMAS_DIR / "reason-code.schema.json").read_text(encoding="utf-8"))
    schema_codes = set(schema["enum"])
    model_codes = {member.value for member in ReasonCode}

    assert len(schema["enum"]) == len(schema_codes), "Duplicate codes in reason-code.schema.json"
    assert schema_codes == doc_codes, (
        f"Schema vs doc mismatch. Extra in schema: {schema_codes - doc_codes}, "
        f"missing from schema: {doc_codes - schema_codes}"
    )
    assert model_codes == doc_codes


def test_every_gate_reason_code_in_schemas_doc_appears_in_gate_spec():
    from paymatch_contracts import GateReason, gate

    doc_codes = _extract_gate_reason_codes_from_schemas_doc()
    assert len(doc_codes) == 16

    gate_reason_schema = json.loads(
        (SCHEMAS_DIR / "gate-reason.schema.json").read_text(encoding="utf-8")
    )
    schema_codes = set(gate_reason_schema["properties"]["code"]["enum"])
    assert schema_codes == doc_codes

    gate_yaml_text = GATE_SPEC_PATH.read_text(encoding="utf-8")
    for code in sorted(doc_codes):
        assert code in gate_yaml_text, f"GateReason code {code} missing from gate.yaml"

    gate_model_codes = {member.value for member in gate.Code}
    assert gate_model_codes == doc_codes

    # Verify GateReason shared model validates every code
    for code in sorted(doc_codes):
        inst = GateReason.model_validate(
            {"code": code, "layer": "hard_rule", "detail": f"Test {code}"}
        )
        assert inst.code.value == code


def test_generated_files_have_header_comment():
    py_files = sorted(CONTRACTS_PY_SRC.rglob("*.py"))
    assert py_files, "No generated Python files found in paymatch_contracts"
    for py_file in py_files:
        first_line = py_file.read_text(encoding="utf-8").splitlines()[0]
        assert first_line == "# generated — do not edit", (
            f"{py_file} missing generated header comment (got {first_line!r})"
        )


def test_generated_models_import_and_roundtrip_examples():
    import paymatch_contracts as pc
    from paymatch_contracts import events, gate, internal, merchant

    merchant_spec = yaml.safe_load(MERCHANT_SPEC_PATH.read_text(encoding="utf-8"))
    internal_spec = yaml.safe_load(INTERNAL_SPEC_PATH.read_text(encoding="utf-8"))
    gate_spec = yaml.safe_load(GATE_SPEC_PATH.read_text(encoding="utf-8"))

    invoice_examples = merchant_spec["paths"]["/m/invoices/{invoice_id}"]["get"]["responses"][
        "200"
    ]["content"]["application/json"]["examples"]
    yellow_inv = invoice_examples["yellow_cups_shrinkflation"]["value"]
    green_inv = invoice_examples["green_coffee_autopay"]["value"]
    red_inv = invoice_examples["red_syrup_new_vendor_fraud"]["value"]

    findings_ex = merchant_spec["paths"]["/m/invoices/{invoice_id}/findings"]["get"]["responses"][
        "200"
    ]["content"]["application/json"]["examples"]["yellow_cups_shrinkflation"]["value"]
    preview_ex = merchant_spec["paths"]["/m/invoices/{invoice_id}/approval-preview"]["get"][
        "responses"
    ]["200"]["content"]["application/json"]["examples"]["yellow_cups_require_approval"]["value"]
    approve_resp_ex = merchant_spec["paths"]["/m/invoices/{invoice_id}:approve"]["post"][
        "responses"
    ]["200"]["content"]["application/json"]["examples"]["approved_cups_yellow"]["value"]
    reject_resp_ex = merchant_spec["paths"]["/m/invoices/{invoice_id}:reject"]["post"][
        "responses"
    ]["200"]["content"]["application/json"]["examples"]["rejected_cups_with_adjustment"]["value"]
    adj_ex = merchant_spec["paths"]["/m/invoices/{invoice_id}/adjustment-request"]["get"][
        "responses"
    ]["200"]["content"]["application/json"]["examples"]["cups_shrinkflation_draft"]["value"]
    job_ex = merchant_spec["paths"]["/m/jobs/{job_id}"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["examples"]["completed_cups_job"]["value"]
    notif_page_ex = merchant_spec["paths"]["/m/notifications"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["examples"]["demo_notifications"]["value"]
    me_ex = merchant_spec["paths"]["/m/me"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["examples"]["owner_lan"]["value"]
    auth_ex = merchant_spec["paths"]["/m/auth/session"]["post"]["responses"]["200"]["content"][
        "application/json"
    ]["examples"]["owner_lan"]["value"]
    queue_ex = merchant_spec["paths"]["/m/approval-queue"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["examples"]["by_vendor"]["value"]
    inv_page_ex = merchant_spec["paths"]["/m/invoices"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["examples"]["brd_14_six_scenarios"]["value"]
    upload_ex = merchant_spec["paths"]["/m/invoices:upload"]["post"]["responses"]["202"][
        "content"
    ]["application/json"]["examples"]["accepted_xml"]["value"]
    reset_ex = merchant_spec["paths"]["/m/demo:reset"]["post"]["responses"]["200"]["content"][
        "application/json"
    ]["examples"]["demo_reset_ok"]["value"]
    problem_ex = merchant_spec["paths"]["/m/invoices/{invoice_id}:approve"]["post"]["responses"][
        "409"
    ]["content"]["application/problem+json"]["examples"]["mandate_review_only"]["value"]

    finding_sub_ex = internal_spec["paths"]["/internal/jobs/{job_id}/findings"]["post"][
        "requestBody"
    ]["content"]["application/json"]["examples"]["procurement_shrinkflation"]["value"]
    finding_sup_ex = internal_spec["paths"]["/internal/jobs/{job_id}/findings"]["post"][
        "responses"
    ]["201"]["content"]["application/json"]["examples"]["filtered_for_supervisor"]["value"]
    bot_answer_ex = internal_spec["paths"]["/internal/jobs/{job_id}/bot-answers"]["post"][
        "responses"
    ]["201"]["content"]["application/json"]["examples"]["verified_bot_answer"]["value"]
    session_ex = internal_spec["paths"]["/internal/jobs/{job_id}/session"]["post"]["responses"][
        "200"
    ]["content"]["application/json"]["examples"]["investigate_goods_session"]["value"]
    model_cfg_ex = internal_spec["paths"]["/internal/model-configs"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["examples"]["default_configs"]["value"][0]
    tool_def_ex = internal_spec["paths"]["/internal/tools"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["examples"]["procurement_tools"]["value"][0]
    tool_res_ex = internal_spec["paths"]["/internal/tools/{tool_id}:invoke"]["post"]["responses"][
        "200"
    ]["content"]["application/json"]["examples"]["price_check_shrinkflation_result"]["value"]
    complete_ans_req = internal_spec["paths"]["/internal/jobs/{job_id}:complete"]["post"][
        "requestBody"
    ]["content"]["application/json"]["examples"]["complete_question_answer"]["value"]

    pi_ex = gate_spec["paths"]["/gate/intents"]["post"]["responses"]["201"]["content"][
        "application/json"
    ]["examples"]["authorized_cups"]["value"]
    escrow_ex = gate_spec["paths"]["/gate/escrows"]["post"]["responses"]["201"]["content"][
        "application/json"
    ]["examples"]["held_escrow"]["value"]

    schema_samples: dict[str, tuple[Any, Any]] = {
        "MoneyVnd": (pc.MoneyVnd, 22400000),
        "SignedMoneyVnd": (pc.SignedMoneyVnd, -1620000),
        "Decimal": (pc.Decimal, "518518.518519"),
        "Timestamp": (pc.Timestamp, "2026-11-26T08:25:42+07:00"),
        "LocalDate": (pc.LocalDate, "2026-11-26"),
        "Severity": (pc.Severity, "yellow"),
        "Provenance": (pc.Provenance, "untrusted"),
        "Channel": (pc.Channel, "bank_transfer"),
        "InvoiceType": (pc.InvoiceType, "goods"),
        "ReasonCode": (pc.ReasonCode, "PACK_SIZE_CHANGED"),
        "UntrustedText": (pc.UntrustedText, yellow_inv["untrusted"]["seller_name"]),
        "InvoiceStatus": (pc.InvoiceStatus, "pending_approval"),
        "InvoiceSource": (pc.InvoiceSource, "email"),
        "JobStatus": (pc.JobStatus, "completed"),
        "TaskType": (pc.TaskType, "investigate_invoice"),
        "ApprovalMethod": (pc.ApprovalMethod, "single"),
        "PaymentIntentStatus": (pc.PaymentIntentStatus, "settled"),
        "EscrowStatus": (pc.EscrowStatus, "held"),
        "NotificationKind": (pc.NotificationKind, "verification_needed"),
        "BotStatus": (pc.BotStatus, "active"),
        "IndicatorKind": (pc.IndicatorKind, "account_hash"),
        "KillSwitchScope": (pc.KillSwitchScope, "auto_pay_global"),
        "MandateMode": (pc.MandateMode, "auto_pay"),
        "VendorAccountStatus": (pc.VendorAccountStatus, "verified"),
        "InvoiceSummary": (pc.InvoiceSummary, inv_page_ex["items"][0]),
        "Invoice": (pc.Invoice, yellow_inv),
        "InvoiceLine": (pc.InvoiceLine, yellow_inv["lines"][0]),
        "EvidenceRef": (pc.EvidenceRef, findings_ex[0]["evidence"][0]),
        "Brief": (pc.Brief, yellow_inv["brief"]),
        "Finding": (pc.Finding, findings_ex[0]),
        "FindingSubmission": (pc.FindingSubmission, finding_sub_ex),
        "FindingForSupervisor": (pc.FindingForSupervisor, finding_sup_ex),
        "BotAnswer": (pc.BotAnswer, bot_answer_ex),
        "Job": (pc.Job, job_ex),
        "GateReason": (pc.GateReason, preview_ex["gate_reasons"][0]),
        "Verification": (
            pc.Verification,
            {
                "called_phone_on_file": True,
                "result": "confirmed",
                "note": "Đã gọi 0280***003 xác nhận với kế toán trưởng NCC.",
                "at": "2026-11-26T08:30:00+07:00",
            },
        ),
        "ApprovalSummary": (pc.ApprovalSummary, green_inv["approval"]),
        "Approval": (pc.Approval, approve_resp_ex["approval"]),
        "ApprovalPreview": (pc.ApprovalPreview, preview_ex),
        "AdjustmentRequest": (pc.AdjustmentRequest, adj_ex),
        "Problem": (pc.Problem, problem_ex),
        "Page": (pc.Page, inv_page_ex),
        "Notification": (pc.Notification, notif_page_ex["items"][0]),
        "User": (pc.User, auth_ex["user"]),
        "PaymentIntent": (pc.PaymentIntent, pi_ex),
        "Escrow": (pc.Escrow, escrow_ex),
        "Mandate": (
            pc.Mandate,
            {
                "mandate_id": "man_01M885AXP309SER6BAC46N5FJT",
                "version": 1,
                "mode": "auto_pay",
                "limits": {"per_invoice_vnd": 30000000, "per_day_vnd": 50000000},
                "auto_pay_vendor_ids": ["ven_01M88CGAPGH0KRTMDHYVB4JF3C"],
                "channel_rules": [{"invoice_type": "software", "channel": "virtual_card"}],
                "bulk_approvable": [{"reason_codes": ["NON_XML_SOURCE"], "max_amount_vnd": 2000000}],
                "auto_pay_window": {"start": "07:00", "end": "22:00"},
                "signed": {
                    "by_user_id": "usr_01M885AXP309SER6BAC46N5FJT",
                    "method": "otp",
                    "auth_proof_jti": "jti_mandate_001",
                    "at": "2026-01-05T08:00:00+07:00",
                },
                "created_at": "2026-01-05T08:00:00+07:00",
            },
        ),
        "PlatformLimits": (
            pc.PlatformLimits,
            {
                "auto_pay_per_invoice_vnd": 30000000,
                "auto_pay_per_day_vnd": 50000000,
                "updated_at": "2026-01-01T08:00:00+07:00",
            },
        ),
        "AutoPaySuspension": (
            pc.AutoPaySuspension,
            {
                "vendor_id": "ven_01M8876N5RKZ3A9GRME2NFSMH0",
                "reason_codes": ["PACK_SIZE_CHANGED", "PRICE_ABOVE_CONTRACT"],
                "source_invoice_id": "inv_01M882P8NTCDKGE2KVFMBTS5RK",
                "suspended_at": "2026-11-26T08:25:42+07:00",
                "lifted_at": None,
                "lifted_by": None,
            },
        ),
        "Vendor": (
            pc.Vendor,
            {
                "vendor_id": "ven_01M8876N5RKZ3A9GRME2NFSMH0",
                "name": "CÔNG TY TNHH BAO BÌ NHỰA XANH VIỆT",
                "tax_id": "0999010003",
                "phone_on_file_masked": "0280***003",
                "status": "active",
                "created_at": "2026-01-05T08:00:00+07:00",
            },
        ),
        "VendorAccount": (
            pc.VendorAccount,
            {
                "vendor_account_id": "vac_01M883RZCB3B6Y8WG7WQVC1BBY",
                "vendor_id": "ven_01M8876N5RKZ3A9GRME2NFSMH0",
                "kind": "bank_account",
                "bank_code": "NVB",
                "bank_name": "Ngân hàng Mẫu Nam Việt",
                "account_number_masked": "****0003",
                "merchant_id": None,
                "account_name": "CONG TY TNHH BAO BI NHUA XANH VIET",
                "status": "verified",
                "verified_at": "2026-01-05T08:00:00+07:00",
            },
        ),
        "ContractItem": (
            pc.ContractItem,
            {
                "item_id": "itm_01M88CSDFSBSMNDF8409DYVJBZ",
                "sku": "CUP-PP500-1000",
                "name": "Ly nhựa PP 500ml",
                "base_unit": "cái",
                "pack_spec": "1000 cái/thùng",
                "pack_qty": "1000.000000",
                "unit_price": "532.407407",
                "vat_rate": "8%",
            },
        ),
        "PurchaseOrder": (
            pc.PurchaseOrder,
            {
                "purchase_order_id": "po_01M88KAB60PG4ZW7CE8F96MQE1",
                "vendor_id": "ven_01M884AMS92SKW70F02KZYE55Z",
                "store_id": "sto_01M88EX5B609CFYQKTCYCCN3XN",
                "lines": [
                    {
                        "sku": "SUG-LIQ-25KG",
                        "quantity": "15.000000",
                        "unit_price": "544444.444444",
                    }
                ],
                "total_vnd": 8820000,
                "status": "received",
                "created_by": "usr_01M88KDM92WAXYR1VPJ05VGKVV",
                "created_at": "2026-11-23T09:00:00+07:00",
            },
        ),
        "GoodsReceipt": (
            pc.GoodsReceipt,
            {
                "goods_receipt_id": "grn_01M884Y1K8SBPJVXXPDS01Q7PV",
                "purchase_order_id": "po_01M886NDCXNRHK9AN74YJSFB5A",
                "store_id": "sto_01M88EX5B609CFYQKTCYCCN3XN",
                "lines": [{"sku": "SUG-LIQ-25KG", "quantity_received": "15.000000"}],
                "confirmed_by": "usr_01M88KDM92WAXYR1VPJ05VGKVV",
                "confirmed_at": "2026-11-25T14:30:00+07:00",
            },
        ),
        "BotManifest": (pc.BotManifest, session_ex["bots"][0]["manifest"]),
        "ModelConfig": (pc.ModelConfig, model_cfg_ex),
        "ToolDefinition": (pc.ToolDefinition, tool_def_ex),
        "ToolResult": (pc.ToolResult, tool_res_ex),
        "CapabilityTokenClaims": (
            pc.CapabilityTokenClaims,
            {
                "iss": "core",
                "aud": "internal-api",
                "sub": "supervisor",
                "tenant_id": "ten_01M88D3C06B97Y4G0S9W8BVKNG",
                "job_id": "job_01M882G20CAMSQWE8SVGP02RHD",
                "invoice_id": None,
                "attempt": 1,
                "worker_id": "agent-worker-01",
                "bot_version": None,
                "tools": ["queue_status", "invoice_explain"],
                "exp": 1795656000,
                "jti": "jti_sup_001",
            },
        ),
        "ProposedAction": (
            pc.ProposedAction,
            complete_ans_req["result"]["answer"]["proposed_actions"][0],
        ),
    }

    # Ensure every schema file in contracts/schemas/ is covered by schema_samples
    all_titles = {
        json.loads(p.read_text(encoding="utf-8"))["title"]
        for p in sorted(SCHEMAS_DIR.glob("*.schema.json"))
    }
    assert set(schema_samples.keys()) == all_titles

    for name, (model_type, sample) in schema_samples.items():
        if isinstance(model_type, type) and issubclass(model_type, BaseModel):
            inst = model_type.model_validate(sample)
            dumped = inst.model_dump(mode="json", by_alias=True)
            assert model_type.model_validate(dumped) == inst, f"Round-trip failed for {name}"
        else:
            adapter = TypeAdapter(model_type)
            inst = adapter.validate_python(sample)
            dumped = adapter.dump_python(inst, mode="json", by_alias=True)
            assert adapter.validate_python(dumped) == inst, f"Round-trip failed for {name}"

    # Verify CapabilityTokenClaims also accepts bot subject + store_ids and Job accepts {report_id}
    bot_claims = pc.CapabilityTokenClaims.model_validate(
        {
            "iss": "core",
            "aud": "internal-api",
            "sub": "procurement",
            "tenant_id": "ten_01M88D3C06B97Y4G0S9W8BVKNG",
            "job_id": "job_01M882G20CAMSQWE8SVGP02RHD",
            "invoice_id": "inv_01M882P8NTCDKGE2KVFMBTS5RK",
            "attempt": 1,
            "worker_id": "agent-worker-01",
            "bot_version": 1,
            "tools": ["invoices", "price_check"],
            "store_ids": ["sto_01M8890N9Y7RRHWTHDZPHWM785"],
            "exp": 1795656000,
            "jti": "jti_proc_001",
        }
    )
    assert pc.CapabilityTokenClaims.model_validate(bot_claims.model_dump(mode="json")) == bot_claims

    for inv_sample in (green_inv, red_inv):
        inst = pc.Invoice.model_validate(inv_sample)
        assert pc.Invoice.model_validate(inst.model_dump(mode="json")) == inst

    api_model_samples = [
        (merchant.AuthSessionResponse, auth_ex),
        (merchant.MeResponse, me_ex),
        (merchant.InvoicePage, inv_page_ex),
        (merchant.NotificationPage, notif_page_ex),
        (merchant.InvoiceUploadResponse, upload_ex),
        (merchant.ApproveInvoiceResponse, approve_resp_ex),
        (merchant.RejectInvoiceResponse, reject_resp_ex),
        (merchant.ApprovalQueueResponse, queue_ex),
        (merchant.DemoResetResponse, reset_ex),
        (
            internal.ClaimedJobResponse,
            internal_spec["paths"]["/internal/jobs:claim"]["post"]["responses"]["200"]["content"][
                "application/json"
            ]["examples"]["claimed_report_job"]["value"],
        ),
        (internal.JobSessionResponse, session_ex),
        (
            internal.JobProgressRequest,
            internal_spec["paths"]["/internal/jobs/{job_id}/progress"]["post"]["requestBody"][
                "content"
            ]["application/json"]["examples"]["bot_lifecycle_events"]["value"],
        ),
        (internal.CompleteJobRequest, complete_ans_req),
        (
            internal.RailsWebhookRequest,
            internal_spec["paths"]["/internal/webhooks/rails"]["post"]["requestBody"]["content"][
                "application/json"
            ]["examples"]["card_declined_wrong_merchant"]["value"],
        ),
        (
            gate.EvaluateResponse,
            gate_spec["paths"]["/gate/evaluate"]["post"]["responses"]["200"]["content"][
                "application/json"
            ]["examples"]["deny_syrup_blocked"]["value"],
        ),
        (
            gate.DailyBudgetResponse,
            gate_spec["paths"]["/gate/budgets/{tenant_id}/{date}"]["get"]["responses"]["200"][
                "content"
            ]["application/json"]["examples"]["morning_after_coffee_and_pos"]["value"],
        ),
        (
            gate.GateDeniedProblem,
            gate_spec["components"]["responses"]["GateDenied"]["content"][
                "application/problem+json"
            ]["examples"]["cross_alert_unverified"]["value"],
        ),
        (
            events.CrossAlertPublishedEvent,
            json.loads(
                (EVENTS_DIR / "cross_alert.published.schema.json").read_text(encoding="utf-8")
            )["examples"][0],
        ),
    ]
    for model_cls, sample in api_model_samples:
        inst = model_cls.model_validate(sample)
        assert model_cls.model_validate(inst.model_dump(mode="json", by_alias=True)) == inst
