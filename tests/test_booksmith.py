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
        assert MODEL_PROVIDER_MAP["reviewer"][0] == "local"

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
        monkeypatch.setenv("LOCAL_BASE_URL", "http://localhost:9999")

        import importlib
        import booksmith.api_client

        importlib.reload(booksmith.api_client)

        from booksmith.api_client import ANTHROPIC_BASE_URL, LOCAL_BASE_URL

        assert ANTHROPIC_BASE_URL == "https://test.zenmux.ai"
        assert LOCAL_BASE_URL == "http://localhost:9999"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
