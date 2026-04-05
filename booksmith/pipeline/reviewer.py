import re
from typing import Optional

from ..api_client import APIClient, format_prompt
from ..storage.project import Project
from ..ui.console import console, print_header


def check_placeholders(outline_text: str) -> tuple[int, list[str]]:
    """Check outline for placeholder text and return count and examples."""
    placeholder_patterns = [
        r"\[Specify[^\]]*\]",
        r"\[Describe[^\]]*\]",
        r"\[Character[^\]]*\]",
        r"\[Location[^\]]*\]",
        r"\[Action[^\]]*\]",
        r"\[Opening[^\]]*\]",
        r"\[Escalation[^\]]*\]",
        r"\[Climax[^\]]*\]",
        r"\[Resolution[^\]]*\]",
        r"\[Foreshadowing[^\]]*\]",
        r"\[Callback[^\]]*\]",
        r"\[SCENE[^\]]*\]",
        r"\[POV[^\]]*\]",
        r"\[Setting[^\]]*\]",
    ]

    found = []
    for pattern in placeholder_patterns:
        matches = re.findall(pattern, outline_text, re.IGNORECASE)
        found.extend(matches)

    return len(found), found[:10]  # Return count and first 10 examples


def extract_score(review_text: str) -> Optional[float]:
    """Extract quality score from review text."""
    word_to_num = {
        "zero": 0,
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
    }

    patterns = [
        r"(\d+(?:\.\d+)?)\s*/\s*10",
        r"(\d+(?:\.\d+)?)\s+out\s+of\s+10",
        r"score[:\s]*(\d+(?:\.\d+)?)",
        r"rating[:\s]*(\d+(?:\.\d+)?)",
        r"quality[:\s]*(\d+(?:\.\d+)?)",
        r"overall[:\s]*(\d+(?:\.\d+)?)",
        r"final\s+score[:\s]*(\d+(?:\.\d+)?)",
    ]

    for pattern in patterns:
        match = re.search(pattern, review_text, re.IGNORECASE)
        if match:
            score = float(match.group(1))
            if 0 <= score <= 10:
                return score

    for word, num in word_to_num.items():
        pattern = rf"\b{word}\s+out\s+of\s+10\b"
        if re.search(pattern, review_text, re.IGNORECASE):
            return float(num)

    return None


def truncate_chapter_for_review(chapter_text: str, max_words: int = 3000) -> str:
    """Truncate chapter content for review, keeping beginning and end.

    This prevents context overflow while preserving chapter structure.
    Returns first 2/3 and last 1/3 of content within max_words limit.
    """
    words = chapter_text.split()
    if len(words) <= max_words:
        return chapter_text

    # Keep first 2/3 and last 1/3, but cap at max_words
    first_part_size = int(max_words * 0.67)
    last_part_size = max_words - first_part_size

    first_part = " ".join(words[:first_part_size])
    last_part = " ".join(words[-last_part_size:])

    return f"{first_part}\n\n[... middle section omitted for review ...]\n\n{last_part}"


def generate_review(
    project: Project,
    client: APIClient,
    chapter_num: int,
) -> tuple[str, float]:
    """Generate AI review for a chapter draft."""
    print_header(f"Generating review for Chapter {chapter_num}...")

    chapter_outline = project.get_chapter_outline(chapter_num)
    # Try draft first, fall back to final version
    try:
        chapter_draft = project.read_file(f"chapters/chapter_{chapter_num}_draft.md")
    except FileNotFoundError:
        chapter_draft = project.read_file(f"chapters/chapter_{chapter_num}.md")

    # Truncate chapter to prevent context overflow
    chapter_draft = truncate_chapter_for_review(chapter_draft, max_words=3000)

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
        # Truncate macro summary to prevent context overflow
        if previous_summary and len(previous_summary) > 2000:
            previous_summary = (
                previous_summary[:2000] + "\n\n[... summary truncated ...]"
            )
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

    score = extract_score(review) or 6.0

    review_file = f"reviews/chapter_{chapter_num}_review.md"
    project.write_file(review_file, review)

    return review, score


def get_review(
    project: Project, chapter_num: int
) -> tuple[Optional[str], Optional[float]]:
    """Get existing review or generate new one."""
    try:
        review = project.read_file(f"reviews/chapter_{chapter_num}_review.md")
        score = extract_score(review) or 6.0
        return review, score
    except FileNotFoundError:
        return None, None


def generate_outline_review(
    project: Project,
    client: APIClient,
    chapter_num: int,
) -> tuple[str, float]:
    """Generate AI review for a chapter outline."""
    print_header(f"Generating outline review for Chapter {chapter_num}...")

    chapter_outline = project.get_chapter_outline(chapter_num)
    story_bible = project.read_file("story_bible.md")

    # Check for placeholders first
    placeholder_count, placeholder_examples = check_placeholders(chapter_outline)

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

    placeholder_warning = ""
    if placeholder_count > 3:
        placeholder_warning = f"""

⚠️ CRITICAL ISSUE: This outline contains {placeholder_count} placeholders!

Examples of placeholders found:
{chr(10).join(f"- {ex}" for ex in placeholder_examples)}

This outline MUST be regenerated with actual content. Placeholders indicate the AI did not provide specific details.
"""

    prompt = f"""## OUTLINE REVIEW - NOT CHAPTER PROSE

You are reviewing a CHAPTER OUTLINE (structure/scenes), NOT written prose.

## Story Bible

{story_bible}

## Character Profiles

{character_text}

## Chapter Outline

{chapter_outline}

{placeholder_warning}

---

OUTLINE REVIEW CRITERIA:

1. **COMPLETENESS (CRITICAL)**: Does this outline contain specific details or just placeholders like [Specify], [Describe]? If there are more than 3 placeholders, score should be 3 or below.
2. **Story Alignment**: Does this outline follow from the story bible and serve the overall plot?
3. **Chapter Purpose**: Is the purpose of this chapter clear and meaningful?
4. **Character Logic**: Are character actions consistent with their established arcs?
5. **Pacing**: Does the scene breakdown create good flow?
6. **Continuity**: Any issues with world/character state?
7. **Setup & Payoff**: Are seeds planted for future chapters?

SCORING GUIDE:
- 0-3/10: Outline contains placeholders or is incomplete
- 4-6/10: Outline has structure but weak content
- 7-8/10: Good outline with specific details
- 9-10/10: Excellent outline with specific, meaningful content

Provide a score 0-10 and specific feedback. Focus on structural improvements, not prose quality."""

    review = ""
    for chunk in client.stream(
        stage="outline_reviewer",
        system="You are a professional book editor and plot architect. Your task is to review chapter outlines for coherence, pacing, and story alignment.",
        user_message=prompt,
        project_config=project.config,
    ):
        review += chunk

    score = extract_score(review) or 6.0

    # If there are many placeholders, cap the score at 3
    if placeholder_count > 3 and score > 3:
        score = 3.0
        review += f"\n\n⚠️ Score capped at 3/10 due to {placeholder_count} placeholders found in outline."

    review_file = f"reviews/chapter_{chapter_num}_outline_review.md"
    project.write_file(review_file, review)

    return review, score
