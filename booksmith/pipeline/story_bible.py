import re
from pathlib import Path
from typing import Generator, Optional

from ..api_client import APIClient, DEFAULT_MIN_WORDS, format_prompt
from ..storage.project import Project
from ..ui.console import console, print_header

CHAPTER_TARGET_WORDS = 1750


def extract_word_count(story_bible: str) -> int:
    """Extract estimated total word count from story bible."""
    # Try "**Estimated Word Count** - 50000" format
    est_match = re.search(
        r"\*\*Estimated Word Count\*\*\s*[-–—]?\s*([\d,]+)", story_bible, re.IGNORECASE
    )
    if est_match:
        return int(est_match.group(1).replace(",", ""))

    # Try "Estimated Word Count: 50000" format
    est_match2 = re.search(
        r"estimated\s+word\s+count\s*[:=]\s*([\d,]+)", story_bible, re.IGNORECASE
    )
    if est_match2:
        return int(est_match2.group(1).replace(",", ""))

    # Try "50,000 words" or "50000 words"
    words_match = re.search(r"([\d,]+)\s*words?", story_bible, re.IGNORECASE)
    if words_match:
        return int(words_match.group(1).replace(",", ""))

    return 0


def calculate_chapter_count(
    total_words: int, min_words: int = DEFAULT_MIN_WORDS
) -> int:
    """Calculate chapter count from total word count.

    Chapters are targeted at ~1750 words. Returns enough chapters to
    cover the total word count, clamped to a minimum of 8.
    """
    if total_words <= 0:
        return 24

    count = max(8, round(total_words / CHAPTER_TARGET_WORDS))
    return count


def generate_story_bible(
    project: Project,
    client: APIClient,
    extra_instruction: Optional[str] = None,
) -> str:
    """Generate story bible from seed file."""
    print_header("Generating Story Bible...")

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

    total_words = extract_word_count(content)
    chapter_count = calculate_chapter_count(total_words)
    project.set_total_chapters(chapter_count)

    if total_words > 0:
        console.print(
            f"[dim]Estimated total: {total_words:,} words → {chapter_count} chapters[/dim]"
        )

    return content


def regenerate_story_bible(
    project: Project,
    client: APIClient,
    extra_instruction: Optional[str] = None,
) -> str:
    """Regenerate story bible with optional extra instruction."""
    return generate_story_bible(project, client, extra_instruction)
