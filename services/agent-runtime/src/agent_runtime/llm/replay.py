"""Replay LLM adapter with deterministic input-hash cassettes (record & replay modes)."""

from __future__ import annotations

import hashlib
import json
import pathlib
from collections.abc import Sequence
from typing import Any, Literal

from agent_runtime.domain.models import LLMMessage, LLMResponse, LLMToolSchema

from .port import LLM, CassetteMissError, LLMError


def canonical_llm_input(
    messages: Sequence[LLMMessage],
    tools: Sequence[LLMToolSchema] | None = None,
    schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a provider-neutral canonical JSON dict representing an LLM.complete() input."""
    return {
        "messages": [m.model_dump(mode="json") for m in messages],
        "tools": [t.model_dump(mode="json") for t in tools] if tools is not None else None,
        "schema": schema,
    }


def compute_cassette_key(
    messages: Sequence[LLMMessage],
    tools: Sequence[LLMToolSchema] | None = None,
    schema: dict[str, Any] | None = None,
) -> str:
    """Compute SHA-256 hex digest of canonical LLM input."""
    payload = canonical_llm_input(messages, tools, schema)
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


class ReplayLLM:
    """Cassette-backed LLM adapter supporting 'replay' and 'record' modes.

    Cassette JSON format:
    {
      "version": 1,
      "entries": {
        "<sha256_hex>": {
          "response": { ... LLMResponse JSON ... },
          "note": "optional human note"
        }
      }
    }
    """

    def __init__(
        self,
        *,
        mode: Literal["replay", "record"] = "replay",
        cassette_path: pathlib.Path | str | None = None,
        entries: dict[str, dict[str, Any]] | None = None,
        upstream: LLM | None = None,
    ) -> None:
        if mode == "record" and upstream is None:
            raise ValueError("ReplayLLM in 'record' mode requires an upstream LLM")
        self.mode = mode
        self.cassette_path = pathlib.Path(cassette_path) if cassette_path is not None else None
        self._upstream = upstream
        self._entries: dict[str, dict[str, Any]] = {}
        if self.cassette_path is not None and self.cassette_path.exists():
            self._load_file(self.cassette_path)
        if entries:
            self._entries.update(entries)
        self.played_keys: list[str] = []

    @classmethod
    def from_file(cls, cassette_path: pathlib.Path | str) -> ReplayLLM:
        """Load a cassette file in strict replay mode."""
        path = pathlib.Path(cassette_path)
        if not path.exists():
            raise FileNotFoundError(f"Cassette file not found: {path}")
        return cls(mode="replay", cassette_path=path)

    @classmethod
    def record_to_file(cls, cassette_path: pathlib.Path | str, upstream: LLM) -> ReplayLLM:
        """Create a ReplayLLM in record mode writing to cassette_path."""
        return cls(mode="record", cassette_path=cassette_path, upstream=upstream)

    def _load_file(self, path: pathlib.Path) -> None:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or "entries" not in raw or not isinstance(raw["entries"], dict):
            raise LLMError(f"Invalid cassette format in {path}")
        self._entries = dict(raw["entries"])

    def save(self, path: pathlib.Path | str | None = None) -> pathlib.Path:
        """Persist cassette entries to disk in deterministic sorted JSON."""
        target = pathlib.Path(path) if path is not None else self.cassette_path
        if target is None:
            raise ValueError("No cassette_path configured for ReplayLLM.save()")
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "entries": dict(sorted(self._entries.items()))}
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        tmp.replace(target)
        return target

    @property
    def entries(self) -> dict[str, dict[str, Any]]:
        return dict(self._entries)

    async def complete(
        self,
        messages: Sequence[LLMMessage],
        tools: Sequence[LLMToolSchema] | None = None,
        schema: dict[str, Any] | None = None,
    ) -> LLMResponse:
        key = compute_cassette_key(messages, tools, schema)

        if self.mode == "replay":
            entry = self._entries.get(key)
            if entry is None:
                last_role = messages[-1].role if messages else "none"
                last_preview = (messages[-1].content[:120] if messages else "")
                raise CassetteMissError(
                    key,
                    f"messages={len(messages)} last={last_role}:{last_preview!r}",
                )
            self.played_keys.append(key)
            return LLMResponse.model_validate(entry["response"])

        assert self._upstream is not None
        response = await self._upstream.complete(messages, tools=tools, schema=schema)
        self._entries[key] = {
            "response": response.model_dump(mode="json"),
        }
        self.played_keys.append(key)
        if self.cassette_path is not None:
            self.save()
        return response
