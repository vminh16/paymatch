"""In-memory Ed25519 key pair for signing and verifying demo JWTs + JWKS."""

from __future__ import annotations

import base64
import hashlib
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from sim_world.errors import ProblemError


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


class IdentityKeyStore:
    """Holds an ephemeral Ed25519 signing key generated at service startup."""

    def __init__(self) -> None:
        self._private_key = Ed25519PrivateKey.generate()
        self._public_key = self._private_key.public_key()
        self._raw_public = self._public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        digest = hashlib.sha256(self._raw_public).hexdigest()[:12]
        self.kid = f"sim-ed25519-{digest}"

    def jwks(self) -> dict[str, Any]:
        return {
            "keys": [
                {
                    "kty": "OKP",
                    "crv": "Ed25519",
                    "alg": "EdDSA",
                    "use": "sig",
                    "kid": self.kid,
                    "x": _b64url(self._raw_public),
                }
            ]
        }

    def sign(self, claims: dict[str, Any]) -> str:
        return jwt.encode(
            claims,
            self._private_key,
            algorithm="EdDSA",
            headers={"kid": self.kid},
        )

    def verify(self, token: str, audience: str | None = None) -> dict[str, Any]:
        try:
            options = {"verify_aud": audience is not None}
            return jwt.decode(
                token,
                self._public_key,
                algorithms=["EdDSA"],
                audience=audience,
                options=options,
            )
        except jwt.ExpiredSignatureError as exc:
            raise ProblemError(
                status=401,
                code="TOKEN_EXPIRED",
                title="Token expired",
                detail="The provided JWT has expired.",
            ) from exc
        except jwt.InvalidTokenError as exc:
            raise ProblemError(
                status=401,
                code="UNAUTHENTICATED",
                title="Invalid token",
                detail=f"Token verification failed: {exc}",
            ) from exc
