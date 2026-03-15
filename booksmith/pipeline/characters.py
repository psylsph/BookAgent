import json
import re
from pathlib import Path
from typing import Generator, Optional

from ..api_client import APIClient, format_prompt
from ..storage.project import Project
from ..ui import console


def parse_character_list(text: str) -> list[dict]:
    """Parse character list from AI response."""
    characters = []

    json_match = re.search(r"```json\n([\s\S]*?)\n```", text)
    if json_match:
        try:
            characters = json.loads(json_match.group(1))
            characters = _normalize_character_keys(characters)
            return characters
        except json.JSONDecodeError:
            pass

    json_match = re.search(r"\[[\s\S]*\]", text)
    if json_match:
        try:
            characters = json.loads(json_match.group())
            characters = _normalize_character_keys(characters)
            return characters
        except json.JSONDecodeError:
            pass

    lines = text.split("\n")
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        parts = re.split(r"[-:–—]", line, maxsplit=1)
        if len(parts) == 2:
            name = parts[0].strip()
            desc = parts[1].strip()
            if name and desc:
                characters.append(
                    {
                        "name": name,
                        "role": "Character",
                        "description": desc,
                    }
                )

    return characters


def _normalize_character_keys(characters: list[dict]) -> list[dict]:
    """Normalize character keys to lowercase."""
    normalized = []
    for char in characters:
        new_char = {}
        for key, value in char.items():
            key_lower = key.lower()
            if key_lower == "name":
                new_char["name"] = value
            elif key_lower == "role":
                new_char["role"] = value
            elif key_lower == "description":
                new_char["description"] = value
            else:
                new_char[key_lower] = value
        normalized.append(new_char)
    return normalized


def generate_character_list(
    project: Project,
    client: APIClient,
) -> list[dict]:
    """Generate initial character list."""
    console.print_header("Generating Character List...")

    story_bible = project.read_file("story_bible.md")
    world = project.read_file("world.md")
    seed_content = project.read_file(project.seed_file)

    system_prompt, user_prompt = format_prompt(
        "characters",
        seed_content=seed_content,
        story_bible=story_bible,
        world=world,
    )

    response = client.generate(
        stage="characters",
        system=system_prompt,
        user_message=user_prompt,
        project_config=project.config,
    )

    characters = parse_character_list(response)

    project.write_file("characters/character_list.md", response)

    return characters


def generate_character_profile(
    project: Project,
    client: APIClient,
    character_info: dict,
    all_characters: list[dict],
) -> str:
    """Generate full profile for a single character."""
    console.print_header(f"Generating profile for {character_info['name']}...")

    story_bible = project.read_file("story_bible.md")
    world = project.read_file("world.md")

    character_list_text = "\n".join(
        [
            f"- {c['name']}: {c.get('description', c.get('role', ''))}"
            for c in all_characters
        ]
    )

    prompt = f"""## Story Bible

{story_bible}

## World Guide

{world}

## All Characters

{character_list_text}

## This Character

Name: {character_info["name"]}
Role: {character_info.get("role", "Character")}
Description: {character_info.get("description", "")}

---

Please create a detailed profile for {character_info["name"]} including:
- Full name, age, physical description
- Backstory
- Personality and voice notes
- Motivation and goal
- Internal conflict
- Arc summary
- Relationships to other characters
- Key possessions or symbols
"""

    profile = client.stream(
        stage="characters",
        system="You are a character development expert.",
        user_message=prompt,
        project_config=project.config,
    )

    content = ""
    for chunk in profile:
        content += chunk

    filename = f"characters/{character_info['name'].replace(' ', '_')}.md"
    project.write_file(filename, content)

    return content


def generate_all_characters(
    project: Project,
    client: APIClient,
    characters: Optional[list[dict]] = None,
) -> list[dict]:
    """Generate all character profiles."""
    if characters is None:
        characters = generate_character_list(project, client)

    character_index = []

    for char_info in characters:
        generate_character_profile(project, client, char_info, characters)

        char_summary = {
            "name": char_info["name"],
            "role": char_info.get("role", "Character"),
            "description": char_info.get("description", ""),
        }
        character_index.append(char_summary)

    project.save_character_index(character_index)

    return character_index


def regenerate_character(
    project: Project,
    client: APIClient,
    character_name: str,
) -> str:
    """Regenerate a specific character's profile."""
    characters = project.get_characters()

    for char_info in characters:
        if char_info["name"].lower() == character_name.lower():
            return generate_character_profile(project, client, char_info, characters)

    raise ValueError(f"Character not found: {character_name}")
