import re
from pathlib import Path
from typing import Generator, Optional

from ..api_client import APIClient, format_prompt
from ..storage.project import Project
from ..ui import console


def extract_chapter_count(story_bible: str) -> int:
    """Extract suggested chapter count from story bible."""
    patterns = [
        r"(\d+)\s*chapters?",
        r"chapter\s*count[:\s]*(\d+)",
        r"approximately\s*(\d+)\s*chapters?",
    ]

    for pattern in patterns:
        match = re.search(pattern, story_bible, re.IGNORECASE)
        if match:
            return int(match.group(1))

    return 24


def generate_story_bible(
    project: Project,
    client: APIClient,
    extra_instruction: Optional[str] = None,
) -> str:
    """Generate story bible from seed file."""
    console.print_header("Generating Story Bible...")

    seed_content = project.read_file(project.seed_file)

    system_prompt, user_prompt = format_prompt(
        "story_bible",
        seed_content=seed_content,
    )

    if extra_instruction:
        user_prompt += f"\n\n---\n\nAdditional instruction: {extra_instruction}"

    story_bible = client.stream(
        stage="story_bible",
        system=system_prompt,
        user_message=user_prompt,
        project_config=project.config,
    )

    content = ""
    for chunk in story_bible:
        content += chunk

    project.write_file("story_bible.md", content)

    chapter_count = extract_chapter_count(content)
    project.set_total_chapters(chapter_count)

    return content


def regenerate_story_bible(
    project: Project,
    client: APIClient,
    extra_instruction: Optional[str] = None,
) -> str:
    """Regenerate story bible with optional extra instruction."""
    return generate_story_bible(project, client, extra_instruction)
