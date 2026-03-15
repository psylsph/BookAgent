import re
from pathlib import Path
from typing import Generator, List, Optional, Tuple

from ..api_client import APIClient, format_prompt
from ..storage.project import Project
from ..ui import console


def extract_act_structure(story_bible: str) -> List[dict]:
    """Extract act structure from story bible.

    Returns list of acts with their descriptions and chapter ranges.
    """
    acts = []

    # Pattern to match act definitions
    act_patterns = [
        r"(?:Act\s*(\d+)|Act\s*([IVX]+))[:\s]+(.+?)(?=(?:Act\s*\d+|Act\s*[IVX]+)|$)",
        r"(?:Part\s*(\d+)|Part\s*([IVX]+))[:\s]+(.+?)(?=(?:Part\s*\d+|Part\s*[IVX]+)|$)",
    ]

    for pattern in act_patterns:
        matches = list(re.finditer(pattern, story_bible, re.IGNORECASE | re.DOTALL))
        if matches:
            for match in matches:
                act_num = match.group(1) or match.group(2)
                description = match.group(3).strip()[:200]  # Limit length
                acts.append(
                    {
                        "number": int(act_num) if act_num.isdigit() else act_num,
                        "description": description,
                    }
                )
            break

    # If no explicit acts found, try to infer from chapter count
    if not acts:
        # Default to 3 acts if no structure found
        acts = [
            {
                "number": 1,
                "description": "Setup - Introduce characters, world, and inciting incident",
            },
            {"number": 2, "description": "Confrontation - Rising action and obstacles"},
            {"number": 3, "description": "Resolution - Climax and conclusion"},
        ]

    return acts


def parse_chapter_list(text: str) -> List[dict]:
    """Parse chapter list from AI response."""
    chapters = []

    lines = text.split("\n")
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("|"):
            # Skip empty lines, headers, and table dividers
            if "---" in line or "===" in line:
                continue
            if line.startswith("|"):
                # Check if it's a table row with a number
                if not re.match(r"\|\s*\d+\s*\|", line):
                    continue

        # Match table row format: | 1 | Ambush | Purpose |
        table_match = re.match(r"\|\s*(\d+)\s*\|\s*([^|]+)\|\s*([^|]+)\|", line)
        if table_match:
            chapters.append(
                {
                    "number": int(table_match.group(1)),
                    "title": table_match.group(2).strip(),
                    "purpose": table_match.group(3).strip(),
                }
            )
            continue

        # Match numbered list format: 1. Title - Purpose
        num_match = re.match(r"^(\d+)[\.\):]\s*(.+?)(?:\s*[-–—]\s*(.+))?$", line)
        if num_match:
            chapters.append(
                {
                    "number": int(num_match.group(1)),
                    "title": num_match.group(2).strip(),
                    "purpose": num_match.group(3).strip() if num_match.group(3) else "",
                }
            )
            continue

    return chapters


def generate_chapter_list(
    project: Project,
    client: APIClient,
) -> List[dict]:
    """Generate chapter list."""
    console.print_header("Generating Chapter List...")

    story_bible = project.read_file("story_bible.md")
    world = project.read_file("world.md")
    seed_content = project.read_file(project.seed_file)

    characters = project.get_characters()

    # Build detailed character text from full profiles
    character_parts = []
    for c in characters:
        char_file = f"characters/{c['name'].replace(' ', '_')}.md"
        try:
            profile = project.read_file(char_file)
            character_parts.append(
                f"## {c['name']} ({c.get('role', 'Character')})\n{profile[:800]}"
            )
        except FileNotFoundError:
            character_parts.append(
                f"- {c['name']}: {c.get('description', c.get('role', ''))}"
            )

    character_text = "\n\n".join(character_parts)

    total_chapters = project.total_chapters or 24

    # Extract act structure for context
    acts = extract_act_structure(story_bible)
    acts_text = "\n".join([f"Act {a['number']}: {a['description']}" for a in acts])

    system_prompt, user_prompt = format_prompt(
        "chapter_outline",
        seed_content=seed_content,
        story_bible=story_bible,
        world=world,
        characters=character_text,
        total_chapters=str(total_chapters),
        acts_text=acts_text,
        act_context="",
    )

    response = client.generate(
        stage="chapter_outliner",
        system=system_prompt,
        user_message=user_prompt,
        project_config=project.config,
    )

    chapters = parse_chapter_list(response)

    # Save chapter list with header
    list_content = f"# Chapter List\n\n{response}"
    project.write_file("chapter_outlines/chapter_list.md", list_content)

    return chapters


def generate_chapter_outline(
    project: Project,
    client: APIClient,
    chapter_info: dict,
    all_chapters: List[dict],
    feedback: Optional[str] = None,
) -> str:
    """Generate detailed outline for a single chapter."""
    console.print_header(f"Generating outline for Chapter {chapter_info['number']}...")

    story_bible = project.read_file("story_bible.md")
    world = project.read_file("world.md")
    seed_content = project.read_file(project.seed_file)

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

    prev_num = prev_chapter["number"] if prev_chapter else 1
    prev_title = prev_chapter["title"] if prev_chapter else "N/A"
    next_num = next_chapter["number"] if next_chapter else "last"
    next_title = next_chapter["title"] if next_chapter else "N/A"

    feedback_text = f"**User Feedback:** {feedback}" if feedback else ""

    if prev_chapter:
        prev_ref = f"Chapter {prev_num} - {prev_title}"
    else:
        prev_ref = "the Seed Story / Prologue"

    prompt = f"""## Seed Story

{seed_content}

## Story Bible (summary)

{story_bible_summary}

## World Details

{world[:1500]}

## Characters

{characters_text}

## Chapter List (Full Story Arc)

{chapter_list_text}

---

## GENERATE CHAPTER NUMBER {chapter_info["number"]}: {chapter_info["title"]}

**This is Chapter {chapter_info["number"]} in the story sequence.** You are generating the outline for the {chapter_info["number"]}th chapter of this book.

**Title (MUST USE EXACTLY):** {chapter_info["title"]}
**Purpose (MUST FOLLOW):** {chapter_info.get("purpose", "")}

**Story Sequence Position:** This is chapter {chapter_info["number"]} out of {len(all_chapters)} chapters.
**Previous chapter:** {prev_ref}
**Next chapter:** Chapter {next_num} - {next_title}

{feedback_text}

---

## Required Outline Structure

**IMPORTANT**: Write the outline for CHAPTER {chapter_info["number"]} ({chapter_info["title"]}), not any other chapter. The content must match this position in the story.

### {chapter_info["title"]}

**POV Character:** [Name and brief characterization]
**Setting:** [Location and time of day/atmosphere]
**Characters Present:** [List who appears]

**Chapter Goal:** [What must happen narratively - the one thing this chapter must achieve]

**Emotional Arc:** [Starting mood → ending mood]

**Scene Breakdown:**
1. [Opening scene - where/who/what]
2. [Second scene - escalation]
3. [Third scene - climax/tension peak]
4. [Closing beat - transition to next chapter]

**Connections:**
- How it follows from {prev_ref}: [specific link]
- How it sets up Chapter {next_num}: [specific setup]

**Foreshadowing/Callbacks:** [What threads are planted or resolved]

**Target Word Count:** [2000-3000 words]

---

IMPORTANT: Ground everything in the Seed Story. This chapter must feel like a natural continuation of the established plot and characters.

CRITICAL: Do NOT write actual chapter prose. Only output the structured outline with scene beats. No narrative text, no dialogue, no descriptions of what characters say or do in full sentences. Just the outline structure.
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

    # If parsing failed, try to load from existing outline files
    if not chapters:
        outlines_dir = project.path / "chapter_outlines"
        if outlines_dir.exists():
            for f in sorted(outlines_dir.glob("chapter_[0-9]*.md")):
                try:
                    num = int(f.stem.split("_")[1])
                except (ValueError, IndexError):
                    continue
                content = f.read_text()
                title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
                title = title_match.group(1) if title_match else f"Chapter {num}"
                chapters.append({"number": num, "title": title, "purpose": ""})

    for chapter_info in chapters:
        generate_chapter_outline(project, client, chapter_info, chapters)

    return chapters


def regenerate_chapter_outline(
    project: Project,
    client: APIClient,
    chapter_num: int,
    feedback: Optional[str] = None,
) -> str:
    """Regenerate a specific chapter outline."""
    # Read from chapter_list.md to get correct titles and purposes
    chapter_list_path = project.path / "chapter_outlines" / "chapter_list.md"
    if chapter_list_path.exists():
        content = chapter_list_path.read_text()
        chapters = parse_chapter_list(content)
    else:
        # Fallback: read from individual files
        chapters = []
        all_outlines_dir = project.path / "chapter_outlines"
        for f in sorted(all_outlines_dir.glob("chapter_[0-9]*.md")):
            try:
                num = int(f.stem.split("_")[1])
            except (ValueError, IndexError):
                continue
            content = f.read_text()
            title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
            title = title_match.group(1) if title_match else f"Chapter {num}"
            chapters.append({"number": num, "title": title, "purpose": ""})
        chapters.sort(key=lambda x: x["number"])

    for chapter_info in chapters:
        if chapter_info["number"] == chapter_num:
            return generate_chapter_outline(
                project, client, chapter_info, chapters, feedback
            )

    raise ValueError(f"Chapter not found: {chapter_num}")
