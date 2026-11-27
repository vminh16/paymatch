"""Plugin and prompt loader for built-in system bots and safety prompts."""

from __future__ import annotations

import pathlib
from dataclasses import dataclass

import yaml
from paymatch_contracts.internal import BotManifest, BotSkillContent

from agent_runtime.domain.safety import strip_yaml_frontmatter


@dataclass(frozen=True)
class LoadedSkill:
    """Parsed skill.md with frontmatter metadata."""

    skill_id: str
    version: int
    prefetch: tuple[str, ...]
    content_md: str


@dataclass(frozen=True)
class LoadedBotPlugin:
    """Validated system bot plugin loaded from plugins/bots/<id>/."""

    manifest: BotManifest
    skill: LoadedSkill


@dataclass(frozen=True)
class RuntimePrompts:
    """System-level prompts loaded from services/agent-runtime/prompts/."""

    safety_frame: str
    chief_accountant: str


def default_prompts_dir() -> pathlib.Path:
    """Locate services/agent-runtime/prompts/ relative to this package."""
    # services/agent-runtime/src/agent_runtime/plugins/loader.py -> parents[3] = services/agent-runtime
    return pathlib.Path(__file__).resolve().parents[3] / "prompts"


def default_plugins_dir() -> pathlib.Path:
    """Locate repo-root plugins/bots/ relative to this package."""
    # services/agent-runtime -> parents[2] = repo root
    return pathlib.Path(__file__).resolve().parents[5] / "plugins" / "bots"


def parse_skill_markdown(content_md: str, fallback_skill_id: str = "default") -> LoadedSkill:
    """Parse optional YAML frontmatter (`skill_id`, `version`, `prefetch`) from skill.md."""
    skill_id = fallback_skill_id
    version = 1
    prefetch: list[str] = []

    if content_md.startswith("---"):
        lines = content_md.splitlines()
        if lines and lines[0].strip() == "---":
            end_idx = None
            for idx in range(1, len(lines)):
                if lines[idx].strip() == "---":
                    end_idx = idx
                    break
            if end_idx is not None:
                frontmatter_raw = "\n".join(lines[1:end_idx])
                parsed = yaml.safe_load(frontmatter_raw) or {}
                if isinstance(parsed, dict):
                    if isinstance(parsed.get("skill_id"), str) and parsed["skill_id"]:
                        skill_id = parsed["skill_id"]
                    if isinstance(parsed.get("version"), int) and parsed["version"] >= 1:
                        version = parsed["version"]
                    raw_prefetch = parsed.get("prefetch", [])
                    if isinstance(raw_prefetch, list):
                        prefetch = [str(item) for item in raw_prefetch if isinstance(item, str)]

    return LoadedSkill(
        skill_id=skill_id,
        version=version,
        prefetch=tuple(prefetch),
        content_md=content_md,
    )


def extract_prefetch_from_skills(skills: list[BotSkillContent]) -> list[str]:
    """Extract ordered unique prefetch tool IDs declared in skill markdown frontmatter."""
    seen: set[str] = set()
    ordered: list[str] = []
    for sk in skills:
        parsed = parse_skill_markdown(sk.content_md, fallback_skill_id=sk.skill_id)
        for tool_id in parsed.prefetch:
            if tool_id not in seen:
                seen.add(tool_id)
                ordered.append(tool_id)
    return ordered


def load_bot_plugin(bot_dir: pathlib.Path) -> LoadedBotPlugin:
    """Load and validate one bot plugin directory containing manifest.yaml and skill.md."""
    manifest_path = bot_dir / "manifest.yaml"
    skill_path = bot_dir / "skill.md"
    raw_manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest = BotManifest.model_validate(raw_manifest)
    raw_skill = skill_path.read_text(encoding="utf-8")
    fallback_id = manifest.skills[0].split("@", 1)[0]
    skill = parse_skill_markdown(raw_skill, fallback_skill_id=fallback_id)
    # Sanity check: skill markdown body must remain non-empty after stripping frontmatter
    if not strip_yaml_frontmatter(raw_skill).strip():
        raise ValueError(f"Empty skill body in {skill_path}")
    return LoadedBotPlugin(manifest=manifest, skill=skill)


def load_all_system_bot_plugins(
    plugins_dir: pathlib.Path | None = None,
) -> dict[str, LoadedBotPlugin]:
    """Load all system bot plugins (directories containing manifest.yaml + skill.md)."""
    root = plugins_dir or default_plugins_dir()
    loaded: dict[str, LoadedBotPlugin] = {}
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        if not (child / "manifest.yaml").exists():
            continue
        plugin = load_bot_plugin(child)
        loaded[plugin.manifest.id] = plugin
    return loaded


def load_runtime_prompts(prompts_dir: pathlib.Path | None = None) -> RuntimePrompts:
    """Load safety_frame.md and chief_accountant.md from prompts/."""
    root = prompts_dir or default_prompts_dir()
    return RuntimePrompts(
        safety_frame=(root / "safety_frame.md").read_text(encoding="utf-8"),
        chief_accountant=(root / "chief_accountant.md").read_text(encoding="utf-8"),
    )
