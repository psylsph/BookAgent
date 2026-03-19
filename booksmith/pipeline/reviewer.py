import re
from typing import Optional

from ..api_client import APIClient, format_prompt
from ..storage.project import Project
from ..ui import console


def extract_score(review_text: str) -> Optional[float]:
    """Extract quality score from review text."""
    patterns = [
        r"(\d+(?:\.\d+)?)\s*/\s*10",
        r"(\d+(?:\.\d+)?)\s+out\s+of\s+10",
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
    # Try draft first, fall back to final version
    try:
        chapter_draft = project.read_file(f"chapters/chapter_{chapter_num}_draft.md")
    except FileNotFoundError:
        chapter_draft = project.read_file(f"chapters/chapter_{chapter_num}.md")

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


def generate_outline_review(
    project: Project,
    client: APIClient,
    chapter_num: int,
) -> tuple[str, float]:
    """Generate AI review for a chapter outline."""
    console.print_header(f"Generating outline review for Chapter {chapter_num}...")

    chapter_outline = project.get_chapter_outline(chapter_num)
    story_bible = project.read_file("story_bible.md")

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

    prompt = f"""## OUTLINE REVIEW - NOT CHAPTER PROSE

You are reviewing a CHAPTER OUTLINE (structure/scenes), NOT written prose.

## Story Bible

{story_bible}

## Character Profiles

{character_text}

## Chapter Outline

{chapter_outline}

---

OUTLINE REVIEW CRITERIA:

1. **Story Alignment**: Does this outline follow from the story bible and serve the overall plot?
2. **Chapter Purpose**: Is the purpose of this chapter clear and meaningful?
3. **Character Logic**: Are character actions consistent with their established arcs?
4. **Pacing**: Does the scene breakdown create good flow?
5. **Continuity**: Any issues with world/character state?
6. **Setup & Payoff**: Are seeds planted for future chapters?

Provide a score 0-10 and specific feedback. Focus on structural improvements, not prose quality."""

    review = ""
    for chunk in client.stream(
        stage="outline_reviewer",
        system="You are a professional book editor and plot architect. Your task is to review chapter outlines for coherence, pacing, and story alignment.",
        user_message=prompt,
        project_config=project.config,
    ):
        review += chunk

    score = extract_score(review) or 5.0

    review_file = f"reviews/chapter_{chapter_num}_outline_review.md"
    project.write_file(review_file, review)

    return review, score
