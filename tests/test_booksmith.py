import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from booksmith.storage.project import Project, DEFAULT_CONFIG


class TestProject:
    def test_create_project(self, tmp_path):
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# My Book\n\nA story about something.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test_book", seed_file, projects_dir)

        assert project.path.exists()
        assert (project.path / "project.json").exists()
        assert (project.path / "seed.md").exists()
        assert (project.path / "characters").is_dir()
        assert (project.path / "chapter_outlines").is_dir()
        assert (project.path / "chapters").is_dir()
        assert (project.path / "reviews").is_dir()
        assert (project.path / "summaries").is_dir()

    def test_load_project(self, tmp_path):
        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project_path = projects_dir / "test_book"
        project_path.mkdir()

        (project_path / "project.json").write_text(
            json.dumps(
                {
                    "title": "Test Book",
                    "seed_file": "seed.md",
                    "status": "writing",
                    "current_chapter": 0,
                    **DEFAULT_CONFIG,
                }
            )
        )

        project = Project.load(project_path)

        assert project.title == "Test Book"
        assert project.status == "writing"

    def test_update_chapter_status(self, tmp_path):
        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project_path = projects_dir / "test_book"
        project_path.mkdir()

        config = {
            "title": "Test Book",
            "seed_file": "seed.md",
            "status": "writing",
            "current_chapter": 0,
            "approved_chapters": [],
            **DEFAULT_CONFIG,
        }
        (project_path / "project.json").write_text(json.dumps(config))

        project = Project.load(project_path)
        project.update_chapter_status(1, approved=True)

        loaded = project.load_config()
        assert 1 in loaded["approved_chapters"]
        assert loaded["current_chapter"] == 1

    def test_read_write_file(self, tmp_path):
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nSeed content.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test_book", seed_file, projects_dir)

        project.write_file("test.txt", "Hello, World!")

        assert project.read_file("test.txt") == "Hello, World!"
        assert project.file_exists("test.txt")

    def test_get_characters(self, tmp_path):
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nSeed content.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test_book", seed_file, projects_dir)

        characters = [
            {"name": "Alice", "role": "Protagonist", "description": "A brave hero"},
            {"name": "Bob", "role": "Antagonist", "description": "A dark villain"},
        ]
        project.save_character_index(characters)

        loaded = project.get_characters()

        assert len(loaded) == 2
        assert loaded[0]["name"] == "Alice"


class TestWordCount:
    def test_count_words(self):
        from booksmith.ui.console import count_words

        assert count_words("Hello, World!") == 2
        assert count_words("One two three") == 3
        assert count_words("") == 0
        assert count_words("   spaces   ") == 1


class TestAPIClient:
    def test_model_provider_map(self):
        from booksmith.api_client import MODEL_PROVIDER_MAP

        assert MODEL_PROVIDER_MAP["story_bible"][0] == "local"
        assert MODEL_PROVIDER_MAP["chapter_writer"][0] == "remote"
        assert MODEL_PROVIDER_MAP["chapter_outliner"][0] == "local"
        assert MODEL_PROVIDER_MAP["reviewer"][0] == "remote"
        assert MODEL_PROVIDER_MAP["outline_reviewer"][0] == "local"
        assert MODEL_PROVIDER_MAP["macro_summary"][0] == "local"

    def test_format_prompt(self):
        from booksmith.api_client import format_prompt

        with pytest.raises(FileNotFoundError):
            format_prompt("nonexistent")


class TestRetrieval:
    def test_stopwords_defined(self):
        from booksmith.pipeline.retrieval import STOPWORDS

        assert "the" in STOPWORDS
        assert "a" in STOPWORDS
        assert "and" in STOPWORDS
        assert len(STOPWORDS) > 100

    def test_retriever_empty_project(self, tmp_path):
        from booksmith.pipeline.retrieval import BookRetriever

        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nSeed content.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test_book", seed_file, projects_dir)

        retriever = BookRetriever(project.path)

        results = retriever.retrieve("test query")

        assert results == []

    def test_retriever_with_content(self, tmp_path):
        from booksmith.pipeline.retrieval import BookRetriever

        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nSeed content.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test_book", seed_file, projects_dir)

        project.write_file(
            "characters/Alice.md", "Alice is a brave hero from the north."
        )
        project.save_character_index([{"name": "Alice", "role": "Hero"}])

        retriever = BookRetriever(project.path)

        results = retriever.retrieve("Alice hero north", top_n=1)

        assert len(results) > 0
        assert "Alice" in results[0]["source"]


class TestWorkflow:
    """Integration tests for the workflow."""

    def test_story_bible_phase_checks_existence(self, tmp_path):
        """Test story bible phase logic."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test Book\n\nA test story.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test_book", seed_file, projects_dir)

        assert not project.file_exists("story_bible.md")

    def test_world_phase_checks_existence(self, tmp_path):
        """Test world phase logic."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nSeed.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test_book", seed_file, projects_dir)

        assert not project.file_exists("world.md")

    def test_chapter_approval_options(self):
        """Test that all chapter approval options exist."""
        from booksmith.ui.console import ask_chapter_approval

        with patch("booksmith.ui.console.Prompt.ask", return_value="A"):
            result = ask_chapter_approval("Test")
            assert result == "A"

        with patch("booksmith.ui.console.Prompt.ask", return_value="S"):
            result = ask_chapter_approval("Test")
            assert result == "S"

        with patch("booksmith.ui.console.Prompt.ask", return_value="R"):
            result = ask_chapter_approval("Test")
            assert result == "R"

        with patch("booksmith.ui.console.Prompt.ask", return_value="F"):
            result = ask_chapter_approval("Test")
            assert result == "F"

        with patch("booksmith.ui.console.Prompt.ask", return_value="E"):
            result = ask_chapter_approval("Test")
            assert result == "E"


class TestAPIConfig:
    def test_loads_from_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://test.zenmux.ai")
        monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "test-token")

        import importlib
        import booksmith.api_client

        importlib.reload(booksmith.api_client)

        from booksmith.api_client import ANTHROPIC_BASE_URL, ANTHROPIC_AUTH_TOKEN

        assert ANTHROPIC_BASE_URL == "https://test.zenmux.ai"
        assert ANTHROPIC_AUTH_TOKEN == "test-token"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestChapterOutliner:
    def test_parse_chapter_list_table(self):
        from booksmith.pipeline.chapter_outliner import parse_chapter_list

        text = """| # | Title | Purpose |
|---|-------|---------|
| 1 | Chapter One | First purpose |
| 2 | Chapter Two | Second purpose |
"""
        chapters = parse_chapter_list(text)
        assert len(chapters) == 2
        assert chapters[0]["number"] == 1
        assert chapters[0]["title"] == "Chapter One"
        assert chapters[0]["purpose"] == "First purpose"

    def test_parse_chapter_list_numbered(self):
        from booksmith.pipeline.chapter_outliner import parse_chapter_list

        text = """1. Chapter One - First purpose
2. Chapter Two - Second purpose"""
        chapters = parse_chapter_list(text)
        assert len(chapters) == 2

    def test_parse_chapter_list_empty(self):
        from booksmith.pipeline.chapter_outliner import parse_chapter_list

        chapters = parse_chapter_list("")
        assert chapters == []

    def test_extract_act_structure(self):
        from booksmith.pipeline.chapter_outliner import extract_act_structure

        text = """Act 1: Setup - Introduction
Act 2: Confrontation - Rising action
Act 3: Resolution - Conclusion"""
        acts = extract_act_structure(text)
        assert len(acts) == 3
        assert acts[0]["number"] == 1


class TestCharacters:
    def test_load_character_index(self, tmp_path):
        from booksmith.storage.project import Project

        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nSeed.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test_book", seed_file, projects_dir)

        chars = [
            {"name": "Alice", "role": "Hero", "description": "A brave hero"},
            {"name": "Bob", "role": "Villain", "description": "Evil"},
        ]
        project.save_character_index(chars)

        loaded = project.get_characters()
        assert len(loaded) == 2
        assert loaded[0]["name"] == "Alice"

    def test_character_profile_exists(self, tmp_path):
        from booksmith.storage.project import Project

        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nSeed.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test_book", seed_file, projects_dir)

        project.write_file("characters/Alice.md", "# Alice\n\nHero profile.")

        assert project.file_exists("characters/Alice.md")


class TestWorldBuilder:
    def test_world_file_operations(self, tmp_path):
        from booksmith.storage.project import Project

        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nSeed.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test_book", seed_file, projects_dir)

        project.write_file("world.md", "# World\n\nWorld building content.")

        assert project.read_file("world.md") == "# World\n\nWorld building content."


class TestStoryBible:
    def test_story_bible_file_operations(self, tmp_path):
        from booksmith.storage.project import Project

        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nSeed.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test_book", seed_file, projects_dir)

        project.write_file("story_bible.md", "# Story Bible\n\nStory overview.")

        assert project.read_file("story_bible.md") == "# Story Bible\n\nStory overview."


class TestReviewer:
    def test_extract_score(self):
        from booksmith.pipeline.reviewer import extract_score

        assert extract_score("The score is 8 out of 10.") == 8.0
        assert extract_score("Rating: 5/10 for quality.") == 5.0
        assert extract_score("Score: 7.5") == 7.5
        assert extract_score("No score here.") is None
        assert extract_score("") is None


class TestConsole:
    def test_ask_choice_defaults(self):
        from booksmith.ui.console import ask_choice

        with patch("booksmith.ui.console.Prompt.ask", return_value="A"):
            result = ask_choice("Test?", ["A", "R"])
            assert result == "A"

    def test_ask_choice_lowercase(self):
        from booksmith.ui.console import ask_choice

        with patch("booksmith.ui.console.Prompt.ask", return_value="a"):
            result = ask_choice("Test?", ["A", "R"])
            assert result == "A"

    def test_confirm_yes(self):
        from booksmith.ui.console import confirm

        with patch("booksmith.ui.console.Confirm.ask", return_value=True):
            result = confirm("Continue?")
            assert result is True

    def test_confirm_no(self):
        from booksmith.ui.console import confirm

        with patch("booksmith.ui.console.Confirm.ask", return_value=False):
            result = confirm("Continue?")
            assert result is False

    def test_print_header(self):
        from booksmith.ui.console import print_header

        print_header("Test Header")

    def test_print_success(self):
        from booksmith.ui.console import print_success

        print_success("Success message")

    def test_print_error(self):
        from booksmith.ui.console import print_error

        print_error("Error message")

    def test_print_panel(self):
        from booksmith.ui.console import print_panel

        print_panel("Content", title="Test Panel")

    def test_print_markdown(self):
        from booksmith.ui.console import print_markdown

        print_markdown("# Markdown\n\nContent", title="Test")

    def test_display_project_status(self, tmp_path):
        from booksmith.storage.project import Project
        from booksmith.ui.console import display_project_status

        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nSeed.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test_book", seed_file, projects_dir)

        display_project_status(project)


class TestProjectAdvanced:
    def test_get_macro_summary(self, tmp_path):
        from booksmith.storage.project import Project

        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nSeed.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test_book", seed_file, projects_dir)

        project.write_file(
            "summaries/macro_summary.md", "# Summary\n\nChapter summaries."
        )

        summary = project.get_macro_summary()
        assert summary == "# Summary\n\nChapter summaries."

    def test_get_chapter_outline(self, tmp_path):
        from booksmith.storage.project import Project

        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nSeed.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test_book", seed_file, projects_dir)

        project.write_file("chapter_outlines/chapter_1.md", "# Chapter 1\n\nOutline.")

        outline = project.get_chapter_outline(1)
        assert outline == "# Chapter 1\n\nOutline."

    def test_get_chapter_outline_missing(self, tmp_path):
        from booksmith.storage.project import Project

        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nSeed.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test_book", seed_file, projects_dir)

        outline = project.get_chapter_outline(1)
        assert outline is None

    def test_get_approved_chapter(self, tmp_path):
        from booksmith.storage.project import Project

        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nSeed.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test_book", seed_file, projects_dir)

        project.write_file("chapters/chapter_1.md", "# Chapter 1\n\nContent.")

        chapter = project.get_approved_chapter(1)
        assert chapter == "# Chapter 1\n\nContent."

    def test_project_set_status(self, tmp_path):
        from booksmith.storage.project import Project

        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nSeed.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test_book", seed_file, projects_dir)

        project.set_status("completed")

        config = project.load_config()
        assert config["status"] == "completed"

    def test_project_total_chapters(self, tmp_path):
        from booksmith.storage.project import Project

        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nSeed.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test_book", seed_file, projects_dir)

        assert project.total_chapters == 0
        assert project.approved_outlines == []

        project.set_total_chapters(24)
        assert project.total_chapters == 24

        project.update_outline_status(1, approved=True)
        assert project.approved_outlines == [1]

        project.update_outline_status(2, approved=True)
        assert project.approved_outlines == [1, 2]

        project.update_outline_status(1, approved=False)
        assert project.approved_outlines == [2]
