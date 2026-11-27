"""LLM port and Fake / Replay adapters (no real provider adapter yet)."""

from .fake import FakeLLM, RecordedLLMCall, infer_agent_id
from .langchain_adapter import PortChatModel
from .port import LLM, CassetteMissError, LLMError, LLMMode
from .replay import ReplayLLM, canonical_llm_input, compute_cassette_key

__all__ = [
    "LLM",
    "CassetteMissError",
    "FakeLLM",
    "LLMError",
    "LLMMode",
    "PortChatModel",
    "RecordedLLMCall",
    "ReplayLLM",
    "canonical_llm_input",
    "compute_cassette_key",
    "infer_agent_id",
]
