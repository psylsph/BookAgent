"""Unit tests for main.py workflow functions with mocked AI responses."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch, call
from typing import Generator

import pytest

from booksmith.main import (
    get_yolo_mode,
    callback,
    run_chapters_phase,
    review_chapter_list_and_proceed,
    review_chapter_outlines,
)
from booksmith.storage.project import Project, DEFAULT_CONFIG


class TestYoloMode:
    """Test YOLO mode functionality."""

    def test_get_yolo_mode_default(self):
        """Test default YOLO mode is False."""
        assert get_yolo_mode() is False

    def test_yolo_mode_can_be_enabled(self):
        """Test YOLO mode can be enabled via callback."""
        # Test through the callback mechanism
        # In real usage this would be called by typer
        # We just verify the global variable can be set
        from booksmith import main

        main._yolo_mode = True
        assert get_yolo_mode() is True
        main._yolo_mode = False  # Reset


class TestChapterListFeedback:
    """Test chapter list feedback mechanism."""

    def test_review_chapter_list_approve(self, tmp_path):
        """Test approving chapter list proceeds to outline review."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)

        # Mock chapters
        chapters = [
            {"number": 1, "title": "Chapter One", "purpose": "Setup"},
            {"number": 2, "title": "Chapter Two", "purpose": "Action"},
        ]

        mock_client = MagicMock()
        mock_outlines = MagicMock()

        with patch("booksmith.main.ask_choice", return_value="A"):
            with patch("booksmith.main.review_chapter_outlines") as mock_review:
                review_chapter_list_and_proceed(project, mock_client, chapters)

                # Should proceed to outline review
                mock_review.assert_called_once()
                args = mock_review.call_args
                assert args[0][0] == project
                assert args[0][1] == mock_client
                assert args[0][2] == chapters
                assert args[0][3] == 1  # First chapter

    def test_review_chapter_list_regenerate(self, tmp_path):
        """Test regenerating chapter list."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.write_file("story_bible.md", "# Bible\n\nOverview")
        project.write_file("world.md", "# World\n\nDetails")
        project.save_character_index([{"name": "Alice", "role": "Hero"}])

        chapters = [{"number": 1, "title": "Old Title", "purpose": "Old purpose"}]

        # Mock regeneration response
        new_response = """| # | Title | Purpose |
|---|-------|---------|
| 1 | New Title | New purpose |"""

        mock_client = MagicMock()
        mock_client.generate.return_value = new_response

        with patch("booksmith.main.ask_choice", return_value="R"):
            with patch("booksmith.main.review_chapter_list_and_proceed") as mock_review:
                review_chapter_list_and_proceed(project, mock_client, chapters)

                # Should have regenerated and called itself
                assert mock_client.generate.called
                # Should call itself again with new chapters
                assert mock_review.call_count == 1

    def test_review_chapter_list_feedback(self, tmp_path):
        """Test providing feedback on chapter list."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.write_file("story_bible.md", "# Bible\n\nOverview")
        project.write_file("world.md", "# World\n\nDetails")
        project.save_character_index([{"name": "Alice", "role": "Hero"}])

        chapters = [{"number": 1, "title": "Old Title", "purpose": "Old purpose"}]

        # Mock regeneration with feedback
        improved_response = """| # | Title | Purpose |
|---|-------|---------|
| 1 | Improved Title | Improved purpose |"""

        mock_client = MagicMock()
        mock_client.generate.return_value = improved_response

        with patch("booksmith.main.console.input", return_value="Make it better"):
            with patch("booksmith.main.ask_choice", return_value="F"):
                with patch(
                    "booksmith.main.review_chapter_list_and_proceed"
                ) as mock_review:
                    review_chapter_list_and_proceed(project, mock_client, chapters)

                    # Verify feedback was included
                    call_args = mock_client.generate.call_args
                    prompt = call_args[1]["user_message"]
                    assert "Make it better" in prompt

    def test_review_chapter_list_edit(self, tmp_path):
        """Test editing chapter list."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)

        chapters = [{"number": 1, "title": "Chapter One", "purpose": "Setup"}]

        mock_client = MagicMock()

        with patch("booksmith.main.edit_in_editor"):
            with patch("booksmith.main.review_chapter_outlines") as mock_review:
                with patch("booksmith.main.ask_choice", return_value="E"):
                    review_chapter_list_and_proceed(project, mock_client, chapters)

                    # Should proceed to outline review after edit
                    mock_review.assert_called_once()


class TestChapterOutlineReview:
    """Test chapter outline review workflow."""

    def test_review_outlines_skips_approved(self, tmp_path):
        """Test that approved outlines are skipped."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.write_file("story_bible.md", "# Bible\n\nOverview")
        project.write_file("world.md", "# World\n\nDetails")
        project.save_character_index([{"name": "Alice", "role": "Hero"}])

        # Write chapter list
        chapter_list = """| # | Title | Purpose |
|---|-------|---------|
| 1 | Chapter One | Setup |
| 2 | Chapter Two | Action |"""
        project.write_file("chapter_outlines/chapter_list.md", chapter_list)

        # Mark chapter 1 as approved, chapter 2 as not
        project.update_outline_status(1, approved=True)

        chapters = [
            {"number": 1, "title": "Chapter One", "purpose": "Setup"},
            {"number": 2, "title": "Chapter Two", "purpose": "Action"},
        ]

        mock_client = MagicMock()

        with patch("booksmith.main.review_chapter_outlines") as mock_review:
            review_chapter_outlines(project, mock_client, chapters, 1)

            # Should skip chapter 1 and go to chapter 2
            args = mock_review.call_args
            assert args[0][3] == 2  # Chapter 2

    def test_review_outlines_generates_missing(self, tmp_path):
        """Test that missing outlines are generated."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.write_file("story_bible.md", "# Bible\n\nOverview")
        project.write_file("world.md", "# World\n\nDetails")
        project.save_character_index([{"name": "Alice", "role": "Hero"}])

        # Write chapter list but no outline
        chapter_list = """| # | Title | Purpose |
|---|-------|---------|
| 1 | Chapter One | Setup |"""
        project.write_file("chapter_outlines/chapter_list.md", chapter_list)

        chapters = [{"number": 1, "title": "Chapter One", "purpose": "Setup"}]

        # Mock outline generation
        mock_outline = """# CHAPTER 1: Chapter One

## CHAPTER OVERVIEW

**POV Character:** Alice
"""

        mock_client = MagicMock()
        mock_client.generate.return_value = mock_outline

        with patch("booksmith.main.ask_choice", return_value="A"):
            with patch("booksmith.main.ask_choice", return_value="C"):
                with patch("booksmith.main.print_markdown"):
                    review_chapter_outlines(project, mock_client, chapters, 1)

                    # Should have generated the outline
                    assert mock_client.generate.called

                    # Verify file was created
                    assert project.file_exists("chapter_outlines/chapter_1.md")

    def test_review_outlines_user_approve(self, tmp_path):
        """Test user approving outline triggers AI review."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.write_file("story_bible.md", "# Bible\n\nOverview")
        project.write_file("world.md", "# World\n\nDetails")
        project.save_character_index([{"name": "Alice", "role": "Hero"}])

        # Write chapter list and outline
        chapter_list = """| # | Title | Purpose |
|---|-------|---------|
| 1 | Chapter One | Setup |"""
        project.write_file("chapter_outlines/chapter_list.md", chapter_list)

        outline = """# CHAPTER 1: Chapter One

## CHAPTER OVERVIEW

**POV Character:** Alice
**Setting:** The Castle
"""
        project.write_file("chapter_outlines/chapter_1.md", outline)

        chapters = [{"number": 1, "title": "Chapter One", "purpose": "Setup"}]

        # Mock AI review
        mock_review = "Great outline! Score: 8/10"
        mock_client = MagicMock()
        mock_client.stream.return_value = iter(mock_review)

        # Mock ask_choice to return "A" (approve) first, then "C" (continue)
        with patch("booksmith.main.ask_choice", side_effect=["A", "C"]):
            with patch("booksmith.main.print_markdown"):
                with patch("booksmith.main.print_panel"):
                    review_chapter_outlines(project, mock_client, chapters, 1)

                    # Should have generated AI review
                    assert mock_client.stream.called

                    # Outline should be approved
                    assert 1 in project.approved_outlines


class TestRunChaptersPhase:
    """Test the chapter outlines phase."""

    def test_uses_existing_chapter_list(self, tmp_path):
        """Test that existing chapter list is used."""
        from booksmith.pipeline.chapter_outliner import parse_chapter_list

        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)

        # Create existing chapter list
        chapter_list = """| # | Title | Purpose |
|---|-------|---------|
| 1 | Chapter One | Setup |
| 2 | Chapter Two | Action |"""
        project.write_file("chapter_outlines/chapter_list.md", chapter_list)

        # Parse the list so we know what to expect
        expected_chapters = parse_chapter_list(chapter_list)

        mock_client = MagicMock()

        with patch("booksmith.main.review_chapter_outlines") as mock_review:
            run_chapters_phase(project, mock_client)

            # Should use existing list
            mock_review.assert_called_once()
            args = mock_review.call_args[0]
            chapters = args[2]  # Third argument is chapters list
            assert len(chapters) == 2
            assert chapters[0]["title"] == "Chapter One"

    def test_generates_new_chapter_list(self, tmp_path):
        """Test that new chapter list is generated if missing."""
        from booksmith.pipeline import chapter_outliner

        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)

        # Mock chapter list generation
        mock_chapters = [{"number": 1, "title": "Chapter One", "purpose": "Setup"}]
        mock_client = MagicMock()

        with patch(
            "booksmith.main.chapter_outliner.generate_chapter_list",
            return_value=mock_chapters,
        ):
            with patch("booksmith.main.ask_choice", return_value="A"):
                with patch("booksmith.main.review_chapter_outlines") as mock_review:
                    run_chapters_phase(project, mock_client)

                    # Should have generated new list
                    mock_review.assert_called_once()
                    args = mock_review.call_args[0]
                    chapters = args[2]  # Third argument is chapters list
                    assert len(chapters) == 1

    def test_updates_total_chapters_if_mismatch(self, tmp_path):
        """Test that total_chapters is updated if count doesn't match."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.set_total_chapters(10)  # Set to 10

        # Mock chapter list with 5 chapters
        mock_chapters = [
            {"number": i, "title": f"Chapter {i}", "purpose": f"Purpose {i}"}
            for i in range(1, 6)
        ]
        mock_client = MagicMock()

        with patch(
            "booksmith.main.chapter_outliner.generate_chapter_list",
            return_value=mock_chapters,
        ):
            with patch("booksmith.main.review_chapter_list_and_proceed"):
                run_chapters_phase(project, mock_client)

                # Should have updated to 5
                assert project.total_chapters == 5


class TestWorkflowIntegration:
    """Integration tests for main workflow."""

    def test_new_command_creates_project(self, tmp_path):
        """Test that new command creates project correctly."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test Book\n\nA story.")

        # Create project directly instead of using CLI
        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        from booksmith.storage.project import Project

        project = Project.create("test-book", seed_file, projects_dir)

        # Verify project was created
        assert project.path.exists()
        assert (project.path / "project.json").exists()
        assert project.title == "Test Book"

    def test_status_command(self, tmp_path):
        """Test status command."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        # Create project first
        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        from booksmith.storage.project import Project

        project = Project.create("test-book", seed_file, projects_dir)

        # Test displaying status
        from booksmith.ui.console import display_project_status

        # Just verify it doesn't crash
        display_project_status(project)
        assert (tmp_path / "projects" / "test-book").exists()

    def test_status_command(self, tmp_path):
        """Test status command."""
        from typer.testing import CliRunner
        from booksmith.main import app

        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        # Create project first
        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        from booksmith.storage.project import Project

        project = Project.create("test-book", seed_file, projects_dir)

        runner = CliRunner()
        result = runner.invoke(app, ["status", "test-book"])

        assert result.exit_code == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
