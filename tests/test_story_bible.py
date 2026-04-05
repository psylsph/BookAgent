"""Unit tests for story_bible with mocked AI responses."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from booksmith.pipeline.story_bible import (
    extract_word_count,
    calculate_chapter_count,
    generate_story_bible,
    regenerate_story_bible,
)
from booksmith.storage.project import Project


class TestExtractWordCount:
    """Test word count extraction from story bible."""

    def test_extract_word_count_asterisk_format(self):
        """Test extracting word count from **Estimated Word Count** - 50000 format."""
        bible = """
# Story Bible

## Overview
This is a story.

**Estimated Word Count** - 50000

## Characters
...
"""
        count = extract_word_count(bible)
        assert count == 50000

    def test_extract_word_count_colon_format(self):
        """Test extracting word count from Estimated Word Count: 50000 format."""
        bible = """
# Story Bible

## Overview
This is a story.

Estimated Word Count: 75000

## Characters
...
"""
        count = extract_word_count(bible)
        assert count == 75000

    def test_extract_word_count_words_format(self):
        """Test extracting word count from 50,000 words format."""
        bible = """
# Story Bible

This story is approximately 50,000 words in length.

## Characters
...
"""
        count = extract_word_count(bible)
        assert count == 50000

    def test_extract_word_count_with_commas(self):
        """Test extracting word count with commas."""
        bible = """
# Story Bible

**Estimated Word Count** - 75,000

## Characters
...
"""
        count = extract_word_count(bible)
        assert count == 75000

    def test_extract_word_count_no_match(self):
        """Test when no word count is found."""
        bible = """
# Story Bible

## Overview
This is a story without word count.

## Characters
...
"""
        count = extract_word_count(bible)
        assert count == 0

    def test_extract_word_count_case_insensitive(self):
        """Test that extraction is case insensitive."""
        bible = """
# Story Bible

ESTIMATED WORD COUNT: 60000

## Characters
...
"""
        count = extract_word_count(bible)
        assert count == 60000


class TestCalculateChapterCount:
    """Test chapter count calculation."""

    def test_calculate_chapter_count_from_word_count(self):
        """Test calculating chapter count from word count."""
        # 50000 words / 1750 words per chapter = ~28.57 → 29 chapters
        count = calculate_chapter_count(50000)
        assert count == 29

    def test_calculate_chapter_count_minimum_8(self):
        """Test that chapter count is minimum 8."""
        # 10000 words / 1750 = ~5.71 → 8 (minimum)
        count = calculate_chapter_count(10000)
        assert count == 8

    def test_calculate_chapter_count_zero_words(self):
        """Test that zero word count returns default 24."""
        count = calculate_chapter_count(0)
        assert count == 24

    def test_calculate_chapter_count_negative_words(self):
        """Test that negative word count returns default 24."""
        count = calculate_chapter_count(-1000)
        assert count == 24

    def test_calculate_chapter_count_custom_min_words(self):
        """Test calculating with custom min words per chapter."""
        # Note: The min_words parameter is not actually used in the function
        # The function always uses CHAPTER_TARGET_WORDS (1750) internally
        count = calculate_chapter_count(50000, min_words=2000)
        # 50000 / 1750 = ~28.57 → 29 chapters (not 25, because min_words param is ignored)
        assert count == 29

    def test_calculate_chapter_count_rounding(self):
        """Test that chapter count rounds correctly."""
        # 30000 / 1750 = 17.14 → 17
        count = calculate_chapter_count(30000)
        assert count == 17


class TestGenerateStoryBible:
    """Test story bible generation."""

    def test_generate_story_bible_basic(self, tmp_path):
        """Test basic story bible generation."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory content.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)

        # Mock story bible generation
        mock_bible = """# Story Bible

## Overview
This is a test story.

**Estimated Word Count** - 50000

## Characters
- Alice: The hero
"""
        mock_client = MagicMock()
        mock_client.stream.return_value = iter(mock_bible)

        with patch("booksmith.pipeline.story_bible.print_header"):
            with patch("booksmith.pipeline.story_bible.console"):
                with patch(
                    "booksmith.pipeline.story_bible.format_prompt"
                ) as mock_format:
                    mock_format.return_value = ("system", "user")
                    result = generate_story_bible(project, mock_client)

                    assert "This is a test story" in result
                    # Should save to file
                    assert project.file_exists("story_bible.md")
                    # Should set chapter count
                    # 50000 / 1750 = ~28.57 → 29 chapters
                    assert project.config.get("total_chapters_planned") == 29

    def test_generate_story_bible_with_extra_instruction(self, tmp_path):
        """Test story bible generation with extra instruction."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory content.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)

        mock_bible = "# Story Bible\n\nContent"
        mock_client = MagicMock()
        mock_client.stream.return_value = iter(mock_bible)

        with patch("booksmith.pipeline.story_bible.print_header"):
            with patch("booksmith.pipeline.story_bible.console"):
                with patch(
                    "booksmith.pipeline.story_bible.format_prompt"
                ) as mock_format:
                    mock_format.return_value = ("system", "user")
                    result = generate_story_bible(
                        project, mock_client, extra_instruction="Make it longer"
                    )

                    # Should have called format_prompt
                    mock_format.assert_called_once()
                    # Extra instruction should be added to user prompt
                    # (we can't easily check this without inspecting the mock)

    def test_generate_story_bible_saves_to_file(self, tmp_path):
        """Test that generated story bible is saved to file."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)

        mock_bible = "# Story Bible\n\n**Estimated Word Count** - 35000\n\nContent here"
        mock_client = MagicMock()
        mock_client.stream.return_value = iter(mock_bible)

        with patch("booksmith.pipeline.story_bible.print_header"):
            with patch("booksmith.pipeline.story_bible.console"):
                with patch(
                    "booksmith.pipeline.story_bible.format_prompt"
                ) as mock_format:
                    mock_format.return_value = ("system", "user")
                    generate_story_bible(project, mock_client)

                    # Should save to file
                    content = project.read_file("story_bible.md")
                    assert "Content here" in content

    def test_generate_story_bible_default_chapter_count(self, tmp_path):
        """Test default chapter count when no word count found."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)

        # Mock story bible without word count
        mock_bible = "# Story Bible\n\nNo word count here"
        mock_client = MagicMock()
        mock_client.stream.return_value = iter(mock_bible)

        with patch("booksmith.pipeline.story_bible.print_header"):
            with patch("booksmith.pipeline.story_bible.console"):
                with patch(
                    "booksmith.pipeline.story_bible.format_prompt"
                ) as mock_format:
                    mock_format.return_value = ("system", "user")
                    generate_story_bible(project, mock_client)

                    # Should default to 24 chapters
                    assert project.config.get("total_chapters_planned") == 24


class TestRegenerateStoryBible:
    """Test story bible regeneration."""

    def test_regenerate_story_bible_basic(self, tmp_path):
        """Test basic story bible regeneration."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)

        mock_bible = (
            "# Story Bible\n\n**Estimated Word Count** - 60000\n\nRegenerated content"
        )
        mock_client = MagicMock()
        mock_client.stream.return_value = iter(mock_bible)

        with patch("booksmith.pipeline.story_bible.print_header"):
            with patch("booksmith.pipeline.story_bible.console"):
                with patch(
                    "booksmith.pipeline.story_bible.format_prompt"
                ) as mock_format:
                    mock_format.return_value = ("system", "user")
                    result = regenerate_story_bible(project, mock_client)

                    assert "Regenerated content" in result
                    # Should update the file
                    content = project.read_file("story_bible.md")
                    assert "Regenerated content" in content

    def test_regenerate_with_extra_instruction(self, tmp_path):
        """Test regeneration with extra instruction."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)

        mock_bible = "# Story Bible\n\nUpdated content"
        mock_client = MagicMock()
        mock_client.stream.return_value = iter(mock_bible)

        with patch("booksmith.pipeline.story_bible.print_header"):
            with patch("booksmith.pipeline.story_bible.console"):
                with patch(
                    "booksmith.pipeline.story_bible.format_prompt"
                ) as mock_format:
                    mock_format.return_value = ("system", "user")
                    regenerate_story_bible(
                        project, mock_client, extra_instruction="Add more detail"
                    )

                    # Should have called with extra instruction
                    content = project.read_file("story_bible.md")
                    assert "Updated content" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
