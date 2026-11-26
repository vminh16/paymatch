"""Ed25519 JWT signing/verification for capability tokens, merchant sessions, and sim-world JWKS."""

from __future__ import annotations

import base64
import hashlib
import time
from typing import Any, Protocol

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from core.shared.errors import ProblemError
from core.shared.ids import new_id


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


class Ed25519KeyManager:
    """Signs and verifies EdDSA JWTs (capability tokens and merchant session JWTs)."""

    def __init__(self, pem: str | None = None) -> None:
        if pem:
            key = serialization.load_pem_private_key(pem.encode("utf-8"), password=None)
            if not isinstance(key, Ed25519PrivateKey):
                raise ValueError("Signing key PEM must be Ed25519")
            self._private_key = key
        else:
            self._private_key = Ed25519PrivateKey.generate()
        self._public_key = self._private_key.public_key()
        raw_pub = self._public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        self.kid = hashlib.sha256(raw_pub).hexdigest()[:16]

    def sign(self, claims: dict[str, Any]) -> str:
        return jwt.encode(claims, self._private_key, algorithm="EdDSA", headers={"kid": self.kid})

    def verify(
        self,
        token: str,
        *,
        audience: str,
        issuer: str | None = None,
        now_ts: int | None = None,
    ) -> dict[str, Any]:
        try:
            kwargs: dict[str, Any] = {
                "algorithms": ["EdDSA"],
                "audience": audience,
                "options": {"verify_exp": False},
            }
            if issuer is not None:
                kwargs["issuer"] = issuer
            claims = jwt.decode(token, self._public_key, **kwargs)
        except jwt.PyJWTError as exc:
            raise ProblemError(
                status=401,
                code="UNAUTHENTICATED",
                title="Invalid token",
                detail=f"Token không hợp lệ: {exc}",
            ) from exc
        exp = claims.get("exp")
        check_now = int(time.time()) if now_ts is None else now_ts
        if exp is not None and int(exp) < check_now:
            raise ProblemError(
                status=401,
                code="TOKEN_EXPIRED",
                title="Token expired",
                detail="Token đã hết hạn.",
            )
        return claims

    def issue_capability_token(
        self,
        *,
        sub: str,
        tenant_id: str,
        job_id: str,
        invoice_id: str | None,
        attempt: int,
        worker_id: str,
        bot_version: int | None,
        tools: list[str],
        store_ids: list[str] | None = None,
        ttl_seconds: int = 120,
        now_ts: int | None = None,
    ) -> tuple[str, int]:
        """Issue EdDSA capability JWT matching contracts/schemas/capability-token-claims.schema.json."""
        if ttl_seconds > 120:
            ttl_seconds = 120
        now_i = int(time.time()) if now_ts is None else now_ts
        exp = now_i + ttl_seconds
        claims: dict[str, Any] = {
            "iss": "core",
            "aud": "internal-api",
            "sub": sub,
            "tenant_id": tenant_id,
            "job_id": job_id,
            "invoice_id": invoice_id,
            "attempt": attempt,
            "worker_id": worker_id,
            "bot_version": bot_version,
            "tools": list(tools),
            "exp": exp,
            "jti": new_id("jti"),
        }
        if store_ids is not None:
            claims["store_ids"] = list(store_ids)
        return self.sign(claims), exp


class JwksVerifier(Protocol):
    def verify_momo_token(self, token: str) -> dict[str, Any]: ...

    def verify_auth_proof(self, token: str) -> dict[str, Any]: ...


class StaticJwksVerifier:
    """In-memory verifier backed by a static JWKS dict (ideal for unit/integration tests)."""

    def __init__(self, jwks: dict[str, Any]) -> None:
        self._keys = _parse_ed25519_jwks(jwks)

    def update_jwks(self, jwks: dict[str, Any]) -> None:
        self._keys = _parse_ed25519_jwks(jwks)

    def _verify(self, token: str, *, expected_use: str, err_code_on_fail: str, err_status: int) -> dict[str, Any]:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise ProblemError(err_status, err_code_on_fail, "Invalid JWT", f"Invalid JWT header: {exc}") from exc
        kid = header.get("kid")
        pub = self._keys.get(kid) if kid else (next(iter(self._keys.values())) if self._keys else None)
        if pub is None:
            raise ProblemError(err_status, err_code_on_fail, "Unknown signing key", "Signing key not found in JWKS.")
        try:
            claims = jwt.decode(token, pub, algorithms=["EdDSA"], audience="paymatch")
        except jwt.ExpiredSignatureError as exc:
            code = "TOKEN_EXPIRED" if expected_use == "momo_token" else "STEP_UP_INVALID"
            raise ProblemError(err_status, code, "Token expired", "Token đã hết hạn.") from exc
        except jwt.PyJWTError as exc:
            raise ProblemError(err_status, err_code_on_fail, "Invalid JWT", f"Chữ ký JWT không hợp lệ: {exc}") from exc
        if claims.get("token_use") != expected_use:
            raise ProblemError(
                err_status,
                err_code_on_fail,
                "Invalid token type",
                f"Yêu cầu token_use={expected_use}.",
            )
        return claims

    def verify_momo_token(self, token: str) -> dict[str, Any]:
        return self._verify(token, expected_use="momo_token", err_code_on_fail="UNAUTHENTICATED", err_status=401)

    def verify_auth_proof(self, token: str) -> dict[str, Any]:
        return self._verify(token, expected_use="auth_proof", err_code_on_fail="STEP_UP_INVALID", err_status=403)


class HttpJwksVerifier:
    """Fetches and caches Ed25519 JWKS from {SIM_URL}/identity/.well-known/jwks.json."""

    def __init__(self, sim_url: str, service_key: str = "") -> None:
        self._sim_url = sim_url.rstrip("/")
        self._service_key = service_key
        self._keys: dict[str, Ed25519PublicKey] = {}

    def _refresh(self) -> None:
        headers = {"X-Service-Key": self._service_key} if self._service_key else {}
        try:
            resp = httpx.get(
                f"{self._sim_url}/identity/.well-known/jwks.json",
                headers=headers,
                timeout=3.0,
            )
            resp.raise_for_status()
            self._keys = _parse_ed25519_jwks(resp.json())
        except Exception as exc:
            raise ProblemError(
                status=503,
                code="UPSTREAM_UNAVAILABLE",
                title="Identity provider unavailable",
                detail=f"Không thể tải JWKS từ bên định danh: {exc}",
            ) from exc

    def _get_key(self, kid: str | None) -> Ed25519PublicKey:
        if not self._keys or (kid and kid not in self._keys):
            self._refresh()
        pub = self._keys.get(kid) if kid else (next(iter(self._keys.values())) if self._keys else None)
        if pub is None:
            raise ProblemError(401, "UNAUTHENTICATED", "Unknown key", "Không tìm thấy khóa JWKS phù hợp.")
        return pub

    def _verify(self, token: str, *, expected_use: str, err_code_on_fail: str, err_status: int) -> dict[str, Any]:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise ProblemError(err_status, err_code_on_fail, "Invalid JWT", f"Invalid JWT header: {exc}") from exc
        pub = self._get_key(header.get("kid"))
        try:
            claims = jwt.decode(token, pub, algorithms=["EdDSA"], audience="paymatch")
        except jwt.ExpiredSignatureError as exc:
            code = "TOKEN_EXPIRED" if expected_use == "momo_token" else "STEP_UP_INVALID"
            raise ProblemError(err_status, code, "Token expired", "Token đã hết hạn.") from exc
        except jwt.PyJWTError as exc:
            raise ProblemError(err_status, err_code_on_fail, "Invalid JWT", f"Chữ ký JWT không hợp lệ: {exc}") from exc
        if claims.get("token_use") != expected_use:
            raise ProblemError(
                err_status,
                err_code_on_fail,
                "Invalid token type",
                f"Yêu cầu token_use={expected_use}.",
            )
        return claims

    def verify_momo_token(self, token: str) -> dict[str, Any]:
        return self._verify(token, expected_use="momo_token", err_code_on_fail="UNAUTHENTICATED", err_status=401)

    def verify_auth_proof(self, token: str) -> dict[str, Any]:
        return self._verify(token, expected_use="auth_proof", err_code_on_fail="STEP_UP_INVALID", err_status=403)


def _parse_ed25519_jwks(jwks: dict[str, Any]) -> dict[str, Ed25519PublicKey]:
    result: dict[str, Ed25519PublicKey] = {}
    for item in jwks.get("keys", []):
        if item.get("kty") == "OKP" and item.get("crv") == "Ed25519" and item.get("x"):
            raw = _b64url_decode(item["x"])
            result[item.get("kid", "default")] = Ed25519PublicKey.from_public_bytes(raw)
    return result
