from pathlib import Path
from typing import Generator, Optional

from ..api_client import APIClient, format_prompt
from ..storage.project import Project
from ..ui.console import (
    console,
    print_header,
    print_warning,
    count_words,
)
from .retrieval import BookRetriever, format_retrieved_context


MAX_WORD_COUNT_RETRIES = 3


def count_words(text: str) -> int:
    """Count words in text."""
    return len(text.split())


def summarize_text(text: str, max_words: int = 500) -> str:
    """Summarize text to max_words."""
    words = text.split()
    if len(words) <= max_words:
        return text

    return " ".join(words[:max_words]) + "..."


def build_chapter_context(
    project: Project,
    chapter_num: int,
    chapter_outline: str,
) -> dict:
    """Build context for chapter writing."""
    config = project.config

    story_bible = project.read_file("story_bible.md")
    story_bible_summary = summarize_text(story_bible, 500)

    previous_chapter = None
    if chapter_num > 1:
        try:
            previous_chapter = project.get_approved_chapter(chapter_num - 1)
            if previous_chapter:
                previous_chapter = summarize_text(previous_chapter, 750)
        except FileNotFoundError:
            previous_chapter = None

    macro_summary = None
    try:
        macro_summary = project.get_macro_summary()
    except FileNotFoundError:
        macro_summary = None

    retriever = BookRetriever(project.path)
    retrieved_chunks = retriever.retrieve_for_chapter(
        chapter_outline, chapter_num, top_n=8
    )
    retrieved_context = format_retrieved_context(retrieved_chunks)

    return {
        "story_bible_summary": story_bible_summary,
        "macro_summary": macro_summary or "No prior chapters yet.",
        "previous_chapter": previous_chapter or "This is the first chapter.",
        "retrieved_context": retrieved_context,
        "chapter_outline": chapter_outline,
        "chapter_number": chapter_num,
        "chapter_title": f"Chapter {chapter_num}",
        "min_words": config.get("min_words_per_chapter", 2000),
        "pov": config.get("pov", "third person limited"),
        "tense": config.get("tense", "past"),
        "tone": config.get("tone", "literary"),
    }


def generate_chapter(
    project: Project,
    client: APIClient,
    chapter_num: int,
    extra_feedback: Optional[str] = None,
) -> str:
    """Generate a chapter with context and word count enforcement."""
    print_header(f"Generating Chapter {chapter_num}...")

    chapter_outline = project.get_chapter_outline(chapter_num)
    if not chapter_outline:
        raise ValueError(f"No outline found for chapter {chapter_num}")

    context = build_chapter_context(project, chapter_num, chapter_outline)

    # Build full prompt with all context
    user_message = f"""## Story Bible (summary)

{context["story_bible_summary"]}

## Macro Summary (all prior chapters)

{context["macro_summary"]}

## Previous Chapter Summary

{context["previous_chapter"]}

## Retrieved Context (relevant characters, locations, prior scenes)

{context["retrieved_context"]}

## Current Chapter Outline

{context["chapter_outline"]}

---

Write Chapter {context["chapter_number"]}: {context["chapter_title"]}.

Focus on quality and tightness. Include only the scenes needed to fulfill the chapter purpose. Do NOT add filler to hit word counts."""

    # If there's feedback (from AI review), rewrite with the feedback instead
    if extra_feedback:
        # First get current chapter text from draft
        draft_path = f"chapters/chapter_{chapter_num}_draft.md"
        try:
            current_text = project.read_file(draft_path)
        except FileNotFoundError:
            current_text = ""

        console.print("[cyan]Rewriting chapter with AI feedback...[/cyan]")

        rewrite_prompt = f"""## Current Chapter Text

{current_text}

## AI Review Comments to Address

{extra_feedback}

## Instructions

Rewrite the chapter incorporating the AI review comments above. Keep the same chapter outline but address the issues raised in the review. Output ONLY the revised chapter text.

Context:
- Story Bible: {context["story_bible_summary"]}
- Previous Chapter: {context["previous_chapter"]}
- Chapter Outline: {context["chapter_outline"]}
"""

        chapter_content = ""
        for chunk in client.stream(
            stage="chapter_writer",
            system="You are a professional fiction author. Rewrite the chapter based on feedback.",
            user_message=rewrite_prompt,
            project_config=project.config,
        ):
            chapter_content += chunk
    else:
        # Normal generation
        chapter_content = ""
        for chunk in client.stream(
            stage="chapter_writer",
            system="You are a professional fiction author. Output ONLY the chapter text. No thinking, no reasoning, just the story.",
            user_message=user_message,
            project_config=project.config,
        ):
            chapter_content += chunk

    word_count = count_words(chapter_content)
    min_words = context["min_words"]

    console.print(f"[cyan]Initial word count: {word_count}[/cyan]")

    retries = 0
    while word_count < min_words and retries < MAX_WORD_COUNT_RETRIES:
        print_warning(
            f"Chapter is {word_count} words, below minimum of {min_words}. "
            f"Expanding... (retry {retries + 1}/{MAX_WORD_COUNT_RETRIES})"
        )

        continuation_prompt = (
            f"The chapter is {word_count} words, below the minimum of {min_words}. "
            f"Continue and expand the chapter, picking up from where it ended. "
            f"Add more scene detail, interiority, and dialogue. Do not repeat content already written."
        )

        continuation = ""
        for chunk in client.stream(
            stage="chapter_writer",
            system="You are a professional fiction author. Continue the chapter.",
            user_message=continuation_prompt,
            project_config=project.config,
        ):
            continuation += chunk

        chapter_content += "\n\n" + continuation
        word_count = count_words(chapter_content)

        console.print(f"[cyan]New word count: {word_count}[/cyan]")
        retries += 1

    if word_count < min_words:
        print_warning(
            f"Chapter still below minimum ({word_count}/{min_words}). "
            "Consider manual expansion."
        )

    draft_path = f"chapters/chapter_{chapter_num}_draft.md"
    project.write_file(draft_path, chapter_content)

    return chapter_content
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
