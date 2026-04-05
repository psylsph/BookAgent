import re
from pathlib import Path
from typing import Generator, List, Optional, Tuple

from ..api_client import APIClient, format_prompt
from ..storage.project import Project
from ..ui.console import console, print_header
from .reviewer import check_placeholders


def is_placeholder_value(value: str) -> bool:
    """Check if a value is a placeholder that should be ignored."""
    if not value:
        return True

    value_stripped = value.strip()

    # Check for common placeholder patterns
    placeholder_patterns = [
        r"\[Specify[^\]]*\]",
        r"\[Describe[^\]]*\]",
        r"\[Character[^\]]*\]",
        r"\[Location[^\]]*\]",
        r"\[Setting[^\]]*\]",
        r"\[Scene[^\]]*\]",
        r"\[Opening[^\]]*\]",
        r"\[Escalation[^\]]*\]",
        r"\[Climax[^\]]*\]",
        r"\[Resolution[^\]]*\]",
        r"\[Foreshadowing[^\]]*\]",
        r"\[Callback[^\]]*\]",
        r"\[element[^\]]*\]",
        r"\[List[^\]]*\]",
        r"\[TBD\]",
        r"\[TODO\]",
        r"\[.*?\]",  # Any [bracketed] text that looks like a placeholder
    ]

    import re

    value_lower = value_stripped.lower()
    for pattern in placeholder_patterns:
        if re.search(pattern, value_lower, re.IGNORECASE):
            return True

    # Also check if it's just a generic placeholder description
    generic_indicators = [
        "tbd",
        "todo",
        "specify",
        "describe",
        "character name",
        "location name",
    ]
    if any(indicator in value_lower for indicator in generic_indicators):
        return len(value_stripped) < 50  # Only short values

    return False


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

    # Sort by chapter number to ensure consistent ordering
    chapters.sort(key=lambda x: x["number"])
    return chapters


def generate_chapter_list(
    project: Project,
    client: APIClient,
) -> List[dict]:
    """Generate chapter list."""
    print_header("Generating Chapter List...")

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


def generate_chapter_list_with_feedback(
    project: Project,
    client: APIClient,
    feedback: str,
) -> List[dict]:
    """Regenerate chapter list with feedback."""
    print_header("Regenerating Chapter List with Feedback...")

    story_bible = project.read_file("story_bible.md")
    world = project.read_file("world.md")
    seed_content = project.read_file(project.seed_file)

    characters = project.get_characters()

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

    feedback_prompt = f"{user_prompt}\n\n## FEEDBACK\n\n{feedback}\n\nPlease regenerate the chapter list incorporating this feedback."

    response = client.generate(
        stage="chapter_outliner",
        system=system_prompt,
        user_message=feedback_prompt,
        project_config=project.config,
    )

    chapters = parse_chapter_list(response)

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
    print_header(f"Generating outline for Chapter {chapter_info['number']}...")

    story_bible = project.read_file("story_bible.md")
    world = project.read_file("world.md")
    seed_content = project.read_file(project.seed_file)

    # Use more context for better outline generation
    story_bible_summary = story_bible[:3000] if len(story_bible) > 3000 else story_bible

    # Include full character profiles
    characters = project.get_characters()
    char_parts = []
    for c in characters:
        char_file = f"characters/{c['name'].replace(' ', '_')}.md"
        try:
            profile = project.read_file(char_file)
            char_parts.append(
                f"## {c['name']} ({c.get('role', 'Character')})\n{profile[:1500]}"
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

    prev_num = prev_chapter["number"] if prev_chapter else 1
    prev_title = prev_chapter["title"] if prev_chapter else "N/A"
    next_num = next_chapter["number"] if next_chapter else "last"
    next_title = next_chapter["title"] if next_chapter else "N/A"

    if prev_chapter:
        prev_ref = f"Chapter {prev_num} - {prev_title}"
    else:
        prev_ref = "the Seed Story / Prologue"

    feedback_text = f"**User Feedback:** {feedback}" if feedback else ""

    # Format feedback as actionable instructions for the AI
    feedback_instructions = ""
    if feedback:
        feedback_instructions = f"""

## FEEDBACK TO INCORPORATE

The following feedback was provided on the previous outline. You MUST address each of these issues in your regenerated outline:

{feedback}

CRITICAL: Your new outline must specifically address the feedback above. Do not ignore it. Make the necessary changes to improve the outline based on this feedback.

"""

    # Load prompt template for detailed chapter outline
    system_prompt, user_prompt = format_prompt(
        "chapter_outline_detail",
        seed_content=seed_content,
        story_bible_summary=story_bible_summary,
        world_details=world[:3000],
        characters_text=characters_text,
        chapter_list_text=chapter_list_text,
        chapter_number=chapter_info["number"],
        chapter_title=chapter_info["title"],
        chapter_title_upper=chapter_info["title"].upper(),
        chapter_purpose=chapter_info.get("purpose", ""),
        total_chapters=len(all_chapters),
        previous_chapter=prev_ref,
        next_chapter=f"Chapter {next_num} - {next_title}",
        next_chapter_num=next_num,
        feedback_text=feedback_text,
        feedback_instructions=feedback_instructions,
    )

    max_attempts = 3
    content = ""

    for attempt in range(max_attempts):
        if attempt == 0:
            console.print(
                f"[cyan]Generating outline for Chapter {chapter_info['number']}...[/cyan]"
            )
        else:
            console.print(
                f"[dim]Refining outline (attempt {attempt + 1}/{max_attempts})...[/dim]"
            )

        if attempt == 0:
            # First attempt - use non-streaming to avoid showing bad output
            content = client.generate(
                stage="chapter_outliner",
                system=system_prompt,
                user_message=user_prompt,
                project_config=project.config,
            )
        else:
            # Add stronger feedback for subsequent attempts
            additional_feedback = f"""

CRITICAL: Your previous attempt contained placeholders. This is unacceptable.

REQUIREMENTS:
- EVERY field must be filled with SPECIFIC details
- Use REAL character names from the story
- Use REAL locations from the world guide
- Describe SPECIFIC plot points that happen in this chapter
- Each scene should have 3-4 sentences of actual content

DO NOT use: [Specify], [Describe], [Character], [Location], [Opening], [Escalation], [Climax], [Resolution], etc.

Provide the complete outline with actual content for every single field.
"""
            content = client.generate(
                stage="chapter_outliner",
                system=system_prompt,
                user_message=user_prompt + additional_feedback,
                project_config=project.config,
            )

        # Check for placeholders
        placeholder_count, placeholder_examples = check_placeholders(content)

        if placeholder_count == 0:
            # No placeholders, we're good
            console.print(f"[green]✓ Outline generated successfully[/green]")
            break
        elif attempt < max_attempts - 1:
            # Show what was found but continue regenerating
            console.print(
                f"[dim]  → Found {placeholder_count} placeholders, retrying...[/dim]"
            )
            continue
        else:
            console.print(
                f"[red]Warning: After {max_attempts} attempts, outline still has {placeholder_count} placeholders. "
                f"Using best attempt. You may need to manually regenerate.[/red]"
            )

    # Normalize to consistent format, but only if it won't break the content
    normalized_content = normalize_outline_format(
        content, chapter_info["number"], chapter_info["title"]
    )

    # Only use normalized version if it doesn't have placeholders (or fewer than original)
    original_placeholder_count = (
        content.count("[Specify]") + content.count("[List") + content.count("[Describe")
    )
    normalized_placeholder_count = (
        normalized_content.count("[Specify]")
        + normalized_content.count("[List")
        + normalized_content.count("[Describe")
    )

    if normalized_placeholder_count <= original_placeholder_count:
        content = normalized_content
    else:
        console.print(
            "[yellow]Warning: Normalization would introduce placeholders, using original content[/yellow]"
        )

    filename = f"chapter_outlines/chapter_{chapter_info['number']}.md"

    # Add regeneration notice if this was regenerated with feedback
    if feedback:
        import datetime

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        regeneration_notice = (
            f"\n\n<!-- Outline regenerated with feedback at {timestamp} -->\n"
        )
        # Insert after the first heading
        lines = content.split("\n", 1)
        if len(lines) == 2:
            content = lines[0] + regeneration_notice + lines[1]
        console.print(f"[cyan]Outline regenerated at {timestamp}[/cyan]")

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


def normalize_outline_format(outline_text: str, chapter_num: int, title: str) -> str:
    """Normalize outline text to consistent format while preserving content.

    This function tries to extract and normalize the outline structure.
    If extraction fails, it falls back to the original text to avoid losing content.
    """
    import re

    lines = outline_text.split("\n")

    # Extract key information using flexible matching
    pov_char = ""
    setting = ""
    chapter_goal = ""
    emotional_arc = ""
    scenes = []
    connections = []
    foreshadowing = []

    # Section state
    in_overview = False
    in_scene_breakdown = False
    in_connections = False
    in_foreshadowing = False

    current_scene_content = []
    current_scene_title = None
    current_scene_setting = None
    current_scene_pov = None

    for i, line in enumerate(lines):
        line_stripped = line.strip()
        if not line_stripped or line_stripped.startswith("---"):
            continue

        line_upper = line_stripped.upper()
        line_lower = line_stripped.lower()

        # Detect section headers
        if any(h in line_upper for h in ["OVERVIEW", "OUTLINE STRUCTURE", "BREAKDOWN"]):
            in_overview = True
            in_scene_breakdown = False
            in_connections = False
            in_foreshadowing = False
            if "SCENE" in line_upper and "BREAKDOWN" in line_upper:
                in_scene_breakdown = True
                in_overview = False
            continue

        if "CONNECTION" in line_upper and (
            "PREVIOUS" in line_upper or "NEXT" in line_upper
        ):
            in_connections = True
            in_scene_breakdown = False
            in_overview = False
            in_foreshadowing = False
            continue

        if "FORESHADOW" in line_upper or "CALLBACK" in line_upper:
            in_foreshadowing = True
            in_connections = False
            in_scene_breakdown = False
            in_overview = False
            continue

        # Extract overview information
        if in_overview and not in_scene_breakdown:
            if "POV" in line_upper and ":" in line:
                pov_char = line.split(":", 1)[1].strip()
                # Remove markdown bold markers if present
                pov_char = pov_char.strip("*").strip()
                continue
            elif "SETTING" in line_upper and ":" in line and "SCENE" not in line_upper:
                setting = line.split(":", 1)[1].strip()
                # Remove markdown bold markers if present
                setting = setting.strip("*").strip()
                continue
            elif "GOAL" in line_upper and ":" in line and "CHAPTER" in line_upper:
                chapter_goal = line.split(":", 1)[1].strip()
                # Remove markdown bold markers if present
                chapter_goal = chapter_goal.strip("*").strip()
                continue
            elif "EMOTIONAL" in line_upper or "ARC" in line_upper:
                if ":" in line:
                    emotional_arc = line.split(":", 1)[1].strip()
                    # Remove markdown bold markers if present
                    emotional_arc = emotional_arc.strip("*").strip()
                continue

        # Extract scene breakdown
        if in_scene_breakdown or (
            not in_overview and not in_connections and not in_foreshadowing
        ):
            # Skip setting/POV/action metadata lines
            if any(
                marker in line_upper
                for marker in ["SETTING:", "**SETTING**", "POV:", "**POV**", "ACTION:"]
            ):
                if "SETTING:" in line_upper or "**SETTING**" in line_upper:
                    current_scene_setting = line.split(":", 1)[-1].strip().strip("*")
                elif "POV:" in line_upper or "**POV**" in line_upper:
                    current_scene_pov = line.split(":", 1)[-1].strip().strip("*")
                continue

            # Check for scene markers with various formats (but not metadata lines)
            is_scene_header = False
            scene_title = None

            # Match: ### Scene X: TITLE, ## X. TITLE, **TITLE**, SCENE: TITLE, etc
            if line_stripped.startswith("###"):
                scene_title = line_stripped[3:].strip()
                # Remove duplicate "Scene X:" prefixes if present
                scene_title = re.sub(
                    r"^Scene\s+\d+:\s*", "", scene_title, flags=re.IGNORECASE
                )
                is_scene_header = True
            elif line_stripped.startswith("##") and not line_stripped.startswith("###"):
                potential_title = line_stripped[2:].strip()
                # Only treat as scene if it looks like a title (not a section header)
                if not any(
                    h in potential_title.upper()
                    for h in ["SCENE", "ACT", "BREAKDOWN", "CHAPTER"]
                ):
                    scene_title = potential_title
                    is_scene_header = True
            elif re.match(r"^\d+\.", line_stripped):
                # Numbered list item like "1. Title"
                scene_title = line_stripped
                is_scene_header = True
            elif line_stripped.startswith("**") and line_stripped.endswith("**"):
                # Bold title like "**TITLE**"
                potential = line_stripped.strip("*")
                if len(potential) < 100 and not any(
                    h in potential.upper() for h in ["SETTING", "POV", "ACTION"]
                ):
                    scene_title = potential
                    is_scene_header = True

            if is_scene_header and scene_title:
                # Save previous scene
                if current_scene_title:
                    scenes.append(
                        {
                            "title": current_scene_title,
                            "setting": current_scene_setting or "",
                            "pov": current_scene_pov or "",
                            "content": current_scene_content,
                        }
                    )
                    current_scene_content = []

                current_scene_title = scene_title
                current_scene_setting = None
                current_scene_pov = None
            elif line_stripped and not line_stripped.startswith("#"):
                # Regular content line
                current_scene_content.append(line_stripped)

        # Extract connections
        if in_connections:
            if line_stripped.startswith(("-", "*", "•")) and len(line_stripped) > 2:
                conn_text = line_stripped.lstrip("-*•").strip()
                if conn_text and not any(conn_text in c for c in connections):
                    connections.append(f"- {conn_text}")
            elif ":" in line_stripped and "connection" in line_stripped.lower():
                conn_text = line_stripped.split(":", 1)[1].strip()
                if conn_text:
                    label = line_stripped.split(":")[0].strip()
                    connections.append(f"**{label}:** {conn_text}")

        # Extract foreshadowing
        if in_foreshadowing:
            if line_stripped.startswith(("-", "*", "•")) and len(line_stripped) > 2:
                text = line_stripped.lstrip("-*•").strip()
                if text and text not in foreshadowing:
                    foreshadowing.append(text)

    # Don't forget the last scene
    if current_scene_title:
        scenes.append(
            {
                "title": current_scene_title,
                "setting": current_scene_setting or "",
                "pov": current_scene_pov or "",
                "content": current_scene_content,
            }
        )

    # Helper to check if value is usable (not a placeholder)
    def get_value(value: str, default: str) -> str:
        """Return value if it's not a placeholder, otherwise return default."""
        if value and not is_placeholder_value(value):
            return value
        return default

    # Build normalized outline with fallback to original content
    normalized = f"""# CHAPTER {chapter_num}: {title.upper()}

## CHAPTER OVERVIEW

**POV Character:** {get_value(pov_char, "[Specify]")}
**Setting:** {get_value(setting, "[Specify]")}
**Characters Present:** [List characters]

**Chapter Goal:** {get_value(chapter_goal, "[Specify]")}

**Emotional Arc:** {get_value(emotional_arc, "[Specify]")}

**Target Word Count:** 2000-3000 words

## SCENE BREAKDOWN
"""

    if scenes:
        # Limit to exactly 3 scenes
        for i, scene in enumerate(scenes[:3], 1):
            scene_content = (
                " ".join(scene["content"][:5])
                if scene["content"]
                else "[Describe what happens]"
            )
            normalized += f"""
### Scene {i}: {scene["title"]}
**Setting:** {get_value(scene["setting"], "[Specify location]")}
**POV:** {get_value(scene["pov"], "[Specify character]")}
**Action:** {scene_content[:300]}
"""
    else:
        normalized += """
### Scene 1: [Opening]
**Setting:** [Specify location]
**POV:** [Specify character]
**Action:** [Describe what happens]

### Scene 2: [Escalation]
**Setting:** [Specify location]
**POV:** [Specify character]
**Action:** [Describe what happens]

### Scene 3: [Resolution]
**Setting:** [Specify location]
**POV:** [Specify character]
**Action:** [Describe what happens]
"""

    normalized += """
## STORY CONNECTIONS

"""
    if connections:
        for conn in connections:
            normalized += f"{conn}\n"
    else:
        normalized += "**Connection to previous chapter:** [Specify]\n**Connection to next chapter:** [Specify]\n"

    normalized += """
## FORESHADOWING & CALLBACKS

"""
    if foreshadowing:
        for item in foreshadowing:
            normalized += f"- {item}\n"
    else:
        normalized += "- [Foreshadowing element 1]\n- [Foreshadowing element 2]\n"

    return normalized


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
