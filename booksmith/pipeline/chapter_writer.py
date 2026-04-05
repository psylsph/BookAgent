import re
from pathlib import Path
from typing import Generator, List, Optional

from ..api_client import APIClient, format_prompt
from ..storage.project import Project
from ..ui.console import (
    console,
    print_header,
    print_warning,
    count_words,
)
from .retrieval import BookRetriever, format_retrieved_context


CHAPTER_WRITER_SYSTEM_PROMPT = (
    "You are a professional fiction author. You write vivid, immersive prose "
    "with strong character voice, purposeful pacing, and cinematic scene construction. "
    "You never summarise when you can show. "
    "Write tight, focused prose - every scene must advance plot or character. "
    "No filler scenes, padding, or unnecessary characters. "
    "Develop character voice and interiority through action and dialogue. "
    "Create tension and momentum. End chapters with hooks that pull readers forward. "
    "Never repeat content from previous chapters. Show don't tell. "
    "CRITICAL: Stay within the target word count range. Do not write excessively long chapters."
)

CHAPTER_WRITER_SYSTEM_REWRITE = (
    "You are a professional fiction author rewriting a chapter based on feedback. "
    "Preserve what works well in the current draft while addressing the review comments. "
    "Maintain the same chapter outline and scene structure. "
    "Write vivid, immersive prose with strong character voice and purposeful pacing. "
    "Never summarise when you can show. Show don't tell."
)


def extract_character_names_from_outline(
    outline: str, available_names: List[str]
) -> List[str]:
    """Extract character names mentioned in the chapter outline.

    Only returns names that exist in the available character list.
    Falls back to all available names if none are found in the outline.
    """
    outline_lower = outline.lower()
    mentioned = []
    for name in available_names:
        if name.lower() in outline_lower:
            mentioned.append(name)
    return mentioned if mentioned else available_names


def build_rewrite_context(
    project: Project,
    chapter_num: int,
    review_comments: str,
    current_text: str,
) -> dict:
    """Build adaptive context for chapter rewrites.

    Only includes the chapter outline when review comments indicate
    structural changes are needed. The context brief already contains
    all relevant story bible and character info.
    """
    context = {
        "current_text": current_text,
        "review_comments": review_comments,
    }

    review_lower = review_comments.lower()

    structure_keywords = [
        "structure",
        "outline",
        "scene",
        "flow",
        "pacing",
        "transition",
        "organization",
        "arrangement",
        "order",
    ]
    structure_matches = sum(1 for kw in structure_keywords if kw in review_lower)
    if structure_matches >= 2:
        outline = project.get_chapter_outline(chapter_num)
        if outline:
            context["chapter_outline"] = outline

    return context


def build_chapter_context(
    project: Project,
    chapter_num: int,
    chapter_outline: str,
) -> dict:
    """Build context for chapter writing."""
    config = project.config

    story_bible = project.read_file("story_bible.md")
    # Truncate story bible if too long
    if len(story_bible) > 3000:
        story_bible = story_bible[:3000] + "\n\n[... story bible truncated ...]"

    retriever = BookRetriever(project.path)
    top_n = 4 if chapter_num == 1 else 8
    retrieved_chunks = retriever.retrieve_for_chapter(
        chapter_outline, chapter_num, top_n=top_n
    )
    retrieved_context = format_retrieved_context(retrieved_chunks)

    characters = project.get_characters()
    available_names = [char["name"] for char in characters if "name" in char]
    relevant_names = extract_character_names_from_outline(
        chapter_outline, available_names
    )

    character_profiles = []
    for char in characters:
        if "name" not in char:
            continue
        name = char["name"]
        if name not in relevant_names:
            continue
        char_file = f"characters/{name.replace(' ', '_')}.md"
        try:
            profile = project.read_file(char_file)
            character_profiles.append(f"## {name}\n{profile[:500]}")
        except FileNotFoundError:
            continue

    if not character_profiles and available_names:
        for name in available_names[:3]:
            char_file = f"characters/{name.replace(' ', '_')}.md"
            try:
                profile = project.read_file(char_file)
                character_profiles.append(f"## {name}\n{profile[:500]}")
            except FileNotFoundError:
                continue

    character_text = "\n\n".join(character_profiles) or "No character profiles found."

    return {
        "story_bible": story_bible,
        "retrieved_context": retrieved_context,
        "character_profiles": character_text,
        "chapter_outline": chapter_outline,
        "chapter_number": chapter_num,
        "min_words": config.get("min_words_per_chapter", 2000),
        "pov": config.get("pov", "third person limited"),
        "tense": config.get("tense", "past"),
        "tone": config.get("tone", "literary"),
    }


def generate_context_brief(
    project: Project,
    client: APIClient,
    chapter_num: int,
    chapter_outline: str,
) -> str:
    """Use Haiku to extract relevant context into a tight brief for Sonnet.

    Sends the full story bible, world guide, and character profiles to Haiku,
    which extracts only what's relevant to this specific chapter.
    This avoids information loss from naive truncation while keeping context minimal.
    """
    config = project.config

    # Load all context sources
    story_bible = project.read_file("story_bible.md")
    world_guide = project.read_file("world.md")

    # Get macro summary for previous chapters context
    try:
        previous_summary = project.get_macro_summary()
    except FileNotFoundError:
        previous_summary = "No previous chapters written yet."

    # Get character profiles
    characters = project.get_characters()
    available_names = [char["name"] for char in characters if "name" in char]
    relevant_names = extract_character_names_from_outline(
        chapter_outline, available_names
    )

    character_profiles = []
    for char in characters:
        if "name" not in char:
            continue
        name = char["name"]
        if name not in relevant_names:
            continue
        char_file = f"characters/{name.replace(' ', '_')}.md"
        try:
            profile = project.read_file(char_file)
            character_profiles.append(f"## {name}\n{profile}")
        except FileNotFoundError:
            continue

    character_text = "\n\n".join(character_profiles) or "No character profiles found."

    # Load and format the prompt template
    system_prompt, user_prompt = format_prompt(
        "chapter_context",
        chapter_number=chapter_num,
        chapter_outline=chapter_outline,
        story_bible=story_bible,
        character_profiles=character_text,
        world_guide=world_guide,
        previous_summary=previous_summary,
        pov=config.get("pov", "third person limited"),
        tense=config.get("tense", "past"),
        tone=config.get("tone", "literary"),
    )

    brief = ""
    for chunk in client.stream(
        stage="context_brief",
        system=system_prompt,
        user_message=user_prompt,
        project_config=project.config,
    ):
        brief += chunk

    return brief


def generate_chapter(
    project: Project,
    client: APIClient,
    chapter_num: int,
    extra_feedback: Optional[str] = None,
) -> str:
    """Generate a chapter with context."""
    print_header(f"Generating Chapter {chapter_num}...")

    chapter_outline = project.get_chapter_outline(chapter_num)
    if not chapter_outline:
        raise ValueError(f"No outline found for chapter {chapter_num}")

    config = project.config

    # Use Haiku to condense all context into a brief for Sonnet
    console.print("[cyan]Summarizing context...[/cyan]")
    context_brief = generate_context_brief(
        project, client, chapter_num, chapter_outline
    )

    # Save context brief for inspection
    brief_path = f"chapters/chapter_{chapter_num}_context_brief.md"
    project.write_file(brief_path, context_brief)
    brief_word_count = len(context_brief.split())
    console.print(f"[dim]Context brief: {brief_word_count} words[/dim]")

    # If there's feedback (from AI review), rewrite with the feedback instead
    if extra_feedback:
        draft_path = f"chapters/chapter_{chapter_num}_draft.md"
        try:
            current_text = project.read_file(draft_path)
        except FileNotFoundError:
            current_text = ""

        console.print("[cyan]Rewriting chapter with AI feedback...[/cyan]")

        rewrite_context = build_rewrite_context(
            project, chapter_num, extra_feedback, current_text
        )

        rewrite_prompt = f"""## Context Brief

{context_brief}

## Current Chapter Text

{rewrite_context["current_text"]}

## AI Review Comments to Address

{rewrite_context["review_comments"]}
"""

        if "chapter_outline" in rewrite_context:
            rewrite_prompt += (
                f"\n## Chapter Outline\n\n{rewrite_context['chapter_outline']}\n"
            )

        rewrite_prompt += """
## Instructions

Rewrite the chapter incorporating the AI review comments above. Keep the same chapter outline but address the issues raised in the review. Output ONLY the revised chapter text.
"""

        chapter_content = ""
        for chunk in client.stream(
            stage="chapter_writer",
            system=CHAPTER_WRITER_SYSTEM_REWRITE,
            user_message=rewrite_prompt,
            project_config=project.config,
        ):
            chapter_content += chunk
    else:
        # Normal generation
        user_message = f"""## Context Brief

{context_brief}

## Current Chapter Outline

{chapter_outline}

---

Write Chapter {chapter_num}.

Target: {config.get("min_words_per_chapter", 1500)} words. Write substantial, developed scenes with rich detail, dialogue, sensory descriptions, and character introspection."""

        chapter_content = ""
        for chunk in client.stream(
            stage="chapter_writer",
            system=f"{CHAPTER_WRITER_SYSTEM_PROMPT}\n\nIMPORTANT: Output ONLY the chapter text. Do not include any thinking, reasoning, analysis, or metadata. Just write the story. Do NOT include scene titles, section headers, or labels. Write in {config.get('pov', 'third person limited')} POV, {config.get('tense', 'past')} tense, with a {config.get('tone', 'literary')} tone.",
            user_message=user_message,
            project_config=project.config,
        ):
            chapter_content += chunk

    word_count = count_words(chapter_content)
    console.print(f"[cyan]Word count: {word_count}[/cyan]")

    # Warn if chapter is excessively long (>5000 words)
    max_words = 5000
    if word_count > max_words:
        console.print(
            f"[yellow]WARNING: Chapter is {word_count} words, which exceeds the recommended maximum of {max_words} words. "
            f"This may cause context overflow in subsequent review passes. "
            f"Consider editing the chapter to reduce length.[/yellow]"
        )

    draft_path = f"chapters/chapter_{chapter_num}_draft.md"
    project.write_file(draft_path, chapter_content)

    return chapter_content


def regenerate_chapter(
    project: Project,
    client: APIClient,
    chapter_num: int,
    feedback: Optional[str] = None,
) -> str:
    """Regenerate a chapter with optional feedback."""
    return generate_chapter(project, client, chapter_num, feedback)
