"""In-memory capability token store updated atomically on heartbeat renewal."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from paymatch_contracts.internal import JobSessionResponse, RenewedCapabilityToken


class TokenStore:
    """Holds per-holder ('supervisor' or '<bot_id>') capability tokens for one job attempt."""

    def __init__(self, session: JobSessionResponse) -> None:
        self._tokens: dict[str, str] = {
            "supervisor": session.supervisor.capability_token,
        }
        self._expirations: dict[str, datetime] = {
            "supervisor": session.supervisor.token_exp,
        }
        for bot in session.bots:
            self._tokens[bot.bot_id] = bot.capability_token
            self._expirations[bot.bot_id] = bot.token_exp

    def get(self, holder: str) -> str:
        """Return current capability token for 'supervisor' or a specific '<bot_id>'."""
        if holder not in self._tokens:
            raise KeyError(f"No capability token held for {holder!r}")
        return self._tokens[holder]

    def expiration(self, holder: str) -> datetime | None:
        return self._expirations.get(holder)

    def update(self, renewed: Sequence[RenewedCapabilityToken]) -> None:
        """Replace tokens returned by POST /internal/jobs/{job_id}/heartbeat."""
        for item in renewed:
            self._tokens[item.holder] = item.capability_token
            self._expirations[item.holder] = item.token_exp
