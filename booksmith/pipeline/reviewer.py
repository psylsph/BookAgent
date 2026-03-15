import re
from typing import Optional

from ..api_client import APIClient, format_prompt
from ..storage.project import Project
from ..ui import console


def extract_score(review_text: str) -> Optional[float]:
    """Extract quality score from review text."""
    patterns = [
        r"(\d+(?:\.\d+)?)\s*/\s*10",
        r"score[:\s]*(\d+(?:\.\d+)?)",
        r"rating[:\s]*(\d+(?:\.\d+)?)",
        r"quality[:\s]*(\d+(?:\.\d+)?)",
    ]

    for pattern in patterns:
        match = re.search(pattern, review_text, re.IGNORECASE)
        if match:
            score = float(match.group(1))
            if 0 <= score <= 10:
                return score

    return None


def generate_review(
    project: Project,
    client: APIClient,
    chapter_num: int,
) -> tuple[str, float]:
    """Generate AI review for a chapter draft."""
    console.print_header(f"Generating review for Chapter {chapter_num}...")

    chapter_outline = project.get_chapter_outline(chapter_num)
    chapter_draft = project.read_file(f"chapters/chapter_{chapter_num}_draft.md")

    characters = project.get_characters()
    character_profiles = []
    for char in characters:
        char_file = f"characters/{char['name'].replace(' ', '_')}.md"
        try:
            profile = project.read_file(char_file)
            character_profiles.append(f"## {char['name']}\n{profile[:500]}")
        except FileNotFoundError:
            continue

    character_text = "\n\n".join(character_profiles) or "No character profiles found."

    previous_summary = None
    try:
        previous_summary = project.get_macro_summary()
    except FileNotFoundError:
        previous_summary = "No previous chapters yet."

    system_prompt, user_prompt = format_prompt(
        "reviewer",
        chapter_outline=chapter_outline,
        character_profiles=character_text,
        previous_summary=previous_summary,
        chapter_content=chapter_draft,
    )

    review = ""
    for chunk in client.stream(
        stage="reviewer",
        system=system_prompt,
        user_message=user_prompt,
        project_config=project.config,
    ):
        review += chunk

    score = extract_score(review) or 5.0

    review_file = f"reviews/chapter_{chapter_num}_review.md"
    project.write_file(review_file, review)

    return review, score


def get_review(
    project: Project, chapter_num: int
) -> tuple[Optional[str], Optional[float]]:
    """Get existing review or generate new one."""
    try:
        review = project.read_file(f"reviews/chapter_{chapter_num}_review.md")
        score = extract_score(review) or 5.0
        return review, score
    except FileNotFoundError:
        return None, None
