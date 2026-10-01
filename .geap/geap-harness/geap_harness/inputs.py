"""Pinned review inputs: skills (content-addressed) and the versioned prompt template."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

DEFAULT_SKILLS = ("enterprise-code-review", "enterprise-secure-coding", "enterprise-unit-test")
PROMPT_VERSION = "review-v1"
MAX_DIFF_CHARS = 120_000


def package_skills_dir() -> Path:
    return Path(str(resources.files("geap_harness") / "skills"))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def skill_sha(skill_dir: Path) -> str:
    """sha256 over (relative path, bytes) of every file in the skill, sorted — rename/content sensitive."""
    h = hashlib.sha256()
    for p in sorted(x for x in skill_dir.rglob("*") if x.is_file() and "__pycache__" not in x.parts):
        rel = p.relative_to(skill_dir).as_posix()
        h.update(rel.encode())
        h.update(b"\0")
        # Normalise CRLF so a checkout on Windows yields the same SHA.
        h.update(p.read_bytes().replace(b"\r\n", b"\n"))
        h.update(b"\0")
    return h.hexdigest()


@dataclass
class Skill:
    name: str
    path: Path
    sha: str
    body: str


def load_skills(skills_dir: Path | None = None, names: tuple[str, ...] | list[str] = DEFAULT_SKILLS) -> list[Skill]:
    base = Path(skills_dir) if skills_dir else package_skills_dir()
    out: list[Skill] = []
    for name in sorted(names):
        d = base / name
        md = d / "SKILL.md"
        if not md.is_file():
            raise FileNotFoundError(f"skill '{name}' not found under {base}")
        out.append(Skill(name=name, path=d, sha=skill_sha(d), body=md.read_text(encoding="utf-8")))
    return out


def prompt_template() -> str:
    return (resources.files("geap_harness") / "prompts" / f"{PROMPT_VERSION}.md").read_text(encoding="utf-8")


def prompt_hash() -> str:
    return sha256_text(prompt_template())


def render_prompt(diff_text: str, files: list[str], skills: list[Skill]) -> str:
    diff = diff_text if len(diff_text) <= MAX_DIFF_CHARS else diff_text[:MAX_DIFF_CHARS] + "\n[... diff truncated ...]\n"
    return (
        prompt_template()
        .replace("{{SKILLS}}", ", ".join(s.name for s in skills))
        .replace("{{FILES}}", "\n".join(f"- {f}" for f in files) or "- (none)")
        .replace("{{DIFF}}", diff)
    )
