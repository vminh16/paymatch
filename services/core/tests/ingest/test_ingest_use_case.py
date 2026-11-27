"""DB tests for ingest use case: sha256 idempotency, duplicate policy, ingest findings, job+outbox atomicity, and poller."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.ingest.application.ingest_invoice import IngestCommand, ingest_invoice
from core.ingest.application.poller import (
    InboxAttachment,
    InboxMessage,
    UtilityBill,
    poll_sources_once,
)
from core.persistence.db import Database
from core.shared.clock import FixedClock
from core.shared.errors import ProblemError

import pathlib

DEMO_DATA_DIR = pathlib.Path(__file__).resolve().parents[4] / "services" / "sim-world" / "data" / "demo"
TENANT_A = "ten_01M88D3C06B97Y4G0S9W8BVKNG"

VN_TZ = timezone(timedelta(hours=7))


def _load_demo_xml(rel_path: str) -> bytes:
    return (DEMO_DATA_DIR / rel_path).read_bytes()


@pytest.mark.db
def test_invariant_sha256_idempotency_is_noop(seeded_db: Database, fixed_clock: FixedClock) -> None:
    """Invariant: re-ingesting identical bytes (same sha256) is a no-op with no DUPLICATE_INVOICE and no extra event."""
    xml_bytes = _load_demo_xml("inbox/attachments/1C26TTN_00001425.xml")

    with seeded_db.connect() as conn:
        first = ingest_invoice(
            conn,
            IngestCommand(
                tenant_id=TENANT_A,
                raw_bytes=xml_bytes,
                filename="1C26TTN_00001425.xml",
                content_type="application/xml",
                source="email",
                message_text="Hóa đơn cà phê hạt đợt 4/11",
            ),
            clock=fixed_clock,
        )
        assert first.already_existed is False
        assert first.status == "investigating"
        assert first.job_id is not None
        assert first.ingest_reason_codes == ()

        second = ingest_invoice(
            conn,
            IngestCommand(
                tenant_id=TENANT_A,
                raw_bytes=xml_bytes,
                filename="1C26TTN_00001425.xml",
                content_type="application/xml",
                source="email",
            ),
            clock=fixed_clock,
        )
        assert second.already_existed is True
        assert second.invoice_id == first.invoice_id
        assert second.job_id == first.job_id

        inv_count = conn.execute(
            "SELECT COUNT(*) AS c FROM core.invoices WHERE tenant_id = %s", (TENANT_A,)
        ).fetchone()["c"]
        outbox_count = conn.execute(
            "SELECT COUNT(*) AS c FROM core.outbox WHERE type = 'invoice.ingested'"
        ).fetchone()["c"]
        dup_findings = conn.execute(
            "SELECT COUNT(*) AS c FROM core.findings WHERE 'DUPLICATE_INVOICE' = ANY(reason_codes)"
        ).fetchone()["c"]
        assert inv_count == 1
        assert outbox_count == 1
        assert dup_findings == 0


@pytest.mark.db
def test_duplicate_policy_upload_409_vs_email_red_finding(
    seeded_db: Database, fixed_clock: FixedClock
) -> None:
    xml_orig = _load_demo_xml("inbox/attachments/1C26TTN_00001425.xml")
    # Different sha256 (unpadded SHDon "1425" vs "00001425"), same business key
    xml_dup = xml_orig.replace(b"<SHDon>00001425</SHDon>", b"<SHDon>1425</SHDon>")
    assert xml_dup != xml_orig

    with seeded_db.connect() as conn:
        first = ingest_invoice(
            conn,
            IngestCommand(
                tenant_id=TENANT_A,
                raw_bytes=xml_orig,
                filename="1C26TTN_00001425.xml",
                content_type="application/xml",
                source="upload",
            ),
            clock=fixed_clock,
        )

        # Upload duplicate -> 409 DUPLICATE_INVOICE, NOT saved
        with pytest.raises(ProblemError) as exc_info:
            ingest_invoice(
                conn,
                IngestCommand(
                    tenant_id=TENANT_A,
                    raw_bytes=xml_dup,
                    filename="dup.xml",
                    content_type="application/xml",
                    source="upload",
                ),
                clock=fixed_clock,
            )
        assert exc_info.value.status == 409
        assert exc_info.value.code == "DUPLICATE_INVOICE"
        assert exc_info.value.existing_invoice_id == first.invoice_id

        # Email duplicate -> saved with duplicate_of + red DUPLICATE_INVOICE Finding
        dup_email = ingest_invoice(
            conn,
            IngestCommand(
                tenant_id=TENANT_A,
                raw_bytes=xml_dup,
                filename="dup.xml",
                content_type="application/xml",
                source="email",
            ),
            clock=fixed_clock,
        )
        assert dup_email.already_existed is False
        assert dup_email.duplicate_of == first.invoice_id
        assert "DUPLICATE_INVOICE" in dup_email.ingest_reason_codes


@pytest.mark.db
def test_ingest_findings_amount_mismatch_unknown_vendor_non_xml(
    seeded_db: Database, fixed_clock: FixedClock
) -> None:
    xml_syrup = _load_demo_xml("inbox/attachments/1C26TAC_00000088.xml")
    # Introduce arithmetic mismatch by altering TgTTTBSo
    xml_bad_math = xml_syrup.replace(b"<TgTTTBSo>8800000</TgTTTBSo>", b"<TgTTTBSo>9999999</TgTTTBSo>")

    with seeded_db.connect() as conn:
        res_xml = ingest_invoice(
            conn,
            IngestCommand(
                tenant_id=TENANT_A,
                raw_bytes=xml_bad_math,
                filename="syrup.xml",
                content_type="application/xml",
                source="email",
            ),
            clock=fixed_clock,
        )
        assert "UNKNOWN_VENDOR" in res_xml.ingest_reason_codes
        assert "AMOUNT_MISMATCH" in res_xml.ingest_reason_codes

        # PDF non-XML source
        res_pdf = ingest_invoice(
            conn,
            IngestCommand(
                tenant_id=TENANT_A,
                raw_bytes=b"%PDF-1.4 fake pdf bytes",
                filename="receipt.pdf",
                content_type="application/pdf",
                source="upload",
            ),
            clock=fixed_clock,
        )
        assert res_pdf.ingest_reason_codes == ("NON_XML_SOURCE",)
        inv = conn.execute(
            "SELECT total_vnd, status FROM core.invoices WHERE invoice_id = %s",
            (res_pdf.invoice_id,),
        ).fetchone()
        assert inv["total_vnd"] is None
        assert inv["status"] == "investigating"


@pytest.mark.db
def test_poller_reads_inbox_and_bills_via_port(seeded_db: Database, fixed_clock: FixedClock) -> None:
    coffee_xml = _load_demo_xml("inbox/attachments/1C26TTN_00001425.xml")
    water_xml = _load_demo_xml("bills/documents/water_sto03_2026-11.xml")

    class FakeSource:
        def list_inbox_messages(self, mailbox: str, after: str | None = None):
            if mailbox == "hoadon@laxanh-fnb.example" and after is None:
                return (
                    [
                        InboxMessage(
                            message_id="msg_01M88TEST00000000000000001",
                            from_address="ketoan@caphetaynguyen.example",
                            subject="HĐ cà phê",
                            body_text="Gửi hóa đơn cà phê",
                            received_at=datetime(2026, 11, 26, 8, 5, tzinfo=VN_TZ),
                            attachments=(
                                InboxAttachment(
                                    attachment_id="att_1",
                                    filename="1C26TTN_00001425.xml",
                                    content_type="application/xml",
                                    raw_bytes=coffee_xml,
                                ),
                            ),
                        )
                    ],
                    "1",
                )
            return [], after

        def list_bills(self, wallet_id: str, after: str | None = None):
            if wallet_id == "wal_01M88AWF62TJ28TZPAQDR9KT4H" and after is None:
                return (
                    [
                        UtilityBill(
                            bill_id="bill_01M88WATER00000000000001",
                            provider="water",
                            customer_code="01109900003",
                            store_ref="sto_01M88F95QCSJH586BGKGH3QDRP",
                            period="2026-11",
                            amount_vnd=4214333,
                            readings={},
                            xml_attachment_id="att_w",
                        )
                    ],
                    "1",
                )
            return [], after

        def fetch_bill_document(self, bill_id: str) -> bytes | None:
            return water_xml

    with seeded_db.connect() as conn:
        first_poll = poll_sources_once(conn, FakeSource(), clock=fixed_clock)
        assert len(first_poll) == 2
        assert all(not r.already_existed for r in first_poll)

        # Second poll with updated cursors is a no-op
        second_poll = poll_sources_once(conn, FakeSource(), clock=fixed_clock)
        assert second_poll == []


@pytest.mark.db
def test_b5_concurrent_same_business_key_upload_vs_email_and_sha_race(
    seeded_db: Database, fixed_clock: FixedClock
) -> None:
    """B5: concurrent ingests of different files sharing the same normalized business key (upload vs email)
    serialize via pg_advisory_xact_lock so ONLY ONE original exists; concurrent same-byte ingests
    arbitrate via ON CONFLICT (tenant_id, sha256) DO NOTHING returning the winning invoice with zero 500s.
    """
    from concurrent.futures import ThreadPoolExecutor
    import threading

    xml_orig = _load_demo_xml("inbox/attachments/1C26TTN_00001425.xml")
    xml_dup = xml_orig.replace(b"<SHDon>00001425</SHDon>", b"<SHDon>1425</SHDon>")
    assert xml_dup != xml_orig

    # --- Race 1: Concurrent upload vs email with DIFFERENT sha256 but SAME normalized business key ---
    barrier1 = threading.Barrier(2)

    def _run_business_key(source: str, raw: bytes):
        with seeded_db.connect() as conn:
            barrier1.wait(timeout=5)
            try:
                return ("ok", ingest_invoice(
                    conn,
                    IngestCommand(
                        tenant_id=TENANT_A,
                        raw_bytes=raw,
                        filename=f"{source}.xml",
                        content_type="application/xml",
                        source=source,  # type: ignore[arg-type]
                    ),
                    clock=fixed_clock,
                ))
            except ProblemError as exc:
                return ("err", exc)

    with ThreadPoolExecutor(max_workers=2) as pool:
        f_up = pool.submit(_run_business_key, "upload", xml_orig)
        f_em = pool.submit(_run_business_key, "email", xml_dup)
        r_up = f_up.result(timeout=15)
        r_em = f_em.result(timeout=15)

    # Either upload won (email got duplicate_of + red DUPLICATE_INVOICE) OR email won (upload got 409 DUPLICATE_INVOICE)
    with seeded_db.connect() as conn:
        invs = conn.execute(
            "SELECT invoice_id, source, duplicate_of, reason_codes FROM core.invoices WHERE tenant_id = %s",
            (TENANT_A,),
        ).fetchall()
    originals = [r for r in invs if r["duplicate_of"] is None]
    assert len(originals) == 1, f"Must admit strictly 1 original, got: {invs}"
    if r_up[0] == "err":
        assert r_up[1].status == 409 and r_up[1].code == "DUPLICATE_INVOICE"
        assert r_em[0] == "ok" and r_em[1].duplicate_of is None
    else:
        assert r_up[0] == "ok" and r_up[1].duplicate_of is None
        assert r_em[0] == "ok" and r_em[1].duplicate_of == r_up[1].invoice_id
        assert "DUPLICATE_INVOICE" in r_em[1].ingest_reason_codes

    # --- Race 2: Concurrent identical-byte (same SHA) ingests -> zero 500s, both return winning invoice ---
    xml_same = _load_demo_xml("inbox/attachments/1C26TTN_00001430.xml")
    barrier2 = threading.Barrier(2)

    def _run_same_sha(idx: int):
        with seeded_db.connect() as conn:
            barrier2.wait(timeout=5)
            return ingest_invoice(
                conn,
                IngestCommand(
                    tenant_id=TENANT_A,
                    raw_bytes=xml_same,
                    filename=f"same_{idx}.xml",
                    content_type="application/xml",
                    source="email",
                ),
                clock=fixed_clock,
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        fs1 = pool.submit(_run_same_sha, 1)
        fs2 = pool.submit(_run_same_sha, 2)
        s1, s2 = fs1.result(timeout=15), fs2.result(timeout=15)

    assert s1.invoice_id == s2.invoice_id
    assert {s1.already_existed, s2.already_existed} == {False, True}

    # --- Race 3: Concurrent identical-byte PDF (no business-key advisory lock -> exercises ON CONFLICT sha256 directly) ---
    pdf_bytes = b"%PDF-1.4\n%concurrent-race-test-payload\n%%EOF\n"
    barrier3 = threading.Barrier(2)

    def _run_same_pdf(idx: int):
        with seeded_db.connect() as conn:
            barrier3.wait(timeout=5)
            return ingest_invoice(
                conn,
                IngestCommand(
                    tenant_id=TENANT_A,
                    raw_bytes=pdf_bytes,
                    filename=f"scan_{idx}.pdf",
                    content_type="application/pdf",
                    source="upload",
                ),
                clock=fixed_clock,
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        fp1 = pool.submit(_run_same_pdf, 1)
        fp2 = pool.submit(_run_same_pdf, 2)
        p1, p2 = fp1.result(timeout=15), fp2.result(timeout=15)

    assert p1.invoice_id == p2.invoice_id
    assert {p1.already_existed, p2.already_existed} == {False, True}


@pytest.mark.db
def test_i10_bounded_ingest_byte_and_xml_element_limits(
    seeded_db: Database, fixed_clock: FixedClock
) -> None:
    """I10: ingest rejects oversized payloads with 413 PAYLOAD_TOO_LARGE and oversized XML element trees with 422."""
    xml_bytes = _load_demo_xml("inbox/attachments/1C26TTN_00001425.xml")
    with seeded_db.connect() as conn:
        with pytest.raises(ProblemError) as exc_sz:
            ingest_invoice(
                conn,
                IngestCommand(
                    tenant_id=TENANT_A,
                    raw_bytes=xml_bytes,
                    filename="big.xml",
                    content_type="application/xml",
                    source="upload",
                ),
                clock=fixed_clock,
                max_invoice_bytes=128,
            )
        assert exc_sz.value.status == 413
        assert exc_sz.value.code == "PAYLOAD_TOO_LARGE"

        with pytest.raises(ProblemError) as exc_el:
            ingest_invoice(
                conn,
                IngestCommand(
                    tenant_id=TENANT_A,
                    raw_bytes=xml_bytes,
                    filename="many_elems.xml",
                    content_type="application/xml",
                    source="upload",
                ),
                clock=fixed_clock,
                max_xml_elements=5,
            )
        assert exc_el.value.status == 422
        assert exc_el.value.code == "XML_UNPARSEABLE"
