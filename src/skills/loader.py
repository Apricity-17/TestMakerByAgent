"""Skill loader: reads Markdown skill files, matches by keywords, injects into prompts."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Skill:
    name: str
    description: str
    triggers: list[str] = field(default_factory=list)
    content: str = ""


def _parse_skill_md(filepath: str) -> Optional[Skill]:
    """Parse a skill Markdown file with YAML front matter."""
    with open(filepath, encoding="utf-8") as f:
        text = f.read()

    if not text.startswith("---"):
        return None

    parts = text.split("---", 2)
    if len(parts) < 3:
        return None

    front_matter = parts[1]
    body = parts[2].strip()

    meta: dict[str, object] = {}
    current_key = ""
    for line in front_matter.strip().split("\n"):
        line = line.strip()
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()
            if val:
                meta[key] = val
                current_key = key
            elif key not in meta:
                meta[key] = []
                current_key = key
        elif line.startswith("- ") and current_key:
            item = line[2:].strip().strip('"').strip("'")
            val = meta.get(current_key, [])
            if isinstance(val, list):
                val.append(item)

    return Skill(
        name=str(meta.get("name", Path(filepath).stem)),
        description=str(meta.get("description", "")),
        triggers=[str(t) for t in meta.get("triggers", [])],
        content=body,
    )


def load_all_skills(skills_dir: str) -> list[Skill]:
    """Load all .md Skill files from a directory."""
    skills: list[Skill] = []
    if not os.path.isdir(skills_dir):
        return skills

    for filename in sorted(os.listdir(skills_dir)):
        if filename.endswith(".md"):
            skill = _parse_skill_md(os.path.join(skills_dir, filename))
            if skill:
                skills.append(skill)
    return skills


def match_skills(skills: list[Skill], context: str) -> list[Skill]:
    """Match skills whose triggers appear in the context string."""
    ctx_lower = context.lower()
    matched: list[Skill] = []
    for skill in skills:
        if not skill.triggers:
            continue
        for trigger in skill.triggers:
            if trigger.lower() in ctx_lower:
                matched.append(skill)
                break
    return matched


def inject_skills_into_prompt(skills: list[Skill], base_prompt: str) -> str:
    """Prepend matched skill content to the prompt as knowledge context."""
    if not skills:
        return base_prompt

    knowledge_blocks = []
    for s in skills:
        knowledge_blocks.append(f"## Skill: {s.name}\n{s.content}")

    knowledge_section = "\n\n---\n\n".join(knowledge_blocks)
    return (
        f"# Expert Knowledge (loaded skills)\n\n{knowledge_section}\n\n"
        f"---\n\n"
        f"# Task\n\n{base_prompt}"
    )


def get_default_skills_dir() -> str:
    return str(Path(__file__).parent / "data")
