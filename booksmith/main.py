import json
import shutil
from pathlib import Path
from typing import Optional

import typer

from .api_client import APIClient, DEFAULT_MIN_WORDS
from .export import epub as epub_exporter
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

_yolo_mode = False


def get_yolo_mode() -> bool:
    """Get current yolo mode state."""
    return _yolo_mode


@app.callback()
def callback(
    ctx: typer.Context,
    yolo: bool = typer.Option(
        False, "--yolo", help="Auto-approve but always regenerate after AI review"
    ),
):
    """Global options for Booksmith."""
    global _yolo_mode
    _yolo_mode = yolo
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

    # Update total_chapters_planned from chapter_list.md if it's 0
    if project.total_chapters == 0:
        chapter_list_path = project.path / "chapter_outlines" / "chapter_list.md"
        if chapter_list_path.exists():
            try:
                content = chapter_list_path.read_text()
                chapters = chapter_outliner.parse_chapter_list(content)
                if chapters:
                    project.set_total_chapters(len(chapters))
                    console.print(
                        f"[dim]Updated total_chapters_planned to {len(chapters)} from chapter list[/dim]"
                    )
            except Exception:
                pass

    display_project_status(project)

    # Check which stages are complete and skip to the right place
    if (
        project.current_chapter > 0
        and project.current_chapter <= project.total_chapters
    ):
        next_chapter = project.current_chapter + 1
        if next_chapter <= project.total_chapters:
            console.print(f"[green]Skipping to Chapter {next_chapter}...[/green]")
            run_chapter_loop(project, client, next_chapter)
        else:
            print_success("All chapters complete!")
    elif project.file_exists("chapters") and any(
        Path(project.path / "chapters").glob("chapter_*.md")
    ):
        # Check if there are approved chapters
        approved = project.approved_chapters
        if approved:
            next_chapter = max(approved) + 1
            if next_chapter <= project.total_chapters:
                console.print(f"[green]Skipping to Chapter {next_chapter}...[/green]")
                run_chapter_loop(project, client, next_chapter)
            else:
                print_success("All chapters complete!")
        else:
            # No approved chapters yet, start chapter writing
            run_chapters_phase(project, client)
        return
    # Check for existing chapter outlines to resume from the right chapter
    outlines_dir = project.path / "chapter_outlines"
    chapter_list_path = project.path / "chapter_outlines" / "chapter_list.md"

    if chapter_list_path.exists():
        try:
            content = chapter_list_path.read_text()
            chapters = chapter_outliner.parse_chapter_list(content)
            if chapters:
                # Find the next chapter that needs outline review
                approved_outlines = project.approved_outlines
                next_chapter = 1
                for ch in chapters:
                    if ch["number"] not in approved_outlines:
                        next_chapter = ch["number"]
                        break
                else:
                    # All outlines approved
                    next_chapter = len(chapters) + 1

                # Count only approved chapters that exist in the chapter list
                approved_count = sum(
                    1 for ch in chapters if ch["number"] in approved_outlines
                )

                if next_chapter <= len(chapters):
                    # Show which chapters are approved for debugging
                    sorted_approved = sorted(
                        [c for c in approved_outlines if c <= len(chapters)]
                    )
                    console.print(
                        f"[green]Resuming outline review from Chapter {next_chapter} "
                        f"({approved_count}/{len(chapters)} approved)...[/green]"
                    )
                    console.print(f"[dim]Approved chapters: {sorted_approved}[/dim]")

                if next_chapter <= len(chapters):
                    console.print(
                        f"[green]Resuming outline review from Chapter {next_chapter} "
                        f"({approved_count}/{len(chapters)} approved)...[/green]"
                    )
                    review_chapter_outlines(project, client, chapters, next_chapter)
                    return
                else:
                    console.print("[green]All chapter outlines complete![/green]")
                    run_chapter_loop(project, client, 1)
                    return
        except Exception as e:
            console.print(
                f"[yellow]Warning: Could not parse chapter list: {e}[/yellow]"
            )

    # Fallback: check for existing outline files
    if outlines_dir.exists():
        existing_outlines = sorted(
            [
                int(f.stem.split("_")[1])
                for f in outlines_dir.glob("chapter_*.md")
                if f.stem.split("_")[1].isdigit()
            ],
            reverse=True,
        )
        if existing_outlines:
            last_outline = existing_outlines[0]
            next_chapter = last_outline + 1
            console.print(
                f"[yellow]Found {len(existing_outlines)} outline files (approval status unknown). "
                f"Starting review from Chapter {next_chapter}...[/yellow]"
            )
            # Load chapter list for review_chapter_outlines
            if chapter_list_path.exists():
                try:
                    content = chapter_list_path.read_text()
                    chapters = chapter_outliner.parse_chapter_list(content)
                    if next_chapter <= len(chapters):
                        review_chapter_outlines(project, client, chapters, next_chapter)
                        return
                except Exception:
                    pass

            console.print("[green]All chapter outlines complete![/green]")
            run_chapter_loop(project, client, 1)
            return

    if project.file_exists("characters/character_index.json"):
        console.print("[green]Skipping to Chapter Outlines...[/green]")
        run_chapters_phase(project, client)
    elif project.file_exists("world.md"):
        console.print("[green]Skipping to Characters...[/green]")
        run_characters_phase(project, client)
    elif project.file_exists("story_bible.md"):
        console.print("[green]Skipping to World Building...[/green]")
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


def review_chapter_list_and_proceed(
    project: Project, client: APIClient, chapters: list
):
    """Show chapter list and ask for feedback/regeneration."""
    # Display the chapter list
    console.print("\n[cyan]Chapter List:[/cyan]")
    for ch in chapters:
        console.print(f"  {ch['number']}. {ch['title']} - {ch.get('purpose', '')}")

    choice = ask_choice(
        "Chapter List",
        ["A", "R", "F", "E"],
    )

    if choice == "A":
        print_success("Chapter list approved.")
        first_chapter = 1
        review_chapter_outlines(project, client, chapters, first_chapter)
    elif choice == "R":
        chapters = chapter_outliner.generate_chapter_list(project, client)
        if chapters and len(chapters) != project.total_chapters:
            project.set_total_chapters(len(chapters))
        review_chapter_list_and_proceed(project, client, chapters)
    elif choice == "F":
        feedback = console.input("What would you like to change? ").strip()
        chapters = chapter_outliner.generate_chapter_list_with_feedback(
            project, client, feedback
        )
        if chapters and len(chapters) != project.total_chapters:
            project.set_total_chapters(len(chapters))
        review_chapter_list_and_proceed(project, client, chapters)
    elif choice == "E":
        edit_in_editor(str(project.path / "chapter_outlines" / "chapter_list.md"))
        # Reload after editing
        chapter_list_path = project.path / "chapter_outlines" / "chapter_list.md"
        try:
            content = chapter_list_path.read_text()
            chapters = chapter_outliner.parse_chapter_list(content)
        except Exception:
            console.print("[yellow]Could not reload chapter list after edit[/yellow]")
        first_chapter = 1
        review_chapter_outlines(project, client, chapters, first_chapter)


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
                    console.print(
                        f"[green]Using existing chapter list ({len(existing_chapters)} chapters).[/green]"
                    )
                    first_chapter = 1
                    review_chapter_outlines(
                        project, client, existing_chapters, first_chapter
                    )
                    return
        except Exception as e:
            console.print(f"[yellow]Error loading existing chapter list: {e}[/yellow]")
            console.print("[yellow]Will generate a new chapter list.[/yellow]")

    try:
        chapters = chapter_outliner.generate_chapter_list(project, client)
    except Exception as e:
        console.print(f"[red]Error generating chapter list: {e}[/red]")
        console.print(
            "[yellow]This may be due to context overflow. Try using a smaller model or reducing context size.[/yellow]"
        )
        return

    if not chapters:
        print_error(
            "Failed to generate chapter list. Please check the output and try again."
        )
        return

    # Warn if chapter count doesn't match expected
    expected = project.total_chapters
    if len(chapters) != expected:
        console.print(
            f"[yellow]Note: Generated {len(chapters)} chapters (expected {expected}). "
            f"Updating project config to match actual count.[/yellow]"
        )
        project.set_total_chapters(len(chapters))

    review_chapter_list_and_proceed(project, client, chapters)


def review_chapter_outlines(
    project: Project, client: APIClient, chapters: list, chapter_num: int
):
    """Review individual chapter outlines one at a time."""
    if chapter_num > len(chapters):
        print_success(f"Reviewed all {len(chapters)} chapter outlines.")
        first_chapter = 1
        run_chapter_loop(project, client, first_chapter)
        return

    # Skip if outline was already approved
    if chapter_num in project.approved_outlines:
        console.print(
            f"[dim]Chapter {chapter_num} outline already approved. Skipping...[/dim]"
        )
        review_chapter_outlines(project, client, chapters, chapter_num + 1)
        return

    chapter = chapters[chapter_num - 1]
    outline_path = project.path / "chapter_outlines" / f"chapter_{chapter['number']}.md"

    console.print(
        f"[dim]Checking outline for chapter {chapter['number']}: {outline_path.exists()}[/dim]"
    )

    # Check if outline exists but wasn't approved (was likely regenerated)
    if outline_path.exists() and chapter["number"] not in project.approved_outlines:
        console.print(
            f"[yellow]Note: Chapter {chapter['number']} outline exists but is not approved. "
            f"It may have been regenerated and needs re-approval.[/yellow]"
        )

    # Generate outline if it doesn't exist
    if not outline_path.exists():
        console.print(
            f"[yellow]Generating missing outline for chapter {chapter['number']}...[/yellow]"
        )
        chapter_outliner.generate_chapter_outline(project, client, chapter, chapters)
    else:
        console.print(
            f"[dim]Using existing outline for chapter {chapter['number']}[/dim]"
        )

    if outline_path.exists():
        outline_content = outline_path.read_text()
        print_markdown(
            outline_content,
            title=f"Chapter {chapter['number']}: {chapter['title']}",
            border_style="green",
        )

    # In yolo mode, auto-approve
    if get_yolo_mode():
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
        if get_yolo_mode():
            console.print(
                "[yellow]YOLO: Regenerating outline with AI feedback...[/yellow]"
            )
            chapter_outliner.regenerate_chapter_outline(
                project,
                client,
                chapter["number"],
                feedback=review_text,
            )
            # Mark as approved after regeneration in YOLO mode
            project.update_outline_status(chapter["number"], approved=True)
            console.print("[yellow]YOLO: Auto-continuing to next chapter...[/yellow]")
            review_chapter_outlines(project, client, chapters, chapter_num + 1)
        else:
            review_choice = ask_choice(
                f"AI Review for Chapter {chapter['number']}",
                ["C", "R"],
            )

            if review_choice == "R":
                # Regenerate outline with AI feedback
                console.print(f"[cyan]Regenerating outline with AI feedback...[/cyan]")
                new_outline = chapter_outliner.regenerate_chapter_outline(
                    project,
                    client,
                    chapter["number"],
                    feedback=review_text,
                )
                # Mark as not approved since we're regenerating
                project.update_outline_status(chapter["number"], approved=False)
                console.print(
                    f"[green]✓ Outline regenerated. Re-displaying for review...[/green]"
                )
                review_chapter_outlines(project, client, chapters, chapter_num)
            else:
                # Continue without changes - mark as approved
                project.update_outline_status(chapter["number"], approved=True)
                review_chapter_outlines(project, client, chapters, chapter_num + 1)
    elif choice == "R":
        chapter_outliner.regenerate_chapter_outline(project, client, chapter["number"])
        # Mark as not approved since we're regenerating
        project.update_outline_status(chapter["number"], approved=False)
        review_chapter_outlines(project, client, chapters, chapter_num)
    elif choice == "F":
        feedback = console.input("What would you like to change? ").strip()
        chapter_outliner.regenerate_chapter_outline(
            project, client, chapter["number"], feedback
        )
        # Mark as not approved since we're regenerating
        project.update_outline_status(chapter["number"], approved=False)
        review_chapter_outlines(project, client, chapters, chapter_num)
    elif choice == "E":
        edit_in_editor(str(outline_path))
        # Mark as approved after edit
        project.update_outline_status(chapter["number"], approved=True)
        review_chapter_outlines(project, client, chapters, chapter_num)
    elif choice == "S":
        review_chapter_outlines(project, client, chapters, chapter_num + 1)


def run_chapter_loop(project: Project, client: APIClient, chapter_num: int):
    """Run the chapter writing loop for a specific chapter."""
    if chapter_num > project.total_chapters:
        print_success("All chapters complete!")
        return

    print_header(f"Chapter {chapter_num}")

    # Check if outline exists, generate if missing
    chapter_outline = project.get_chapter_outline(chapter_num)
    if not chapter_outline:
        console.print(
            f"[yellow]No outline found for Chapter {chapter_num}. Generating...[/yellow]"
        )
        # Load chapter list to get chapter info
        chapter_list_path = project.path / "chapter_outlines" / "chapter_list.md"
        if chapter_list_path.exists():
            try:
                content = chapter_list_path.read_text()
                chapters = chapter_outliner.parse_chapter_list(content)
                chapter_info = None
                for ch in chapters:
                    if ch["number"] == chapter_num:
                        chapter_info = ch
                        break
                if chapter_info:
                    chapter_outliner.generate_chapter_outline(
                        project, client, chapter_info, chapters
                    )
                    console.print(
                        f"[green]Generated outline for Chapter {chapter_num}[/green]"
                    )
                else:
                    print_error(f"Chapter {chapter_num} not found in chapter list")
                    return
            except Exception as e:
                print_error(f"Failed to generate outline: {e}")
                return
        else:
            print_error(
                "No chapter list found. Please generate chapter outlines first."
            )
            return

    # Three-pass generation: generate → review → regenerate → review → regenerate → approve
    review_text = None
    score = None
    previous_score = None

    for pass_num in range(1, 6):
        print_header(f"Chapter {chapter_num} — Pass {pass_num}/5")

        if pass_num == 1:
            chapter_content = chapter_writer.generate_chapter(
                project, client, chapter_num
            )
        else:
            chapter_content = chapter_writer.regenerate_chapter(
                project, client, chapter_num, review_text
            )

        word_count = count_words(chapter_content)

        review_text, score = reviewer.generate_review(project, client, chapter_num)

        # Append code-based word count to review feedback
        min_words = project.config.get("min_words_per_chapter", 1500)
        word_count_note = (
            f"\n\n**Word Count:** {word_count} words (target: {min_words})"
        )
        if word_count < min_words:
            word_count_note += " — BELOW TARGET"
        review_text += word_count_note

        print_panel(
            review_text,
            title=f"AI Review Pass {pass_num}/5 (Score: {score}/10)",
            border_style="yellow",
        )

        console.print(f"\n[cyan]Word count: {word_count}[/cyan]")

        # Detect repetition loop: if score hasn't improved after 3 passes, stop regenerating
        if previous_score is not None and pass_num >= 3:
            if abs(score - previous_score) < 0.5:  # Score hasn't changed significantly
                console.print(
                    f"[yellow]Score stabilized at {score}/10. Stopping regeneration early.[/yellow]"
                )
                break
        if pass_num >= 3:
            previous_score = score

        if pass_num < 5:
            if get_yolo_mode():
                console.print(
                    f"[yellow]YOLO: Auto-regenerating for pass {pass_num + 1}...[/yellow]"
                )
            else:
                choice = ask_choice(
                    f"Pass {pass_num} complete — Score: {score}/10",
                    ["C", "R", "F", "E", "S"],
                )

                if choice == "R":
                    console.print("[cyan]Regenerating with AI feedback...[/cyan]")
                    # review_text already contains the feedback
                    continue
                elif choice == "F":
                    extra_feedback = console.input(
                        "Enter additional feedback: "
                    ).strip()
                    review_text = (
                        f"## AI Review Feedback\n{review_text}\n\n"
                        f"## Additional User Feedback\n{extra_feedback}"
                    )
                    continue
                elif choice == "E":
                    draft_path = (
                        project.path / "chapters" / f"chapter_{chapter_num}_draft.md"
                    )
                    edit_in_editor(str(draft_path))
                    console.print("[green]Edited. Continuing to next pass...[/green]")
                    continue
                elif choice == "S":
                    print(f"Skipping chapter {chapter_num}...")
                    run_chapter_loop(project, client, chapter_num + 1)
                    return
                # "C" continues to next pass

    # After 5 passes, approve
    if get_yolo_mode():
        console.print("[yellow]YOLO: Auto-approving chapter after 5 passes...[/yellow]")
    else:
        console.print(
            f"[green]Chapter {chapter_num} complete after 5 passes. "
            f"Final score: {score}/10[/green]"
        )

    approve_chapter(project, client, chapter_num)


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
            # User chose not to proceed - offer to regenerate current chapter
            console.print(
                f"[yellow]Chapter {chapter_num} is approved. Options:[/yellow]"
            )
            console.print("[R]egenerate this chapter anyway (with latest AI feedback)")
            console.print("[E]xit to menu")
            choice = console.input("Choose an option: ").strip().upper()

            if choice == "R":
                console.print(
                    f"[cyan]Regenerating Chapter {chapter_num} with AI feedback...[/cyan]"
                )
                # Get the latest AI review
                review_text, score = reviewer.generate_review(
                    project, client, chapter_num
                )
                print_panel(
                    review_text,
                    title=f"AI Review (Score: {score}/10)",
                    border_style="yellow",
                )
                # Delete the approved version and regenerate with feedback
                final_path = project.path / "chapters" / f"chapter_{chapter_num}.md"
                if final_path.exists():
                    final_path.unlink()
                # Remove from approved list
                config = project.load_config()
                approved = config.get("approved_chapters", [])
                if chapter_num in approved:
                    config["approved_chapters"] = [
                        c for c in approved if c != chapter_num
                    ]
                    project.save_config(config)
                # Regenerate with AI feedback
                chapter_writer.regenerate_chapter(
                    project, client, chapter_num, review_text
                )
                run_chapter_loop(project, client, chapter_num)
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
    format: str = typer.Option("md", "--format", help="Export format (md, epub)"),
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

    if format == "epub":
        print_header("Exporting to EPUB...")
        output_path = epub_exporter.create_epub(project)
        print_success(f"EPUB exported to: {output_path}")
        return

    # Default: markdown export
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


@app.command()
def normalize_outlines(
    name: str = typer.Argument(..., help="Project name"),
):
    """Normalize all chapter outlines to consistent format."""
    try:
        project = find_project(name, get_projects_dir())
    except FileNotFoundError:
        print_error(f"Project not found: {name}")
        return

    outlines_dir = project.path / "chapter_outlines"
    if not outlines_dir.exists():
        print_error("No chapter_outlines directory found.")
        return

    # Load chapter list for titles
    chapter_list_path = outlines_dir / "chapter_list.md"
    chapters = []
    if chapter_list_path.exists():
        try:
            content = chapter_list_path.read_text()
            chapters = chapter_outliner.parse_chapter_list(content)
        except Exception as e:
            console.print(
                f"[yellow]Warning: Could not parse chapter list: {e}[/yellow]"
            )

    # Find all chapter outline files
    outline_files = sorted(
        outlines_dir.glob("chapter_[0-9]*.md"),
        key=lambda f: (
            int(f.stem.split("_")[1]) if f.stem.split("_")[1].isdigit() else 0
        ),
    )

    if not outline_files:
        print_error("No chapter outline files found.")
        return

    print_header(f"Normalizing {len(outline_files)} chapter outlines...")

    normalized_count = 0
    for outline_file in outline_files:
        try:
            # Extract chapter number
            num_str = outline_file.stem.split("_")[1]
            if not num_str.isdigit():
                continue
            chapter_num = int(num_str)

            # Find title from chapter list
            title = f"Chapter {chapter_num}"
            for ch in chapters:
                if ch["number"] == chapter_num:
                    title = ch["title"]
                    break

            # Read and normalize
            content = outline_file.read_text()
            normalized = chapter_outliner.normalize_outline_format(
                content, chapter_num, title
            )

            # Write back
            outline_file.write_text(normalized)
            normalized_count += 1

            console.print(f"[green]✓[/green] Normalized chapter {chapter_num}: {title}")
        except Exception as e:
            console.print(
                f"[yellow]Warning: Could not normalize {outline_file.name}: {e}[/yellow]"
            )

    print_success(f"Normalized {normalized_count} chapter outlines")


if __name__ == "__main__":
    app()
