"""Contract tests for JSON Schemas, OpenAPI specs, ReasonCode parity, and generated Pydantic v2 models."""

from __future__ import annotations

import json
import pathlib
import re
from typing import Any

import jsonschema
import pytest
import yaml
from openapi_spec_validator import validate as validate_openapi
from openapi_spec_validator.readers import read_from_filename
from pydantic import BaseModel, TypeAdapter
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCHEMAS_DIR = ROOT / "contracts" / "schemas"
OPENAPI_DIR = ROOT / "contracts" / "openapi"
MERCHANT_SPEC_PATH = OPENAPI_DIR / "core-merchant.yaml"
AGENT_RUNTIME_DOC = ROOT / "docs" / "03-agents" / "agent-runtime.md"
CONTRACTS_PY_SRC = ROOT / "packages" / "contracts-py" / "src" / "paymatch_contracts"

EXPECTED_MERCHANT_PATHS = {
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


def _build_registry() -> Registry:
    resources: list[tuple[str, Resource]] = []
    for schema_path in sorted(SCHEMAS_DIR.glob("*.schema.json")):
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        resource = Resource.from_contents(schema)
        resources.append((schema_path.resolve().as_uri(), resource))
        if "$id" in schema:
            resources.append((schema["$id"], resource))
    merchant_spec = yaml.safe_load(MERCHANT_SPEC_PATH.read_text(encoding="utf-8"))
    merchant_resource = Resource.from_contents(
        merchant_spec, default_specification=DRAFT202012
    )
    resources.append((MERCHANT_SPEC_PATH.resolve().as_uri(), merchant_resource))
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


def test_every_openapi_file_validates():
    spec_files = sorted(
        p for p in OPENAPI_DIR.iterdir() if p.suffix in {".yaml", ".yml", ".json"}
    )
    assert spec_files, "Expected at least one OpenAPI spec in contracts/openapi/"
    for spec_path in spec_files:
        spec_dict, base_uri = read_from_filename(str(spec_path))
        validate_openapi(spec_dict, base_uri=base_uri)


def test_merchant_openapi_scope_and_metadata():
    spec = yaml.safe_load(MERCHANT_SPEC_PATH.read_text(encoding="utf-8"))
    assert spec["openapi"] == "3.1.0"
    assert spec["info"]["version"] == "0.1.0"
    assert set(spec["paths"].keys()) == EXPECTED_MERCHANT_PATHS


def test_every_json_schema_is_valid_2020_12():
    schema_files = sorted(SCHEMAS_DIR.glob("*.schema.json"))
    assert len(schema_files) >= 28
    for schema_path in schema_files:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        assert schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema", (
            f"{schema_path.name} must declare JSON Schema 2020-12"
        )
        jsonschema.Draft202012Validator.check_schema(schema)


def test_every_openapi_example_validates_against_its_schema():
    registry = _build_registry()
    validator_id = f"{MERCHANT_SPEC_PATH.parent.resolve().as_uri()}/__example_validator__.json"
    spec = yaml.safe_load(MERCHANT_SPEC_PATH.read_text(encoding="utf-8"))
    format_checker = jsonschema.Draft202012Validator.FORMAT_CHECKER

    def _validate(schema_obj: dict[str, Any], value: Any, label: str) -> None:
        wrapped = {
            "$id": validator_id,
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "components": spec["components"],
            **schema_obj,
        }
        validator = jsonschema.Draft202012Validator(
            wrapped,
            registry=registry,
            format_checker=format_checker,
        )
        errors = sorted(validator.iter_errors(value), key=lambda e: list(e.path))
        assert not errors, (
            f"Example {label} failed schema validation:\n"
            + "\n".join(f"  - {list(e.path)}: {e.message}" for e in errors)
        )

    validated_count = 0
    for path, path_item in spec["paths"].items():
        for method, operation in path_item.items():
            if method not in {"get", "post", "patch", "put", "delete"}:
                continue

            req_body = operation.get("requestBody", {})
            for media_type, media_obj in req_body.get("content", {}).items():
                if media_type != "application/json":
                    continue
                schema_obj = media_obj["schema"]
                for ex_name, ex_obj in media_obj.get("examples", {}).items():
                    _validate(schema_obj, ex_obj["value"], f"{method.upper()} {path} req:{ex_name}")
                    validated_count += 1

            for status_code, resp_obj in operation.get("responses", {}).items():
                if "$ref" in resp_obj:
                    ref_name = resp_obj["$ref"].split("/")[-1]
                    resp_obj = spec["components"]["responses"][ref_name]
                for media_type, media_obj in resp_obj.get("content", {}).items():
                    if media_type in {"application/json", "application/problem+json"}:
                        schema_obj = media_obj["schema"]
                        for ex_name, ex_obj in media_obj.get("examples", {}).items():
                            _validate(
                                schema_obj,
                                ex_obj["value"],
                                f"{method.upper()} {path} {status_code} resp:{ex_name}",
                            )
                            validated_count += 1
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
                                validated_count += 1

    assert validated_count >= 25, f"Expected >= 25 validated examples, got {validated_count}"


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
    from paymatch_contracts import merchant

    spec = yaml.safe_load(MERCHANT_SPEC_PATH.read_text(encoding="utf-8"))

    invoice_examples = spec["paths"]["/m/invoices/{invoice_id}"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["examples"]
    yellow_inv = invoice_examples["yellow_cups_shrinkflation"]["value"]
    green_inv = invoice_examples["green_coffee_autopay"]["value"]
    red_inv = invoice_examples["red_syrup_new_vendor_fraud"]["value"]

    findings_ex = spec["paths"]["/m/invoices/{invoice_id}/findings"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["examples"]["yellow_cups_shrinkflation"]["value"]
    preview_ex = spec["paths"]["/m/invoices/{invoice_id}/approval-preview"]["get"]["responses"][
        "200"
    ]["content"]["application/json"]["examples"]["yellow_cups_require_approval"]["value"]
    approve_resp_ex = spec["paths"]["/m/invoices/{invoice_id}:approve"]["post"]["responses"]["200"][
        "content"
    ]["application/json"]["examples"]["approved_cups_yellow"]["value"]
    reject_resp_ex = spec["paths"]["/m/invoices/{invoice_id}:reject"]["post"]["responses"]["200"][
        "content"
    ]["application/json"]["examples"]["rejected_cups_with_adjustment"]["value"]
    adj_ex = spec["paths"]["/m/invoices/{invoice_id}/adjustment-request"]["get"]["responses"][
        "200"
    ]["content"]["application/json"]["examples"]["cups_shrinkflation_draft"]["value"]
    job_ex = spec["paths"]["/m/jobs/{job_id}"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["examples"]["completed_cups_job"]["value"]
    notif_page_ex = spec["paths"]["/m/notifications"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["examples"]["demo_notifications"]["value"]
    me_ex = spec["paths"]["/m/me"]["get"]["responses"]["200"]["content"]["application/json"][
        "examples"
    ]["owner_lan"]["value"]
    auth_ex = spec["paths"]["/m/auth/session"]["post"]["responses"]["200"]["content"][
        "application/json"
    ]["examples"]["owner_lan"]["value"]
    queue_ex = spec["paths"]["/m/approval-queue"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["examples"]["by_vendor"]["value"]
    inv_page_ex = spec["paths"]["/m/invoices"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["examples"]["brd_14_six_scenarios"]["value"]
    upload_ex = spec["paths"]["/m/invoices:upload"]["post"]["responses"]["202"]["content"][
        "application/json"
    ]["examples"]["accepted_xml"]["value"]
    reset_ex = spec["paths"]["/m/demo:reset"]["post"]["responses"]["200"]["content"][
        "application/json"
    ]["examples"]["demo_reset_ok"]["value"]
    problem_ex = spec["paths"]["/m/invoices/{invoice_id}:approve"]["post"]["responses"]["409"][
        "content"
    ]["application/problem+json"]["examples"]["mandate_review_only"]["value"]

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
        "InvoiceSummary": (pc.InvoiceSummary, inv_page_ex["items"][0]),
        "Invoice": (pc.Invoice, yellow_inv),
        "InvoiceLine": (pc.InvoiceLine, yellow_inv["lines"][0]),
        "EvidenceRef": (pc.EvidenceRef, findings_ex[0]["evidence"][0]),
        "Brief": (pc.Brief, yellow_inv["brief"]),
        "Finding": (pc.Finding, findings_ex[0]),
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
            dumped = inst.model_dump(mode="json")
            assert model_type.model_validate(dumped) == inst, f"Round-trip failed for {name}"
        else:
            adapter = TypeAdapter(model_type)
            inst = adapter.validate_python(sample)
            dumped = adapter.dump_python(inst, mode="json")
            assert adapter.validate_python(dumped) == inst, f"Round-trip failed for {name}"

    # Also verify green and red Invoice examples and merchant API envelope models round-trip cleanly
    for inv_sample in (green_inv, red_inv):
        inst = pc.Invoice.model_validate(inv_sample)
        assert pc.Invoice.model_validate(inst.model_dump(mode="json")) == inst

    merchant_samples = [
        (merchant.AuthSessionResponse, auth_ex),
        (merchant.MeResponse, me_ex),
        (merchant.InvoicePage, inv_page_ex),
        (merchant.NotificationPage, notif_page_ex),
        (merchant.InvoiceUploadResponse, upload_ex),
        (merchant.ApproveInvoiceResponse, approve_resp_ex),
        (merchant.RejectInvoiceResponse, reject_resp_ex),
        (merchant.ApprovalQueueResponse, queue_ex),
        (merchant.DemoResetResponse, reset_ex),
    ]
    for model_cls, sample in merchant_samples:
        inst = model_cls.model_validate(sample)
        assert model_cls.model_validate(inst.model_dump(mode="json")) == inst
