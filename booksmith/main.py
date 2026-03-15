import json
import shutil
from pathlib import Path
from typing import Optional

import typer

from .api_client import APIClient, DEFAULT_MIN_WORDS
from .storage.project import Project, find_project, list_projects
from .ui.console import (
    console,
    print_header,
    print_success,
    print_error,
    print_panel,
    print_markdown,
    ask_approval,
    ask_chapter_approval,
    ask_choice,
    confirm,
    edit_in_editor,
    display_project_status,
    count_words,
    stream_to_panel,
    display_diff,
)
from .pipeline import (
    story_bible,
    world_builder,
    characters,
    chapter_outliner,
    chapter_writer,
    reviewer,
)

app = typer.Typer(help="Booksmith - AI-Assisted Book Writing Pipeline")

# Global yolo mode flag
yolo_mode = False


@app.callback()
def callback(
    ctx: typer.Context,
    yolo: bool = typer.Option(
        False, "--yolo", help="Auto-approve but always regenerate after AI review"
    ),
):
    """Global options for Booksmith."""
    global yolo_mode
    yolo_mode = yolo
    if yolo:
        console.print(
            "[yellow]YOLO mode enabled - will auto-approve and regenerate after AI review[/yellow]"
        )


def get_projects_dir() -> Path:
    """Get the projects directory."""
    return Path.cwd() / "projects"


@app.command()
def new(
    name: str = typer.Argument(..., help="Project name"),
    seed: Path = typer.Option(..., "--seed", "-s", help="Path to seed file"),
    min_words: int = typer.Option(
        DEFAULT_MIN_WORDS, "--min-words", help="Minimum words per chapter"
    ),
    pov: str = typer.Option("third person limited", "--pov", help="Point of view"),
    tense: str = typer.Option("past", "--tense", help="Tense"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing project"),
):
    """Start a new book project."""
    projects_dir = get_projects_dir()
    project_path = projects_dir / name

    if project_path.exists():
        if force:
            import shutil

            shutil.rmtree(project_path)
        elif not confirm(f"Project '{name}' already exists. Overwrite?"):
            print_error("Aborted.")
            return

    if not seed.exists():
        print_error(f"Seed file not found: {seed}")
        return

    print_header(f"Creating new project: {name}")

    project = Project.create(name, seed, projects_dir)

    config = project.load_config()
    config["min_words_per_chapter"] = min_words
    config["pov"] = pov
    config["tense"] = tense
    project.save_config(config)

    print_success(f"Project created: {project_path}")
    display_project_status(project)

    client = APIClient()

    if confirm("Start the writing pipeline?", default=True):
        run_story_bible_phase(project, client)


@app.command()
def resume(
    name: str = typer.Argument(..., help="Project name"),
):
    """Resume working on a project."""
    try:
        project = find_project(name, get_projects_dir())
    except FileNotFoundError:
        print_error(f"Project not found: {name}")
        return

    client = APIClient()

    display_project_status(project)

    status = project.status

    if project.current_chapter > 0:
        next_chapter = project.current_chapter + 1
        if next_chapter <= project.total_chapters:
            run_chapter_loop(project, client, next_chapter)
        else:
            print_success("All chapters complete!")
    elif project.file_exists("story_bible.md"):
        print_success("Resuming from where we left off.")
        run_world_phase(project, client)
    else:
        run_story_bible_phase(project, client)


def run_story_bible_phase(
    project: Project, client: APIClient, force_regenerate: bool = False
):
    """Run story bible generation phase."""
    print_header("Stage 1: Story Bible")

    if not force_regenerate and project.file_exists("story_bible.md"):
        print("Using existing Story Bible.")
    else:
        story_bible.generate_story_bible(project, client)

    print_markdown(
        project.read_file("story_bible.md"),
        title="Story Bible",
        border_style="green",
    )

    choice = ask_choice(
        "Story Bible",
        ["A", "R", "F", "E"],
    )

    if choice == "A":
        print_success("Story Bible approved.")
        run_world_phase(project, client)
    elif choice == "R":
        story_bible.regenerate_story_bible(project, client)
        run_story_bible_phase(project, client)
    elif choice == "F":
        feedback = console.input("What would you like to change? ").strip()
        story_bible.regenerate_story_bible(project, client, feedback)
        run_story_bible_phase(project, client)
    elif choice == "E":
        edit_in_editor(str(project.path / "story_bible.md"))
        run_world_phase(project, client)


def run_world_phase(
    project: Project, client: APIClient, force_regenerate: bool = False
):
    """Run world building phase."""
    print_header("Stage 2: World Building")

    if not force_regenerate and project.file_exists("world.md"):
        print("Using existing World Guide.")
    else:
        world_builder.generate_world(project, client)

    print_markdown(
        project.read_file("world.md"),
        title="World Guide",
        border_style="green",
    )

    choice = ask_choice(
        "World Guide",
        ["A", "R", "F", "E"],
    )

    if choice == "A":
        print_success("World guide approved.")
        run_characters_phase(project, client)
    elif choice == "R":
        world_builder.generate_world(project, client)
        run_world_phase(project, client)
    elif choice == "F":
        feedback = console.input("What would you like to change? ").strip()
        world_builder.generate_world(project, client, feedback)
        run_world_phase(project, client)
    elif choice == "E":
        edit_in_editor(str(project.path / "world.md"))
        run_characters_phase(project, client)


def run_characters_phase(
    project: Project, client: APIClient, force_regenerate: bool = False
):
    """Run character profiles phase."""
    print_header("Stage 3: Characters")

    # Check if character list file exists (saved after generation)
    character_list = None
    if project.file_exists("characters/character_list.md"):
        try:
            import json

            content = project.read_file("characters/character_list.md")
            import re

            json_match = re.search(r"```json\n([\s\S]*?)\n```", content)
            if json_match:
                character_list = json.loads(json_match.group(1))
            else:
                json_match = re.search(r"\[[\s\S]*\]", content)
                if json_match:
                    character_list = json.loads(json_match.group())
        except Exception:
            pass

    # Check if full profile files exist
    chars_dir = project.path / "characters"
    existing_profile_files = list(chars_dir.glob("*.md")) if chars_dir.exists() else []
    has_full_profiles = len(existing_profile_files) > 0

    chars = project.get_characters()

    # Use character_list if chars is empty
    if not chars and character_list:
        chars = character_list

    if not force_regenerate and has_full_profiles:
        print(f"Using existing {len(existing_profile_files)} character profiles.")
        run_chapters_phase(project, client)
        return

    if not force_regenerate and chars:
        print(f"Characters already exist. Run chapters phase.")
        run_chapters_phase(project, client)
        return

    character_list = characters.generate_character_list(project, client)

    _show_and_review_characters(project, client, character_list, run_chapters_phase)


def _show_and_review_characters(project, client, character_list, next_phase):
    """Show characters and allow feedback/regeneration."""
    if not character_list:
        print_error("No characters generated. Please try again.")
        character_list = characters.generate_character_list(project, client)
        _show_and_review_characters(project, client, character_list, next_phase)
        return

    # First show the character list for approval before generating full profiles
    console.print("\n[cyan]Character List:[/cyan]")
    for char in character_list:
        console.print(f"  - {char['name']}: {char.get('description', '')}")

    choice = ask_choice(
        "Character List",
        ["A", "R", "F", "E"],
    )

    if choice == "A":
        # Now generate full profiles after approval
        console.print("\n[cyan]Generating character profiles...[/cyan]")
        for char_info in character_list:
            characters.generate_character_profile(
                project, client, char_info, character_list
            )
            console.print(f"  Generated: {char_info['name']}")

        # Then show profiles for review
        console.print("\n[cyan]Character Profiles:[/cyan]")
        for char_info in character_list:
            char_file = f"characters/{char_info['name'].replace(' ', '_')}.md"
            if project.file_exists(char_file):
                profile = project.read_file(char_file)
                print_panel(
                    profile[:1000] + "..." if len(profile) > 1000 else profile,
                    title=char_info["name"],
                    border_style="green",
                )

        print_success(f"Generated {len(character_list)} character profiles.")
        next_phase(project, client)
    elif choice == "R":
        character_list = characters.generate_character_list(project, client)
        _show_and_review_characters(project, client, character_list, next_phase)
    elif choice == "F":
        feedback = console.input("What would you like to change? ").strip()
        prompt = f"""## Previous Character List

{json.dumps(character_list, indent=2)}

## Feedback

{feedback}

---

Regenerate the character list incorporating this feedback.
"""
        new_list = ""
        for chunk in client.stream(
            stage="characters",
            system="You are a character development expert.",
            user_message=prompt,
            project_config=project.config,
        ):
            new_list += chunk

        try:
            character_list = json.loads(new_list)
        except json.JSONDecodeError:
            character_list = characters.parse_character_list(new_list)

        _show_and_review_characters(project, client, character_list, next_phase)
    elif choice == "E":
        # Generate profiles so they can be edited
        for char_info in character_list:
            characters.generate_character_profile(
                project, client, char_info, character_list
            )
        edit_in_editor(str(project.path / "characters" / "character_index.json"))
        next_phase(project, client)


def run_chapters_phase(
    project: Project, client: APIClient, force_regenerate: bool = False
):
    """Run chapter outlines phase."""
    print_header("Stage 4: Chapter Outlines")

    # Check if chapter list already exists
    chapter_list_path = project.path / "chapter_outlines" / "chapter_list.md"
    existing_chapters = None

    if chapter_list_path.exists() and not force_regenerate:
        try:
            content = chapter_list_path.read_text()
            if content.strip():
                existing_chapters = chapter_outliner.parse_chapter_list(content)
                if existing_chapters:
                    print(
                        f"Using existing chapter list ({len(existing_chapters)} chapters)."
                    )
                    first_chapter = 1
                    review_chapter_outlines(
                        project, client, existing_chapters, first_chapter
                    )
                    return
        except Exception as e:
            print(f"Error loading existing chapter list: {e}")

    chapters = chapter_outliner.generate_chapter_list(project, client)

    if not chapters:
        print_error(
            "Failed to generate chapter list. Please check the output and try again."
        )
        return

    # Warn if chapter count doesn't match story bible
    expected = project.total_chapters
    if len(chapters) != expected:
        print_error(
            f"Warning: Story bible specifies {expected} chapters but got {len(chapters)}. "
            f"Please regenerate with feedback to adjust."
        )

    first_chapter = 1
    review_chapter_outlines(project, client, chapters, first_chapter)


def review_chapter_outlines(
    project: Project, client: APIClient, chapters: list, chapter_num: int
):
    """Review individual chapter outlines one at a time."""
    if chapter_num > len(chapters):
        print_success(f"Reviewed all {len(chapters)} chapter outlines.")
        first_chapter = 1
        run_chapter_loop(project, client, first_chapter)
        return

    chapter = chapters[chapter_num - 1]
    outline_path = project.path / "chapter_outlines" / f"chapter_{chapter['number']}.md"

    # Generate outline if it doesn't exist
    if not outline_path.exists():
        chapter_outliner.generate_chapter_outline(project, client, chapter, chapters)

    if outline_path.exists():
        outline_content = outline_path.read_text()
        print_markdown(
            outline_content,
            title=f"Chapter {chapter['number']}: {chapter['title']}",
            border_style="green",
        )

    # In yolo mode, auto-approve
    if yolo_mode:
        choice = "A"
        console.print("[yellow]YOLO: Auto-approving outline...[/yellow]")
    else:
        choice = ask_choice(
            f"Chapter {chapter['number']} Outline",
            ["A", "R", "F", "E", "S"],
        )

    if choice == "A":
        print_success(f"Chapter {chapter['number']} outline approved.")
        # AI review step
        review_text, score = reviewer.generate_outline_review(
            project, client, chapter["number"]
        )

        print_panel(
            review_text,
            title=f"AI Outline Review (Score: {score}/10)",
            border_style="yellow",
        )

        # In yolo mode, regenerate with AI feedback then continue
        if yolo_mode:
            console.print("[yellow]YOLO: Regenerating with AI feedback...[/yellow]")
            chapter_outliner.regenerate_chapter_outline(
                project, client, chapter["number"], feedback=review_text
            )
            review_chapter_outlines(project, client, chapters, chapter_num + 1)
        else:
            review_choice = ask_choice(
                f"AI Review for Chapter {chapter['number']}",
                ["C", "R"],
            )

            if review_choice == "R":
                # Regenerate outline with AI feedback
                chapter_outliner.regenerate_chapter_outline(
                    project, client, chapter["number"], feedback=review_text
                )
                review_chapter_outlines(project, client, chapters, chapter_num)
            else:
                # Continue without changes
                review_chapter_outlines(project, client, chapters, chapter_num + 1)
    elif choice == "R":
        chapter_outliner.regenerate_chapter_outline(project, client, chapter["number"])
        review_chapter_outlines(project, client, chapters, chapter_num)
    elif choice == "F":
        feedback = console.input("What would you like to change? ").strip()
        chapter_outliner.regenerate_chapter_outline(
            project, client, chapter["number"], feedback
        )
        review_chapter_outlines(project, client, chapters, chapter_num)
    elif choice == "E":
        edit_in_editor(str(outline_path))
        review_chapter_outlines(project, client, chapters, chapter_num)
    elif choice == "S":
        review_chapter_outlines(project, client, chapters, chapter_num + 1)


def run_chapter_loop(project: Project, client: APIClient, chapter_num: int):
    """Run the chapter writing loop for a specific chapter."""
    if chapter_num > project.total_chapters:
        print_success("All chapters complete!")
        return

    print_header(f"Chapter {chapter_num}")

    chapter_content = chapter_writer.generate_chapter(project, client, chapter_num)
    word_count = count_words(chapter_content)

    review_text, score = reviewer.generate_review(project, client, chapter_num)

    print_panel(
        review_text, title=f"AI Review (Score: {score}/10)", border_style="yellow"
    )

    if score < 7:
        print_error(f"Low score! Consider regenerating before approving.")

    console.print(f"\n[cyan]Word count: {word_count}[/cyan]")
    if word_count >= project.config.get("min_words_per_chapter", 2000):
        print_success("Meets minimum word count.")
    else:
        print_error("Below minimum word count.")

    # In yolo mode, regenerate with AI feedback instead of auto-approving
    if yolo_mode:
        console.print("[yellow]YOLO: Regenerating with AI feedback...[/yellow]")
        chapter_writer.regenerate_chapter(
            project, client, chapter_num, feedback=review_text
        )
        run_chapter_loop(project, client, chapter_num)
    else:
        choice = ask_chapter_approval("Chapter")

        if choice == "A":
            approve_chapter(project, client, chapter_num)
        elif choice == "R":
            chapter_writer.regenerate_chapter(project, client, chapter_num)
            run_chapter_loop(project, client, chapter_num)
        elif choice == "F":
            feedback = console.input("Enter feedback: ").strip()
            chapter_writer.regenerate_chapter(project, client, chapter_num, feedback)
            run_chapter_loop(project, client, chapter_num)
        elif choice == "E":
            edit_in_editor(
                str(project.path / "chapters" / f"chapter_{chapter_num}_draft.md")
            )
            approve_chapter(project, client, chapter_num)
        elif choice == "S":
            print(f"Skipping chapter {chapter_num}...")
            run_chapter_loop(project, client, chapter_num + 1)


def update_macro_summary(project: Project, client: APIClient, chapter_num: int):
    """Update macro summary after chapter approval."""
    print_header("Updating Macro Summary...")

    try:
        current_summary = project.get_macro_summary()
    except FileNotFoundError:
        current_summary = None

    chapter_content = project.get_approved_chapter(chapter_num)

    if current_summary:
        prompt = f"""## Current Macro Summary

{current_summary}

## New Chapter ({chapter_num})

{chapter_content}

---

Update the macro summary to incorporate this new chapter. Keep it to around 300 words per chapter worth of content. Preserve key plot decisions, character state changes, deaths or departures, world revelations, and unresolved threads.
"""
    else:
        prompt = f"""## New Chapter ({chapter_num})

{chapter_content}

---

Create a macro summary of this first chapter. Keep it to around 300 words. Include key plot decisions, character introductions, and any important setup for future chapters.
"""

    summary = ""
    for chunk in client.stream(
        stage="macro_summary",
        system="You are a story summarizer. Create concise, informative summaries.",
        user_message=prompt,
        project_config=project.config,
    ):
        summary += chunk

    project.write_file("summaries/macro_summary.md", summary)
    print_success("Macro summary updated.")


def approve_chapter(project: Project, client: APIClient, chapter_num: int):
    """Approve a chapter and move it to final."""
    draft_path = project.path / "chapters" / f"chapter_{chapter_num}_draft.md"
    final_path = project.path / "chapters" / f"chapter_{chapter_num}.md"

    if draft_path.exists():
        shutil.move(str(draft_path), str(final_path))

    project.update_chapter_status(chapter_num, approved=True)
    project.set_status("writing")

    update_macro_summary(project, client, chapter_num)

    print_success(f"Chapter {chapter_num} approved!")

    next_chapter = chapter_num + 1

    if next_chapter <= project.total_chapters:
        if confirm(f"Proceed to Chapter {next_chapter}?"):
            run_chapter_loop(project, client, next_chapter)
    else:
        print_success("All chapters complete!")


@app.command()
def status(
    name: str = typer.Argument(..., help="Project name"),
):
    """Show project status."""
    try:
        project = find_project(name, get_projects_dir())
    except FileNotFoundError:
        print_error(f"Project not found: {name}")
        return

    display_project_status(project)


@app.command()
def chapter(
    name: str = typer.Argument(..., help="Project name"),
    n: int = typer.Option(..., "--n", help="Chapter number"),
):
    """Jump to a specific chapter."""
    try:
        project = find_project(name, get_projects_dir())
    except FileNotFoundError:
        print_error(f"Project not found: {name}")
        return

    if n < 1 or n > project.total_chapters:
        print_error(f"Invalid chapter number. Valid range: 1-{project.total_chapters}")
        return

    client = APIClient()
    run_chapter_loop(project, client, n)


@app.command()
def export(
    name: str = typer.Argument(..., help="Project name"),
    format: str = typer.Option("md", "--format", help="Export format (md)"),
):
    """Export the full manuscript."""
    try:
        project = find_project(name, get_projects_dir())
    except FileNotFoundError:
        print_error(f"Project not found: {name}")
        return

    approved = project.approved_chapters
    if not approved:
        print_error("No approved chapters to export.")
        return

    manuscript = f"# {project.title}\n\n"

    total_words = 0

    for ch in sorted(approved):
        chapter_text = project.get_approved_chapter(ch)
        if not chapter_text:
            continue
        words = count_words(chapter_text)
        total_words += words

        manuscript += f"## Chapter {ch}\n\n"
        manuscript += chapter_text
        manuscript += f"\n\n---\n\n*Chapter {ch}: {words} words*\n\n"

    manuscript += f"---\n\n**Total: {total_words} words**\n"

    output_path = project.path / f"{name}_manuscript.md"
    output_path.write_text(manuscript)

    print_success(f"Manuscript exported to: {output_path}")
    console.print(f"[cyan]Total word count: {total_words}[/cyan]")


if __name__ == "__main__":
    app()
