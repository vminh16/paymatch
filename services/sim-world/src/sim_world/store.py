"""In-memory state store and dataset loader for sim-world (no database)."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sim_world.errors import ProblemError
from sim_world.ids import new_id
from sim_world.jwt_keys import IdentityKeyStore
from sim_world.webhooks import WebhookDispatcher, WebhookRecord

DATASET_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")
STEP_UP_TTL_SECONDS = 300
SESSION_TOKEN_TTL_SECONDS = 3600


def _parse_rfc3339(value: str, field_name: str) -> datetime:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProblemError(
            status=400,
            code="VALIDATION_FAILED",
            title="Invalid timestamp",
            detail=f"Field '{field_name}' must be a valid RFC 3339 timestamp with timezone.",
            errors=[{"field": field_name, "code": "invalid_timestamp", "detail": str(exc)}],
        ) from exc
    if dt.tzinfo is None:
        raise ProblemError(
            status=400,
            code="VALIDATION_FAILED",
            title="Missing timezone offset",
            detail=f"Field '{field_name}' must include a timezone offset.",
            errors=[{"field": field_name, "code": "missing_timezone"}],
        )
    return dt


def _normalize_invoice_number(number: str) -> str:
    stripped = number.strip()
    if stripped.isdigit():
        return str(int(stripped))
    return stripped


def _safe_dataset_file(dataset_dir: Path, rel_path: str) -> Path:
    resolved = (dataset_dir / rel_path).resolve()
    root = dataset_dir.resolve()
    if not str(resolved).startswith(str(root) + "/") and resolved != root:
        raise ValueError(f"Path escapes dataset directory: {rel_path}")
    return resolved


def _last4_from_id(card_id: str) -> str:
    digest = int(hashlib.sha256(card_id.encode("utf-8")).hexdigest()[:8], 16)
    return f"{digest % 10000:04d}"


class SimWorldStore:
    """Thread-safe in-memory state for all sim-world domains."""

    def __init__(
        self,
        *,
        data_dir: Path,
        keys: IdentityKeyStore,
        webhooks: WebhookDispatcher,
        demo_mode: bool = False,
    ) -> None:
        self._data_dir = data_dir
        self._keys = keys
        self._webhooks_dispatcher = webhooks
        self._demo_mode = demo_mode
        self._lock = threading.RLock()

        self.dataset: str = ""
        self.seed: int = 42
        self.loaded_at: str = ""
        self.ready: bool = False

        self._clock_str: str = ""
        self._clock_dt: datetime = datetime.now(UTC)

        # Loaded static / seed datasets (never loads core_seed/)
        self._demo_otp: str = "123456"
        self._merchant_users: dict[str, dict[str, Any]] = {}
        self._staff_users: dict[str, dict[str, Any]] = {}
        self._wallets: dict[str, dict[str, Any]] = {}
        self._external_bank_accounts: dict[tuple[str, str], dict[str, Any]] = {}
        self._card_merchants: dict[str, dict[str, Any]] = {}

        # Inbox
        self._inbox_templates: dict[str, dict[str, Any]] = {}
        self._attachment_bytes: dict[str, tuple[str, bytes]] = {}
        self._delivered_messages: list[tuple[int, dict[str, Any]]] = []
        self._delivered_message_by_id: dict[str, dict[str, Any]] = {}
        self._msg_seq: int = 0

        # Bills
        self._bill_templates: dict[str, dict[str, Any]] = {}
        self._bill_xml_bytes: dict[str, bytes] = {}
        self._delivered_bills: list[tuple[int, dict[str, Any]]] = []
        self._delivered_bill_by_id: dict[str, dict[str, Any]] = {}
        self._bill_seq: int = 0

        # Chat
        self._chat_threads: dict[str, dict[str, Any]] = {}
        self._chat_template_messages: dict[tuple[str, str], dict[str, Any]] = {}

        # Official lookups
        self._einvoice_index: dict[tuple[str, str, str], dict[str, Any]] = {}
        self._taxpayers: dict[str, dict[str, Any]] = {}
        self._tax_risk_list: dict[str, dict[str, Any]] = {}
        self._simo_indicators: dict[tuple[str, str], dict[str, Any]] = {}
        self._revenues: dict[tuple[str, str, str], dict[str, Any]] = {}

        # Scenarios
        self._scenarios_list: list[dict[str, Any]] = []
        self._scenarios_by_id: dict[str, dict[str, Any]] = {}

        # Runtime mutable ledgers
        self._challenges: dict[str, dict[str, Any]] = {}
        self._transfers: dict[str, tuple[tuple[Any, ...], dict[str, Any]]] = {}
        self._cards_by_key: dict[str, tuple[tuple[Any, ...], dict[str, Any]]] = {}
        self._cards_by_id: dict[str, dict[str, Any]] = {}
        self._escrows_by_key: dict[str, tuple[tuple[Any, ...], dict[str, Any]]] = {}
        self._escrows_by_id: dict[str, dict[str, Any]] = {}
        self._escrow_action_keys: dict[tuple[str, str], str] = {}
        self._webhooks: list[WebhookRecord] = []

    def reset(self, dataset: str, seed: int = 42) -> dict[str, Any]:
        if not DATASET_NAME_RE.fullmatch(dataset):
            raise ProblemError(
                status=400,
                code="VALIDATION_FAILED",
                title="Invalid dataset name",
                detail="Dataset name may only contain letters, digits, hyphens, and underscores.",
                errors=[{"field": "dataset", "code": "invalid_format"}],
            )

        dataset_dir = self._data_dir / dataset
        if not dataset_dir.is_dir() or not (dataset_dir / "manifest.json").is_file():
            raise ProblemError(
                status=404,
                code="NOT_FOUND",
                title="Dataset not found",
                detail=f"Dataset '{dataset}' does not exist in {self._data_dir}.",
            )

        def load_json(rel: str) -> dict[str, Any]:
            return json.loads((dataset_dir / rel).read_text(encoding="utf-8"))

        manifest = load_json("manifest.json")
        identity = load_json("identity.json")
        wallets_data = load_json("wallets.json")
        inbox_data = load_json("inbox/messages.json")
        bills_data = load_json("bills/bills.json")
        chat_data = load_json("chat.json")
        einvoice_data = load_json("einvoice_portal.json")
        taxpayers_data = load_json("taxpayers.json")
        tax_risk_data = load_json("tax_risk_list.json")
        simo_data = load_json("simo_indicators.json")
        revenue_data = load_json("revenue.json")
        scenarios_data = load_json("scenarios.json")

        base_clock = manifest["base_clock"]
        base_clock_dt = _parse_rfc3339(base_clock, "base_clock")

        attachment_bytes: dict[str, tuple[str, bytes]] = {}
        inbox_templates: dict[str, dict[str, Any]] = {}
        delivered_messages: list[tuple[int, dict[str, Any]]] = []
        delivered_message_by_id: dict[str, dict[str, Any]] = {}
        msg_seq = 0

        for raw_msg in inbox_data["messages"]:
            attachments_meta: list[dict[str, Any]] = []
            for att in raw_msg.get("attachments", []):
                f_path = _safe_dataset_file(dataset_dir, att["file_path"])
                raw_bytes = f_path.read_bytes()
                attachment_bytes[att["attachment_id"]] = (att["content_type"], raw_bytes)
                attachments_meta.append(
                    {
                        "attachment_id": att["attachment_id"],
                        "filename": att["filename"],
                        "content_type": att["content_type"],
                        "size": len(raw_bytes),
                    }
                )
            msg_record = {
                "message_id": raw_msg["message_id"],
                "mailbox": raw_msg["mailbox"],
                "from": raw_msg["from"],
                "subject": raw_msg["subject"],
                "body_text": raw_msg["body_text"],
                "received_at": raw_msg["received_at"],
                "attachments": attachments_meta,
            }
            inbox_templates[raw_msg["message_id"]] = msg_record
            if raw_msg.get("delivered_by_default"):
                msg_seq += 1
                delivered_copy = copy.deepcopy(msg_record)
                delivered_messages.append((msg_seq, delivered_copy))
                delivered_message_by_id[delivered_copy["message_id"]] = delivered_copy

        bill_xml_bytes: dict[str, bytes] = {}
        bill_templates: dict[str, dict[str, Any]] = {}
        delivered_bills: list[tuple[int, dict[str, Any]]] = []
        delivered_bill_by_id: dict[str, dict[str, Any]] = {}
        bill_seq = 0

        for raw_bill in bills_data["bills"]:
            if raw_bill.get("xml_file_path"):
                xml_path = _safe_dataset_file(dataset_dir, raw_bill["xml_file_path"])
                bill_xml_bytes[raw_bill["bill_id"]] = xml_path.read_bytes()
            bill_copy = copy.deepcopy(raw_bill)
            bill_templates[raw_bill["bill_id"]] = bill_copy
            if raw_bill.get("delivered_by_default"):
                bill_seq += 1
                active_bill = copy.deepcopy(bill_copy)
                delivered_bills.append((bill_seq, active_bill))
                delivered_bill_by_id[active_bill["bill_id"]] = active_bill

        chat_threads: dict[str, dict[str, Any]] = {}
        chat_template_messages: dict[tuple[str, str], dict[str, Any]] = {}
        for raw_thr in chat_data["threads"]:
            delivered_chat: list[dict[str, Any]] = []
            for m in raw_thr.get("messages", []):
                m_clean = {
                    "message_id": m["message_id"],
                    "from": m["from"],
                    "text": m["text"],
                    "sent_at": m["sent_at"],
                }
                chat_template_messages[(raw_thr["thread_id"], m["message_id"])] = m_clean
                if m.get("delivered_by_default"):
                    delivered_chat.append(copy.deepcopy(m_clean))
            chat_threads[raw_thr["thread_id"]] = {
                "thread_id": raw_thr["thread_id"],
                "tenant_ref": raw_thr["tenant_ref"],
                "counterparty_name": raw_thr["counterparty_name"],
                "counterparty_phone": raw_thr["counterparty_phone"],
                "messages": delivered_chat,
            }

        einvoice_index: dict[tuple[str, str, str], dict[str, Any]] = {}
        for inv in einvoice_data["invoices"]:
            key = (
                inv["seller_tax_id"].strip(),
                inv["symbol"].strip(),
                _normalize_invoice_number(str(inv["number"])),
            )
            einvoice_index[key] = copy.deepcopy(inv)

        with self._lock:
            self.dataset = dataset
            self.seed = seed
            self._clock_str = base_clock
            self._clock_dt = base_clock_dt
            self.loaded_at = datetime.now(base_clock_dt.tzinfo).isoformat(timespec="seconds")

            self._demo_otp = str(identity.get("demo_otp", "123456"))
            self._merchant_users = {u["user_id"]: copy.deepcopy(u) for u in identity["merchant_users"]}
            self._staff_users = {s["staff_id"]: copy.deepcopy(s) for s in identity["staff_users"]}

            self._wallets = {w["wallet_id"]: copy.deepcopy(w) for w in wallets_data["wallets"]}
            self._external_bank_accounts = {
                (a["bank_code"].strip().upper(), a["account_number"].strip()): copy.deepcopy(a)
                for a in wallets_data["external_bank_accounts"]
            }
            self._card_merchants = {
                m["merchant_id"]: copy.deepcopy(m) for m in wallets_data.get("card_merchants", [])
            }

            self._inbox_templates = inbox_templates
            self._attachment_bytes = attachment_bytes
            self._delivered_messages = delivered_messages
            self._delivered_message_by_id = delivered_message_by_id
            self._msg_seq = msg_seq

            self._bill_templates = bill_templates
            self._bill_xml_bytes = bill_xml_bytes
            self._delivered_bills = delivered_bills
            self._delivered_bill_by_id = delivered_bill_by_id
            self._bill_seq = bill_seq

            self._chat_threads = chat_threads
            self._chat_template_messages = chat_template_messages

            self._einvoice_index = einvoice_index
            self._taxpayers = {t["tax_id"]: copy.deepcopy(t) for t in taxpayers_data["taxpayers"]}
            self._tax_risk_list = {e["tax_id"]: copy.deepcopy(e) for e in tax_risk_data["entries"]}
            self._simo_indicators = {
                (i["kind"], i["value_hash"].lower()): copy.deepcopy(i)
                for i in simo_data["indicators"]
            }
            self._revenues = {
                (r["wallet_id"], r["store_ref"], r["month"]): copy.deepcopy(r)
                for r in revenue_data["revenues"]
            }

            self._scenarios_list = copy.deepcopy(scenarios_data["scenarios"])
            self._scenarios_by_id = {s["template_id"]: s for s in self._scenarios_list}

            # Clear runtime state
            self._challenges = {}
            self._transfers = {}
            self._cards_by_key = {}
            self._cards_by_id = {}
            self._escrows_by_key = {}
            self._escrows_by_id = {}
            self._escrow_action_keys = {}
            self._webhooks = []
            self.ready = True

            return {
                "loaded_at": self.loaded_at,
                "counts": {
                    "merchant_users": len(self._merchant_users),
                    "staff_users": len(self._staff_users),
                    "wallets": len(self._wallets),
                    "inbox_messages": len(self._inbox_templates),
                    "delivered_inbox_messages": len(self._delivered_messages),
                    "bills": len(self._bill_templates),
                    "delivered_bills": len(self._delivered_bills),
                    "chat_threads": len(self._chat_threads),
                    "einvoice_invoices": len(self._einvoice_index),
                    "taxpayers": len(self._taxpayers),
                    "scenarios": len(self._scenarios_list),
                },
            }

    # --- Identity ---

    def issue_merchant_token(self, user_id: str) -> str:
        with self._lock:
            user = self._merchant_users.get(user_id)
        if user is None:
            raise ProblemError(
                status=404,
                code="NOT_FOUND",
                title="Merchant user not found",
                detail=f"Unknown user_id '{user_id}'.",
            )
        now = int(time.time())
        claims = {
            "iss": "sim-world",
            "aud": "paymatch",
            "sub": user["user_id"],
            "tenant_id": user["tenant_id"],
            "role": user["role"],
            "store_ids": user["store_ids"],
            "name": user["name"],
            "email": user["email"],
            "token_use": "momo_token",
            "iat": now,
            "exp": now + SESSION_TOKEN_TTL_SECONDS,
            "jti": new_id("jti"),
        }
        return self._keys.sign(claims)

    def issue_staff_token(self, staff_id: str) -> str:
        with self._lock:
            staff = self._staff_users.get(staff_id)
        if staff is None:
            raise ProblemError(
                status=404,
                code="NOT_FOUND",
                title="Staff user not found",
                detail=f"Unknown staff_id '{staff_id}'.",
            )
        now = int(time.time())
        claims = {
            "iss": "sim-world",
            "aud": "paymatch-console",
            "sub": staff["staff_id"],
            "name": staff["name"],
            "staff_roles": staff["staff_roles"],
            "token_use": "sso_token",
            "iat": now,
            "exp": now + SESSION_TOKEN_TTL_SECONDS,
            "jti": new_id("jti"),
        }
        return self._keys.sign(claims)

    def create_step_up_challenge(self, momo_token: str, action_hash: str) -> dict[str, Any]:
        claims = self._keys.verify(momo_token, audience="paymatch")
        if claims.get("token_use") != "momo_token":
            raise ProblemError(
                status=401,
                code="UNAUTHENTICATED",
                title="Invalid token type",
                detail="Step-up challenges require a momo_token.",
            )
        challenge_id = new_id("chl")
        now_ts = int(time.time())
        exp_ts = now_ts + STEP_UP_TTL_SECONDS
        with self._lock:
            # Same wall clock as the JWT exp that core checks (SystemClock), not the advanceable demo clock.
            expires_at = datetime.fromtimestamp(exp_ts, self._clock_dt.tzinfo).isoformat()
            otp = self._demo_otp
            self._challenges[challenge_id] = {
                "challenge_id": challenge_id,
                "sub": claims["sub"],
                "tenant_id": claims.get("tenant_id"),
                "action_hash": action_hash,
                "otp": otp,
                "exp_ts": exp_ts,
                "expires_at": expires_at,
                "verified": False,
            }
        return {
            "challenge_id": challenge_id,
            "expires_at": expires_at,
            "demo_otp": otp if self._demo_mode else None,
        }

    def verify_step_up_challenge(self, challenge_id: str, otp: str) -> str:
        with self._lock:
            ch = self._challenges.get(challenge_id)
            if ch is None:
                raise ProblemError(
                    status=404,
                    code="NOT_FOUND",
                    title="Challenge not found",
                    detail=f"Unknown challenge_id '{challenge_id}'.",
                )
            if ch["verified"]:
                raise ProblemError(
                    status=409,
                    code="INVALID_STATE",
                    title="Challenge already verified",
                    detail="This step-up challenge has already been consumed.",
                )
            now_ts = int(time.time())
            if now_ts > ch["exp_ts"]:
                raise ProblemError(
                    status=401,
                    code="TOKEN_EXPIRED",
                    title="Challenge expired",
                    detail="This step-up challenge has expired.",
                )
            if otp != ch["otp"]:
                raise ProblemError(
                    status=403,
                    code="STEP_UP_INVALID",
                    title="Invalid OTP",
                    detail="The provided OTP does not match.",
                )
            ch["verified"] = True
            sub = ch["sub"]
            action_hash = ch["action_hash"]

        claims = {
            "iss": "sim-world",
            "aud": "paymatch",
            "sub": sub,
            "action_hash": action_hash,
            "jti": new_id("jti"),
            "iat": now_ts,
            "exp": now_ts + STEP_UP_TTL_SECONDS,
            "amr": ["otp"],
            "token_use": "auth_proof",
        }
        return self._keys.sign(claims)

    # --- Rails ---

    def _emit_webhook(self, event_type: str, data: dict[str, Any], occurred_at: str) -> None:
        record = WebhookRecord(
            event_id=new_id("evt"), type=event_type, occurred_at=occurred_at, data=data, delivered=False
        )
        with self._lock:
            self._webhooks.append(record)

        def deliver() -> None:
            result = self._webhooks_dispatcher.dispatch(
                event_id=record.event_id, event_type=event_type, occurred_at=occurred_at, data=data
            )
            with self._lock:
                record.delivered, record.error = result.delivered, result.error

        # Retries take up to ~10 s when core is down; the rail caller (gate, 5 s timeout) must not wait on them.
        threading.Thread(target=deliver, daemon=True).start()

    def create_transfer(
        self,
        *,
        idempotency_key: str,
        from_wallet_id: str,
        bank_code: str,
        account_number: str,
        account_name: str,
        amount_vnd: int,
        memo: str,
    ) -> dict[str, Any]:
        fingerprint = (
            from_wallet_id,
            bank_code.strip().upper(),
            account_number.strip(),
            account_name.strip(),
            amount_vnd,
            memo,
        )
        with self._lock:
            existing = self._transfers.get(idempotency_key)
            if existing is not None:
                prev_fp, prev_resp = existing
                if prev_fp != fingerprint:
                    raise ProblemError(
                        status=409,
                        code="IDEMPOTENCY_KEY_REUSED",
                        title="Idempotency key reused with different payload",
                        detail=f"Transfer key '{idempotency_key}' was already used with different parameters.",
                    )
                return copy.deepcopy(prev_resp)

            wallet = self._wallets.get(from_wallet_id)
            if wallet is None:
                raise ProblemError(
                    status=404,
                    code="NOT_FOUND",
                    title="Wallet not found",
                    detail=f"Unknown wallet_id '{from_wallet_id}'.",
                )

            ext = self._external_bank_accounts.get((bank_code.strip().upper(), account_number.strip()))
            failure_code: str | None = None
            if ext is None:
                failure_code = "ACCOUNT_NOT_FOUND"
            elif ext.get("simulate_failure"):
                failure_code = ext["simulate_failure"]
            elif account_name.strip().upper() != ext["account_name"].strip().upper():
                failure_code = "NAME_MISMATCH"
            elif wallet["balance_vnd"] < amount_vnd:
                failure_code = "INSUFFICIENT_FUNDS"

            rail_txn_id = new_id("rtx")
            occurred_at = self._clock_str
            if failure_code is None:
                wallet["balance_vnd"] -= amount_vnd
                wallet["as_of"] = occurred_at
                resp = {
                    "rail_txn_id": rail_txn_id,
                    "status": "settled",
                    "failure_code": None,
                    "settled_at": occurred_at,
                }
                event_type = "transfer.settled"
            else:
                resp = {
                    "rail_txn_id": rail_txn_id,
                    "status": "failed",
                    "failure_code": failure_code,
                    "settled_at": None,
                }
                event_type = "transfer.failed"

            self._transfers[idempotency_key] = (fingerprint, resp)

        self._emit_webhook(
            event_type,
            {
                "rail_txn_id": rail_txn_id,
                "idempotency_key": idempotency_key,
                "status": resp["status"],
                "failure_code": resp["failure_code"],
            },
            occurred_at,
        )
        return copy.deepcopy(resp)

    def get_transfer(self, idempotency_key: str) -> dict[str, Any]:
        with self._lock:
            existing = self._transfers.get(idempotency_key)
        if existing is None:
            raise ProblemError(
                status=404,
                code="NOT_FOUND",
                title="Transfer not found",
                detail=f"No transfer found for idempotency_key '{idempotency_key}'.",
            )
        return copy.deepcopy(existing[1])

    def create_card(
        self,
        *,
        idempotency_key: str,
        from_wallet_id: str,
        merchant_id: str,
        amount_vnd: int,
        single_use: bool = True,
    ) -> dict[str, Any]:
        fingerprint = (from_wallet_id, merchant_id, amount_vnd, single_use)
        with self._lock:
            existing = self._cards_by_key.get(idempotency_key)
            if existing is not None:
                prev_fp, card = existing
                if prev_fp != fingerprint:
                    raise ProblemError(
                        status=409,
                        code="IDEMPOTENCY_KEY_REUSED",
                        title="Idempotency key reused with different payload",
                        detail=f"Card key '{idempotency_key}' was already used with different parameters.",
                    )
                return {
                    "card_id": card["card_id"],
                    "last4": card["last4"],
                    "status": card["status"],
                }

            wallet = self._wallets.get(from_wallet_id)
            if wallet is None:
                raise ProblemError(
                    status=404,
                    code="NOT_FOUND",
                    title="Wallet not found",
                    detail=f"Unknown wallet_id '{from_wallet_id}'.",
                )
            if wallet["balance_vnd"] < amount_vnd:
                raise ProblemError(
                    status=409,
                    code="INVALID_STATE",
                    title="Insufficient wallet balance",
                    detail="Wallet balance is lower than the requested card amount.",
                )

            # v1 captures immediately on issuance per gate-api.md & sim-world-api.md §2
            wallet["balance_vnd"] -= amount_vnd
            wallet["as_of"] = self._clock_str

            card_id = new_id("crd")
            card = {
                "card_id": card_id,
                "last4": _last4_from_id(card_id),
                "from_wallet_id": from_wallet_id,
                "merchant_id": merchant_id,
                "amount_vnd": amount_vnd,
                "single_use": single_use,
                "status": "captured",
                "captures": [
                    {
                        "merchant_id": merchant_id,
                        "amount_vnd": amount_vnd,
                        "captured_at": self._clock_str,
                    }
                ],
                "declined_attempts": [],
            }
            self._cards_by_key[idempotency_key] = (fingerprint, card)
            self._cards_by_id[card_id] = card
            return {
                "card_id": card["card_id"],
                "last4": card["last4"],
                "status": card["status"],
            }

    def get_card(self, card_id: str) -> dict[str, Any]:
        with self._lock:
            card = self._cards_by_id.get(card_id)
            if card is None:
                raise ProblemError(
                    status=404,
                    code="NOT_FOUND",
                    title="Card not found",
                    detail=f"Unknown card_id '{card_id}'.",
                )
            return {
                "card_id": card["card_id"],
                "status": card["status"],
                "captures": copy.deepcopy(card["captures"]),
                "declined_attempts": copy.deepcopy(card["declined_attempts"]),
            }

    def swipe_card(self, card_id: str, *, merchant_id: str, amount_vnd: int) -> dict[str, Any]:
        decline_reason: str | None = None
        occurred_at: str
        with self._lock:
            card = self._cards_by_id.get(card_id)
            if card is None:
                raise ProblemError(
                    status=404,
                    code="NOT_FOUND",
                    title="Card not found",
                    detail=f"Unknown card_id '{card_id}'.",
                )
            occurred_at = self._clock_str
            if merchant_id != card["merchant_id"]:
                decline_reason = "wrong_merchant"
            elif card["status"] == "captured" and card["single_use"]:
                decline_reason = "already_used"
            elif amount_vnd > card["amount_vnd"]:
                decline_reason = "over_amount"

            if decline_reason is None:
                card["status"] = "captured"
                card["captures"].append(
                    {
                        "merchant_id": merchant_id,
                        "amount_vnd": amount_vnd,
                        "captured_at": occurred_at,
                    }
                )
                return {"approved": True, "reason": None}

            card["declined_attempts"].append(
                {
                    "merchant_id": merchant_id,
                    "amount_vnd": amount_vnd,
                    "reason": decline_reason,
                    "at": occurred_at,
                }
            )

        self._emit_webhook(
            "card.authorization_declined",
            {
                "card_id": card_id,
                "merchant_id": merchant_id,
                "reason": decline_reason,
            },
            occurred_at,
        )
        return {"approved": False, "reason": decline_reason}

    def create_escrow(
        self,
        *,
        idempotency_key: str,
        from_wallet_id: str,
        to: dict[str, str],
        amount_vnd: int,
        expires_on: str,
    ) -> dict[str, Any]:
        fingerprint = (
            from_wallet_id,
            to["bank_code"].strip().upper(),
            to["account_number"].strip(),
            to["account_name"].strip(),
            amount_vnd,
            expires_on,
        )
        with self._lock:
            existing = self._escrows_by_key.get(idempotency_key)
            if existing is not None:
                prev_fp, esc = existing
                if prev_fp != fingerprint:
                    raise ProblemError(
                        status=409,
                        code="IDEMPOTENCY_KEY_REUSED",
                        title="Idempotency key reused with different payload",
                        detail=f"Escrow key '{idempotency_key}' was already used with different parameters.",
                    )
                return {"rail_escrow_id": esc["rail_escrow_id"], "status": esc["status"]}

            wallet = self._wallets.get(from_wallet_id)
            if wallet is None:
                raise ProblemError(
                    status=404,
                    code="NOT_FOUND",
                    title="Wallet not found",
                    detail=f"Unknown wallet_id '{from_wallet_id}'.",
                )
            if wallet["balance_vnd"] < amount_vnd:
                raise ProblemError(
                    status=409,
                    code="INVALID_STATE",
                    title="Insufficient wallet balance",
                    detail="Wallet balance is lower than the requested escrow amount.",
                )

            wallet["balance_vnd"] -= amount_vnd
            wallet["as_of"] = self._clock_str
            rail_escrow_id = new_id("resc")
            escrow = {
                "rail_escrow_id": rail_escrow_id,
                "from_wallet_id": from_wallet_id,
                "to": copy.deepcopy(to),
                "amount_vnd": amount_vnd,
                "expires_on": expires_on,
                "status": "held",
                "created_at": self._clock_str,
            }
            self._escrows_by_key[idempotency_key] = (fingerprint, escrow)
            self._escrows_by_id[rail_escrow_id] = escrow
            return {"rail_escrow_id": rail_escrow_id, "status": "held"}

    def release_escrow(self, rail_escrow_id: str, idempotency_key: str) -> dict[str, Any]:
        with self._lock:
            esc = self._escrows_by_id.get(rail_escrow_id)
            if esc is None:
                raise ProblemError(
                    status=404,
                    code="NOT_FOUND",
                    title="Escrow not found",
                    detail=f"Unknown rail_escrow_id '{rail_escrow_id}'.",
                )
            prev_action = self._escrow_action_keys.get((rail_escrow_id, idempotency_key))
            if prev_action == "released":
                return {"status": "released"}
            if esc["status"] != "held":
                raise ProblemError(
                    status=409,
                    code="INVALID_STATE",
                    title="Escrow not in held state",
                    detail=f"Escrow '{rail_escrow_id}' is currently '{esc['status']}'.",
                )
            esc["status"] = "released"
            self._escrow_action_keys[(rail_escrow_id, idempotency_key)] = "released"
            return {"status": "released"}

    def refund_escrow(self, rail_escrow_id: str, idempotency_key: str) -> dict[str, Any]:
        with self._lock:
            esc = self._escrows_by_id.get(rail_escrow_id)
            if esc is None:
                raise ProblemError(
                    status=404,
                    code="NOT_FOUND",
                    title="Escrow not found",
                    detail=f"Unknown rail_escrow_id '{rail_escrow_id}'.",
                )
            prev_action = self._escrow_action_keys.get((rail_escrow_id, idempotency_key))
            if prev_action == "refunded":
                return {"status": "refunded"}
            if esc["status"] != "held":
                raise ProblemError(
                    status=409,
                    code="INVALID_STATE",
                    title="Escrow not in held state",
                    detail=f"Escrow '{rail_escrow_id}' is currently '{esc['status']}'.",
                )
            esc["status"] = "refunded"
            wallet = self._wallets.get(esc["from_wallet_id"])
            if wallet is not None:
                wallet["balance_vnd"] += esc["amount_vnd"]
                wallet["as_of"] = self._clock_str
            self._escrow_action_keys[(rail_escrow_id, idempotency_key)] = "refunded"
            return {"status": "refunded"}

    def get_wallet(self, wallet_id: str) -> dict[str, Any]:
        with self._lock:
            wallet = self._wallets.get(wallet_id)
        if wallet is None:
            raise ProblemError(
                status=404,
                code="NOT_FOUND",
                title="Wallet not found",
                detail=f"Unknown wallet_id '{wallet_id}'.",
            )
        return {
            "wallet_id": wallet["wallet_id"],
            "balance_vnd": wallet["balance_vnd"],
            "as_of": wallet["as_of"],
        }

    # --- Inbox & Bills ---

    def _resolve_after_seq(
        self,
        items: list[tuple[int, dict[str, Any]]],
        id_field: str,
        after: str | None,
    ) -> int:
        # A cursor from before /sim/scenario:reset (unknown id, or past the end) restarts from the top:
        # pollers would otherwise stall forever, and core ingest is idempotent on sha256 so replays are no-ops.
        last_seq = items[-1][0] if items else 0
        if not after:
            return 0
        if after.isdigit():
            return int(after) if int(after) <= last_seq else 0
        return next((seq for seq, item in items if item[id_field] == after), 0)

    def list_inbox_messages(
        self,
        *,
        mailbox: str,
        after: str | None = None,
        from_addr: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        with self._lock:
            min_seq = self._resolve_after_seq(self._delivered_messages, "message_id", after)
            filtered: list[tuple[int, dict[str, Any]]] = []
            for seq, msg in self._delivered_messages:
                if seq <= min_seq:
                    continue
                if msg["mailbox"] != mailbox:
                    continue
                if from_addr is not None and msg["from"] != from_addr:
                    continue
                filtered.append((seq, msg))

            page = filtered[:limit]
            has_more = len(filtered) > limit
            next_cursor = str(page[-1][0]) if (has_more and page) else None
            items = [
                {
                    "message_id": m["message_id"],
                    "from": m["from"],
                    "subject": m["subject"],
                    "body_text": m["body_text"],
                    "received_at": m["received_at"],
                    "attachments": copy.deepcopy(m["attachments"]),
                }
                for _, m in page
            ]
        return {"items": items, "next_cursor": next_cursor}

    def get_inbox_attachment(self, message_id: str, attachment_id: str) -> tuple[str, bytes]:
        with self._lock:
            msg = self._delivered_message_by_id.get(message_id)
            if msg is None:
                raise ProblemError(
                    status=404,
                    code="NOT_FOUND",
                    title="Message not found",
                    detail=f"Message '{message_id}' not found in delivered inbox.",
                )
            att_ids = {a["attachment_id"] for a in msg["attachments"]}
            if attachment_id not in att_ids or attachment_id not in self._attachment_bytes:
                raise ProblemError(
                    status=404,
                    code="NOT_FOUND",
                    title="Attachment not found",
                    detail=f"Attachment '{attachment_id}' not found on message '{message_id}'.",
                )
            return self._attachment_bytes[attachment_id]

    def _public_bill(self, bill: dict[str, Any]) -> dict[str, Any]:
        return {
            "bill_id": bill["bill_id"],
            "provider": bill["provider"],
            "vendor_tax_id": bill.get("vendor_tax_id"),
            "customer_code": bill["customer_code"],
            "store_ref": bill["store_ref"],
            "period": bill["period"],
            "period_start": bill.get("period_start"),
            "period_end": bill.get("period_end"),
            "billing_days": bill.get("billing_days"),
            "due_date": bill.get("due_date"),
            "statement_no": bill.get("statement_no"),
            "total_usage": bill.get("total_usage"),
            "usage_unit": bill.get("usage_unit"),
            "subtotal_vnd": bill.get("subtotal_vnd"),
            "vat_total_vnd": bill.get("vat_total_vnd"),
            "amount_vnd": bill["amount_vnd"],
            "readings": copy.deepcopy(bill["readings"]),
            "xml_attachment_id": bill.get("xml_attachment_id"),
        }

    def list_bills(
        self,
        *,
        wallet_id: str,
        after: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        with self._lock:
            min_seq = self._resolve_after_seq(self._delivered_bills, "bill_id", after)
            filtered = [
                (seq, b)
                for seq, b in self._delivered_bills
                if seq > min_seq and b["wallet_id"] == wallet_id
            ]
            page = filtered[:limit]
            has_more = len(filtered) > limit
            next_cursor = str(page[-1][0]) if (has_more and page) else None
            items = [self._public_bill(b) for _, b in page]
        return {"items": items, "next_cursor": next_cursor}

    def get_bill_document(self, bill_id: str) -> bytes:
        with self._lock:
            if bill_id not in self._delivered_bill_by_id:
                raise ProblemError(
                    status=404,
                    code="NOT_FOUND",
                    title="Bill not found",
                    detail=f"Bill '{bill_id}' not found in delivered bills.",
                )
            raw = self._bill_xml_bytes.get(bill_id)
        if raw is None:
            raise ProblemError(
                status=404,
                code="NOT_FOUND",
                title="Bill XML document not available",
                detail=f"Bill '{bill_id}' does not have an attached XML document.",
            )
        return raw

    # --- Chat ---

    def list_chat_threads(
        self,
        *,
        tenant_ref: str,
        counterparty_phone: str | None = None,
    ) -> list[dict[str, Any]]:
        with self._lock:
            result: list[dict[str, Any]] = []
            for thr in self._chat_threads.values():
                if thr["tenant_ref"] != tenant_ref:
                    continue
                if counterparty_phone is not None and thr["counterparty_phone"] != counterparty_phone:
                    continue
                result.append(
                    {
                        "thread_id": thr["thread_id"],
                        "counterparty_name": thr["counterparty_name"],
                        "counterparty_phone": thr["counterparty_phone"],
                    }
                )
        return result

    def list_chat_messages(self, thread_id: str, *, since: str | None = None) -> list[dict[str, Any]]:
        since_dt = _parse_rfc3339(since, "since") if since is not None else None
        with self._lock:
            thr = self._chat_threads.get(thread_id)
            if thr is None:
                raise ProblemError(
                    status=404,
                    code="NOT_FOUND",
                    title="Chat thread not found",
                    detail=f"Unknown thread_id '{thread_id}'.",
                )
            messages = copy.deepcopy(thr["messages"])

        if since_dt is None:
            return messages
        return [
            m for m in messages if _parse_rfc3339(m["sent_at"], "sent_at") >= since_dt
        ]

    def inject_chat_message(self, thread_id: str, text: str) -> dict[str, Any]:
        with self._lock:
            thr = self._chat_threads.get(thread_id)
            if thr is None:
                raise ProblemError(
                    status=404,
                    code="NOT_FOUND",
                    title="Chat thread not found",
                    detail=f"Unknown thread_id '{thread_id}'.",
                )
            msg = {
                "message_id": new_id("msg"),
                "from": "counterparty",
                "text": text,
                "sent_at": self._clock_str,
            }
            thr["messages"].append(msg)
            return {
                "message_id": msg["message_id"],
                "thread_id": thread_id,
                "from": msg["from"],
                "text": msg["text"],
                "sent_at": msg["sent_at"],
            }

    # --- Official Lookups ---

    def lookup_einvoice(self, *, seller_tax_id: str, symbol: str, number: str) -> dict[str, Any]:
        key = (seller_tax_id.strip(), symbol.strip(), _normalize_invoice_number(number))
        with self._lock:
            inv = self._einvoice_index.get(key)
        if inv is None:
            return {
                "found": False,
                "invoice_status_code": None,
                "invoice_status_label": None,
                "processing_status_code": None,
                "processing_status_label": None,
                "illegal_flag": None,
                "tax_authority_code": None,
                "total_vnd": None,
                "related_invoice": None,
            }
        return {
            "found": True,
            "invoice_status_code": inv["invoice_status_code"],
            "invoice_status_label": inv["invoice_status_label"],
            "processing_status_code": inv["processing_status_code"],
            "processing_status_label": inv["processing_status_label"],
            "illegal_flag": inv["illegal_flag"],
            "tax_authority_code": inv["tax_authority_code"],
            "total_vnd": inv["total_vnd"],
            "related_invoice": copy.deepcopy(inv.get("related_invoice")),
        }

    def get_taxpayer(self, tax_id: str) -> dict[str, Any]:
        with self._lock:
            tp = self._taxpayers.get(tax_id.strip())
        if tp is None:
            raise ProblemError(
                status=404,
                code="NOT_FOUND",
                title="Taxpayer not found",
                detail=f"No taxpayer found for tax_id '{tax_id}'.",
            )
        return {
            "tax_id": tp["tax_id"],
            "name": tp["name"],
            "status_code": tp["status_code"],
            "status_label": tp["status_label"],
            "status_reason_code": tp.get("status_reason_code"),
            "address": tp["address"],
        }

    def get_tax_risk_list(self, tax_id: str) -> dict[str, Any]:
        with self._lock:
            entry = self._tax_risk_list.get(tax_id.strip())
        if entry is None:
            return {"listed": False, "list_name": None, "listed_on": None}
        return {
            "listed": bool(entry["listed"]),
            "list_name": entry.get("list_name"),
            "listed_on": entry.get("listed_on"),
        }

    def check_simo(self, *, kind: str, value_hash: str) -> dict[str, Any]:
        with self._lock:
            ind = self._simo_indicators.get((kind, value_hash.strip().lower()))
        if ind is None:
            return {"listed": False, "list_ref": None}
        return {"listed": bool(ind["listed"]), "list_ref": ind.get("list_ref")}

    def get_revenue(self, *, wallet_id: str, store_ref: str, month: str) -> dict[str, Any]:
        with self._lock:
            row = self._revenues.get((wallet_id, store_ref, month))
        if row is None:
            raise ProblemError(
                status=404,
                code="NOT_FOUND",
                title="Revenue record not found",
                detail=f"No revenue data for wallet='{wallet_id}', store='{store_ref}', month='{month}'.",
            )
        return {
            "revenue_vnd": row["revenue_vnd"],
            "transaction_count": row["transaction_count"],
        }

    # --- Scenario Controls ---

    def get_scenario_state(self) -> dict[str, Any]:
        with self._lock:
            return {
                "dataset": self.dataset,
                "seed": self.seed,
                "loaded_at": self.loaded_at,
                "clock": self._clock_str,
                "inbox_count": len(self._delivered_messages),
                "bills_count": len(self._delivered_bills),
                "wallets": [copy.deepcopy(w) for w in self._wallets.values()],
                "cards": [
                    {
                        "card_id": c["card_id"],
                        "merchant_id": c["merchant_id"],
                        "amount_vnd": c["amount_vnd"],
                        "last4": c["last4"],
                        "status": c["status"],
                        "captures_count": len(c["captures"]),
                        "declined_attempts_count": len(c["declined_attempts"]),
                    }
                    for c in self._cards_by_id.values()
                ],
                "escrows_count": len(self._escrows_by_id),
                "transfers_count": len(self._transfers),
                "webhooks": [w.to_dict() for w in self._webhooks],
            }

    def get_scenario_catalog(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {
                    "template_id": s["template_id"],
                    "title": s["title"],
                    "expected_severity": s.get("expected_severity"),
                    "expected_reason_codes": list(s.get("expected_reason_codes", [])),
                    "group": s.get("group"),
                    "channel": s.get("channel"),
                    "notes": s.get("notes"),
                }
                for s in self._scenarios_list
            ]

    def _deliver_inbox_template(
        self,
        template_msg_id: str,
        overrides: dict[str, Any] | None = None,
    ) -> str:
        tmpl = self._inbox_templates.get(template_msg_id)
        if tmpl is None:
            raise ProblemError(
                status=404,
                code="NOT_FOUND",
                title="Scenario message missing",
                detail=f"Template message '{template_msg_id}' not found in dataset.",
            )

        already_delivered = template_msg_id in self._delivered_message_by_id
        if already_delivered and not overrides:
            return template_msg_id

        delivered = copy.deepcopy(tmpl)
        if already_delivered:
            delivered["message_id"] = new_id("msg")
            delivered["received_at"] = self._clock_str
        else:
            delivered["received_at"] = self._clock_str

        if overrides:
            for field in ("mailbox", "from", "subject", "body_text", "received_at"):
                if field in overrides and overrides[field] is not None:
                    delivered[field] = overrides[field]

        self._msg_seq += 1
        self._delivered_messages.append((self._msg_seq, delivered))
        self._delivered_message_by_id[delivered["message_id"]] = delivered
        return delivered["message_id"]

    def _deliver_bill_template(
        self,
        template_bill_id: str,
        overrides: dict[str, Any] | None = None,
    ) -> str:
        tmpl = self._bill_templates.get(template_bill_id)
        if tmpl is None:
            raise ProblemError(
                status=404,
                code="NOT_FOUND",
                title="Scenario bill missing",
                detail=f"Template bill '{template_bill_id}' not found in dataset.",
            )

        already_delivered = template_bill_id in self._delivered_bill_by_id
        if already_delivered and not overrides:
            return template_bill_id

        delivered = copy.deepcopy(tmpl)
        if already_delivered:
            new_bill_id = new_id("bill")
            if template_bill_id in self._bill_xml_bytes:
                self._bill_xml_bytes[new_bill_id] = self._bill_xml_bytes[template_bill_id]
            delivered["bill_id"] = new_bill_id

        if overrides:
            for field in ("period", "amount_vnd", "subtotal_vnd", "vat_total_vnd", "total_usage", "due_date"):
                if field in overrides and overrides[field] is not None:
                    delivered[field] = overrides[field]

        self._bill_seq += 1
        self._delivered_bills.append((self._bill_seq, delivered))
        self._delivered_bill_by_id[delivered["bill_id"]] = delivered
        return delivered["bill_id"]

    def send_scenario_invoice(
        self,
        *,
        template_id: str,
        overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            sc = self._scenarios_by_id.get(template_id)
            if sc is None:
                raise ProblemError(
                    status=404,
                    code="NOT_FOUND",
                    title="Scenario template not found",
                    detail=f"Unknown template_id '{template_id}'.",
                )
            if sc.get("channel") == "card_swipe":
                raise ProblemError(
                    status=409,
                    code="INVALID_STATE",
                    title="Scenario uses card swipe endpoint",
                    detail="Trigger card swipe scenarios via POST /sim/scenario/cards/{card_id}:swipe.",
                )

            result: dict[str, Any] = {}
            if sc.get("message_id"):
                result["message_id"] = self._deliver_inbox_template(sc["message_id"], overrides)
                extras = sc.get("extra_message_ids") or []
                if extras:
                    result["extra_message_ids"] = [
                        self._deliver_inbox_template(extra_id, None) for extra_id in extras
                    ]

            if sc.get("bill_id"):
                result["bill_id"] = self._deliver_bill_template(sc["bill_id"], overrides)

            chat_ids: list[str] = []
            for inj in sc.get("chat_injections") or []:
                thr = self._chat_threads.get(inj["thread_id"])
                tmpl_chat = self._chat_template_messages.get((inj["thread_id"], inj["message_id"]))
                if thr is not None and tmpl_chat is not None:
                    existing_ids = {m["message_id"] for m in thr["messages"]}
                    if tmpl_chat["message_id"] not in existing_ids:
                        delivered_chat = copy.deepcopy(tmpl_chat)
                        delivered_chat["sent_at"] = self._clock_str
                        thr["messages"].append(delivered_chat)
                    chat_ids.append(tmpl_chat["message_id"])
            if chat_ids:
                result["chat_message_ids"] = chat_ids
                if "message_id" not in result and "bill_id" not in result:
                    result["message_id"] = chat_ids[0]

            return result

    def get_clock(self) -> str:
        with self._lock:
            return self._clock_str

    def advance_clock(self, to: str) -> str:
        target_dt = _parse_rfc3339(to, "to")
        with self._lock:
            if target_dt < self._clock_dt:
                raise ProblemError(
                    status=400,
                    code="VALIDATION_FAILED",
                    title="Cannot move clock backward",
                    detail=f"Target '{to}' is earlier than current clock '{self._clock_str}'. Use /sim/scenario:reset to rewind.",
                    errors=[{"field": "to", "code": "clock_backward"}],
                )
            self._clock_dt = target_dt
            self._clock_str = to
            return self._clock_str
