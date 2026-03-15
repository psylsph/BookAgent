import re
from pathlib import Path
from typing import Generator, List, Optional, Tuple

from ..api_client import APIClient, format_prompt
from ..storage.project import Project
from ..ui import console


def parse_chapter_list(text: str) -> List[dict]:
    """Parse chapter list from AI response."""
    chapters = []

    lines = text.split("\n")
    current_chapter = {}

    for line in lines:
        line = line.strip()

        if not line:
            continue

        num_match = re.match(r"^(\d+)[\.\):]\s*(.+)$", line)
        if num_match:
            if current_chapter:
                chapters.append(current_chapter)
            current_chapter = {
                "number": int(num_match.group(1)),
                "title": num_match.group(2).strip(),
                "purpose": "",
            }
        elif current_chapter and line.startswith("-"):
            current_chapter["purpose"] = line.lstrip("- ").strip()

    if current_chapter:
        chapters.append(current_chapter)

    return chapters


def generate_chapter_list(
    project: Project,
    client: APIClient,
) -> List[dict]:
    """Generate initial chapter list."""
    console.print_header("Generating Chapter List...")

    story_bible = project.read_file("story_bible.md")
    world = project.read_file("world.md")

    characters = project.get_characters()

    # Build detailed character text from full profiles
    character_parts = []
    for c in characters:
        char_file = f"characters/{c['name'].replace(' ', '_')}.md"
        try:
            profile = project.read_file(char_file)
            # Use first 800 chars of profile for context
            character_parts.append(
                f"## {c['name']} ({c.get('role', 'Character')})\n{profile[:800]}"
            )
        except FileNotFoundError:
            character_parts.append(
                f"- {c['name']}: {c.get('description', c.get('role', ''))}"
            )

    character_text = "\n\n".join(character_parts)

    total_chapters = project.total_chapters or 24

    system_prompt, user_prompt = format_prompt(
        "chapter_outline",
        story_bible=story_bible,
        world=world,
        characters=character_text,
        total_chapters=str(total_chapters),
    )

    response = client.generate(
        stage="chapter_outliner",
        system=system_prompt,
        user_message=user_prompt,
        project_config=project.config,
    )

    chapters = parse_chapter_list(response)

    return chapters


def generate_chapter_outline(
    project: Project,
    client: APIClient,
    chapter_info: dict,
    all_chapters: List[dict],
) -> str:
    """Generate detailed outline for a single chapter."""
    console.print_header(f"Generating outline for Chapter {chapter_info['number']}...")

    story_bible = project.read_file("story_bible.md")
    world = project.read_file("world.md")

    story_bible_summary = story_bible[:1000] if len(story_bible) > 1000 else story_bible

    # Include full character profiles
    characters = project.get_characters()
    char_parts = []
    for c in characters:
        char_file = f"characters/{c['name'].replace(' ', '_')}.md"
        try:
            profile = project.read_file(char_file)
            char_parts.append(
                f"## {c['name']} ({c.get('role', 'Character')})\n{profile[:600]}"
            )
        except FileNotFoundError:
            char_parts.append(
                f"- {c['name']}: {c.get('description', c.get('role', ''))}"
            )
    characters_text = "\n\n".join(char_parts)

    chapter_list_text = "\n".join(
        [f"{c['number']}. {c['title']} - {c.get('purpose', '')}" for c in all_chapters]
    )

    prev_chapter = None
    next_chapter = None
    for i, c in enumerate(all_chapters):
        if c["number"] == chapter_info["number"]:
            if i > 0:
                prev_chapter = all_chapters[i - 1]
            if i < len(all_chapters) - 1:
                next_chapter = all_chapters[i + 1]
            break

    connection_text = ""
    if prev_chapter:
        connection_text += f"\n\n**Previous chapter ({prev_chapter['number']}):** {prev_chapter['title']}"
    if next_chapter:
        connection_text += (
            f"\n\n**Next chapter ({next_chapter['number']}):** {next_chapter['title']}"
        )

    prompt = f"""## Story Bible (summary)

{story_bible_summary}

## Characters

{characters_text}

## Chapter List

{chapter_list_text}

## Chapter to Outline

**Chapter {chapter_info["number"]}: {chapter_info["title"]}**
Purpose: {chapter_info.get("purpose", "")}
{connection_text}

---

Please create a detailed outline for this chapter including:
- Chapter title
- POV character
- Setting (which location)
- Characters present
- Scene-by-scene beat breakdown
- Chapter goal (what must be achieved narratively)
- Emotional tone
- How it connects to previous and next chapter
- Foreshadowing or callbacks
- Target word count (around 2000-3000 words)
"""

    outline = client.stream(
        stage="chapter_outliner",
        system="You are a plot architect.",
        user_message=prompt,
        project_config=project.config,
    )

    content = ""
    for chunk in outline:
        content += chunk

    filename = f"chapter_outlines/chapter_{chapter_info['number']}.md"
    project.write_file(filename, content)

    return content


def generate_all_chapter_outlines(
    project: Project,
    client: APIClient,
    chapters: Optional[List[dict]] = None,
) -> List[dict]:
    """Generate all chapter outlines."""
    if chapters is None:
        chapters = generate_chapter_list(project, client)

    for chapter_info in chapters:
        generate_chapter_outline(project, client, chapter_info, chapters)

    return chapters


def regenerate_chapter_outline(
    project: Project,
    client: APIClient,
    chapter_num: int,
) -> str:
    """Regenerate a specific chapter outline."""
    all_outlines_dir = project.path / "chapter_outlines"
    chapters = []

    for f in sorted(all_outlines_dir.glob("chapter_*.md")):
        num = int(f.stem.split("_")[1])
        content = f.read_text()
        title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        title = title_match.group(1) if title_match else f"Chapter {num}"
        chapters.append({"number": num, "title": title, "purpose": ""})

    chapters.sort(key=lambda x: x["number"])

    for chapter_info in chapters:
        if chapter_info["number"] == chapter_num:
            return generate_chapter_outline(project, client, chapter_info, chapters)

    raise ValueError(f"Chapter not found: {chapter_num}")
