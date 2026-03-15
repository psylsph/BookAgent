from pathlib import Path
import re
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


def parse_scenes_from_outline(outline: str) -> list[str]:
    """Parse scene breakdown from outline."""
    scenes = []
    in_scenes = False
    current_scene = []

    for line in outline.split("\n"):
        if "Scene Breakdown" in line or "scene breakdown" in line:
            in_scenes = True
            continue
        if in_scenes:
            # Check for numbered scene (1., 2., etc.)
            if re.match(r"^\d+\.\s+", line) or re.match(r"^-\s+", line):
                if current_scene:
                    scenes.append("\n".join(current_scene))
                current_scene = [line]
            elif line.strip() == "" or line.startswith("**"):
                if current_scene:
                    scenes.append("\n".join(current_scene))
                    current_scene = []
            elif current_scene:
                current_scene.append(line)

    if current_scene:
        scenes.append("\n".join(current_scene))

    return scenes


def write_scene(
    client: APIClient,
    scene_description: str,
    context: dict,
    previous_scene_content: str = "",
) -> str:
    """Write a single scene."""
    prompt = f"""## Scene Description

{scene_description}

## Story Context

{context["chapter_outline"]}

## Previous Scene (for continuity)

{previous_scene_content}

## Instructions

Write this scene in vivid prose. Continue directly from where the previous scene left off. Include dialogue, sensory details, and character interiority.
"""

    scene_content = ""
    for chunk in client.stream(
        stage="chapter_writer",
        system="You are a professional fiction author. Output ONLY the story scene, no thinking.",
        user_message=prompt,
        project_config=context.get("project_config", {}),
    ):
        scene_content += chunk

    return scene_content


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
    """Generate a chapter by writing scenes one at a time."""
    print_header(f"Generating Chapter {chapter_num}...")

    chapter_outline = project.get_chapter_outline(chapter_num)
    if not chapter_outline:
        raise ValueError(f"No outline found for chapter {chapter_num}")

    context = build_chapter_context(project, chapter_num, chapter_outline)
    context["project_config"] = project.config

    # Parse scenes from outline
    scenes = parse_scenes_from_outline(chapter_outline)

    if not scenes:
        # Fallback to single scene if no breakdown found
        scenes = [chapter_outline]

    console.print(f"[cyan]Writing {len(scenes)} scenes...[/cyan]")

    # Write each scene
    chapter_content = ""
    previous_scene = ""

    for i, scene in enumerate(scenes):
        console.print(f"[cyan]Writing scene {i + 1}/{len(scenes)}...[/cyan]")
        scene_content = write_scene(client, scene, context, previous_scene)
        chapter_content += scene_content + "\n\n"
        previous_scene = (
            scene_content[-500:] if len(scene_content) > 500 else scene_content
        )

    # Get word count and expand if needed
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
            f"Continue and expand the chapter. Add more detail, dialogue, and interiority."
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


def regenerate_chapter(
    project: Project,
    client: APIClient,
    chapter_num: int,
    feedback: Optional[str] = None,
) -> str:
    """Regenerate a chapter with optional feedback."""
    return generate_chapter(project, client, chapter_num, feedback)
