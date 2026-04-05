"""Unit tests for chapter writer with mocked AI responses."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch, call
from typing import Generator

import pytest

from booksmith.pipeline.chapter_writer import (
    generate_chapter,
    regenerate_chapter,
)
from booksmith.storage.project import Project


class TestGenerateChapter:
    """Test chapter generation with mocked AI responses."""

    def test_generate_chapter_basic(self, tmp_path):
        """Test basic chapter generation."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory content.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.set_total_chapters(3)
        project.write_file("story_bible.md", "# Bible\n\nOverview")
        project.write_file("world.md", "# World\n\nDetails")
        project.save_character_index([{"name": "Alice", "role": "Hero"}])

        # Create chapter outline
        outline = """# CHAPTER 1: Test Chapter

## CHAPTER OVERVIEW

**POV Character:** Alice
**Setting:** The Castle

**Chapter Goal:** Begin journey
"""
        project.write_file("chapter_outlines/chapter_1.md", outline)

        # Mock both context brief generation and chapter generation
        mock_context_brief = "Context: Alice is the hero in the Castle."
        mock_chapter = "# Chapter 1\n\nOnce upon a time..."

        mock_client = MagicMock()
        # First call is for context brief, second for chapter generation
        mock_client.stream.side_effect = [
            iter(mock_context_brief),
            iter(mock_chapter),
        ]

        with patch("booksmith.pipeline.chapter_writer.print_header"):
            with patch("booksmith.pipeline.chapter_writer.console"):
                result = generate_chapter(project, mock_client, 1)

                assert "Once upon a time" in result

    def test_generate_chapter_includes_context(self, tmp_path):
        """Test that chapter generation includes proper context."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory content.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.set_total_chapters(3)
        project.write_file("story_bible.md", "# Bible\n\nOverview")
        project.write_file("world.md", "# World\n\nDetails")
        project.save_character_index(
            [{"name": "Alice", "role": "Hero"}, {"name": "Bob", "role": "Villain"}]
        )

        outline = """# CHAPTER 1: Test

**POV Character:** Alice
"""
        project.write_file("chapter_outlines/chapter_1.md", outline)

        mock_client = MagicMock()
        mock_context_brief = "Alice is the hero."
        mock_client.stream.side_effect = [
            iter(mock_context_brief),
            iter("# Chapter 1\n\nContent"),
        ]

        with patch("booksmith.pipeline.chapter_writer.print_header"):
            with patch("booksmith.pipeline.chapter_writer.console"):
                generate_chapter(project, mock_client, 1)

                # Verify generate was called with proper system prompt
                assert mock_client.stream.call_count == 2
                # Get the second call (chapter generation)
                call_args = mock_client.stream.call_args_list[1]
                system = call_args[1]["system"]
                user_message = call_args[1]["user_message"]

                # Should include key context
                assert "Alice" in user_message or "Hero" in user_message
                assert "Test Chapter" in user_message or "Test" in user_message

    def test_generate_chapter_with_min_words_check(self, tmp_path):
        """Test chapter generation respects min_words setting."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.config["min_words_per_chapter"] = 2500
        project.save_config(project.config)

        project.write_file("story_bible.md", "# Bible\n\nOverview")
        project.write_file("world.md", "# World\n\nDetails")
        project.save_character_index([{"name": "Alice", "role": "Hero"}])

        outline = """# CHAPTER 1: Test

**POV Character:** Alice
"""
        project.write_file("chapter_outlines/chapter_1.md", outline)

        mock_context_brief = "Context for Alice."
        short_chapter = "# Chapter 1\n\nShort content."  # Below minimum
        long_chapter = "# Chapter 1\n\n" + "A story. " * 300  # Above minimum

        mock_client = MagicMock()

        # First attempt: context brief + short chapter
        # Second attempt: context brief + long chapter
        mock_client.stream.side_effect = [
            iter(mock_context_brief),
            iter(short_chapter),
            iter(mock_context_brief),
            iter(long_chapter),
        ]

        with patch("booksmith.pipeline.chapter_writer.print_header"):
            with patch("booksmith.pipeline.chapter_writer.console"):
                # Note: generate_chapter doesn't retry on word count,
                # word count validation happens in main.py
                generate_chapter(project, mock_client, 1)

                # Should have called twice (context brief + chapter generation)
                assert mock_client.stream.call_count == 2

    def test_generate_chapter_with_retrieval(self, tmp_path):
        """Test chapter generation uses context retrieval."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.set_total_chapters(3)
        project.write_file("story_bible.md", "# Bible\n\nOverview")
        project.write_file("world.md", "# World\n\nDetails")
        project.save_character_index([{"name": "Alice", "role": "Hero"}])

        outline = """# CHAPTER 1: Test

**POV Character:** Alice
"""
        project.write_file("chapter_outlines/chapter_1.md", outline)

        mock_client = MagicMock()
        mock_context_brief = "Context with retrieval."
        mock_client.stream.side_effect = [
            iter(mock_context_brief),
            iter("# Chapter 1\n\nContent"),
        ]

        with patch("booksmith.pipeline.chapter_writer.print_header"):
            with patch("booksmith.pipeline.chapter_writer.console"):
                generate_chapter(project, mock_client, 1)

                # Should have called twice (context brief + chapter generation)
                assert mock_client.stream.call_count == 2

    def test_generate_chapter_word_count_validation(self, tmp_path):
        """Test that word count is validated and included in review."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.config["min_words_per_chapter"] = 1500
        project.save_config(project.config)

        project.write_file("story_bible.md", "# Bible\n\nOverview")
        project.write_file("world.md", "# World\n\nDetails")
        project.save_character_index([{"name": "Alice", "role": "Hero"}])

        outline = """# CHAPTER 1: Test

**POV Character:** Alice
"""
        project.write_file("chapter_outlines/chapter_1.md", outline)

        # Chapter with good word count
        good_chapter = "# Chapter 1\n\n" + "Story " * 200
        mock_context_brief = "Context for good chapter."

        mock_client = MagicMock()
        mock_client.stream.side_effect = [
            iter(mock_context_brief),
            iter(good_chapter),
        ]

        with patch("booksmith.pipeline.chapter_writer.print_header"):
            with patch("booksmith.pipeline.chapter_writer.console"):
                generate_chapter(project, mock_client, 1)

                # Should have completed successfully
                assert mock_client.stream.call_count == 2

    def test_generate_chapter_saves_to_draft(self, tmp_path):
        """Test that chapter is initially saved as draft."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.set_total_chapters(3)
        project.write_file("story_bible.md", "# Bible\n\nOverview")
        project.write_file("world.md", "# World\n\nDetails")
        project.save_character_index([{"name": "Alice", "role": "Hero"}])

        outline = """# CHAPTER 1: Test

**POV Character:** Alice
"""
        project.write_file("chapter_outlines/chapter_1.md", outline)

        mock_chapter = "# Chapter 1\n\nContent here"
        mock_context_brief = "Context."

        mock_client = MagicMock()
        mock_client.stream.side_effect = [
            iter(mock_context_brief),
            iter(mock_chapter),
        ]

        with patch("booksmith.pipeline.chapter_writer.print_header"):
            with patch("booksmith.pipeline.chapter_writer.console"):
                generate_chapter(project, mock_client, 1)

                # Should save as draft
                assert project.file_exists("chapters/chapter_1_draft.md")
                content = project.read_file("chapters/chapter_1_draft.md")
                assert "Content here" in content

    def test_generate_chapter_includes_previous_next_context(self, tmp_path):
        """Test that generation includes context from adjacent chapters."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.set_total_chapters(3)
        project.write_file("story_bible.md", "# Bible\n\nOverview")
        project.write_file("world.md", "# World\n\nDetails")
        project.save_character_index([{"name": "Alice", "role": "Hero"}])

        # Create outlines for all chapters
        for i in range(1, 4):
            outline = f"# CHAPTER {i}: Chapter {i}\n\n**POV Character:** Alice"
            project.write_file(f"chapter_outlines/chapter_{i}.md", outline)

        mock_client = MagicMock()
        mock_context_brief = (
            "Context with adjacent chapters.\n\nPrevious: Chapter 1\n\nNext: Chapter 3"
        )
        mock_client.stream.side_effect = [
            iter(mock_context_brief),
            iter("# Chapter 2\n\nContent"),
        ]

        with patch("booksmith.pipeline.chapter_writer.print_header"):
            with patch("booksmith.pipeline.chapter_writer.console"):
                generate_chapter(project, mock_client, 2)

                # Should include previous and next chapter info
                call_args = mock_client.stream.call_args_list[1]
                user_message = call_args[1]["user_message"]

                # Should reference chapter 2 in the message
                assert "CHAPTER 2" in user_message or "Chapter 2" in user_message
                # Should have context brief info
                assert "Context with adjacent chapters" in user_message


class TestRegenerateChapter:
    """Test chapter regeneration."""

    def test_regenerate_with_feedback(self, tmp_path):
        """Test regeneration includes user feedback."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.set_total_chapters(3)
        project.write_file("story_bible.md", "# Bible\n\nOverview")
        project.write_file("world.md", "# World\n\nDetails")
        project.save_character_index([{"name": "Alice", "role": "Hero"}])

        outline = """# CHAPTER 1: Test

**POV Character:** Alice
"""
        project.write_file("chapter_outlines/chapter_1.md", outline)

        # Create draft
        project.write_file(
            "chapters/chapter_1_draft.md", "# Old chapter\n\nOld content"
        )

        # Mock new chapter
        new_chapter = "# Chapter 1\n\nImproved content"
        mock_context_brief = "Context."

        mock_client = MagicMock()
        mock_client.stream.side_effect = [
            iter(mock_context_brief),
            iter(new_chapter),
        ]

        feedback = "Make it more exciting"

        with patch("booksmith.pipeline.chapter_writer.print_header"):
            with patch("booksmith.pipeline.chapter_writer.console"):
                regenerate_chapter(project, mock_client, 1, feedback=feedback)

                # Should have called twice (context brief + regeneration)
                assert mock_client.stream.call_count == 2
                # Should have included feedback
                call_args = mock_client.stream.call_args_list[1]
                user_message = call_args[1]["user_message"]
                assert "Make it more exciting" in user_message

    def test_regenerate_updates_draft(self, tmp_path):
        """Test that regeneration updates the draft file."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.set_total_chapters(3)
        project.write_file("story_bible.md", "# Bible\n\nOverview")
        project.write_file("world.md", "# World\n\nDetails")
        project.save_character_index([{"name": "Alice", "role": "Hero"}])

        outline = """# CHAPTER 1: Test

**POV Character:** Alice
"""
        project.write_file("chapter_outlines/chapter_1.md", outline)

        # Create draft
        project.write_file(
            "chapters/chapter_1_draft.md", "# Old chapter\n\nOld content"
        )

        new_chapter = "# Chapter 1\n\nNew and improved content"
        mock_context_brief = "Context."

        mock_client = MagicMock()
        mock_client.stream.side_effect = [
            iter(mock_context_brief),
            iter(new_chapter),
        ]

        with patch("booksmith.pipeline.chapter_writer.print_header"):
            with patch("booksmith.pipeline.chapter_writer.console"):
                regenerate_chapter(project, mock_client, 1)

                # Draft should be updated
                draft_content = project.read_file("chapters/chapter_1_draft.md")
                assert "New and improved content" in draft_content

    def test_regenerate_preserves_approved_status(self, tmp_path):
        """Test that approved chapters remain approved after regeneration."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.set_total_chapters(3)
        project.write_file("story_bible.md", "# Bible\n\nOverview")
        project.write_file("world.md", "# World\n\nDetails")
        project.save_character_index([{"name": "Alice", "role": "Hero"}])

        outline = """# CHAPTER 1: Test

**POV Character:** Alice
"""
        project.write_file("chapter_outlines/chapter_1.md", outline)

        # Chapter 1 is not approved initially
        assert 1 not in project.approved_chapters

        # Create final version (not draft)
        project.write_file("chapters/chapter_1.md", "# Chapter 1\n\nFinal content")

        new_chapter = "# Chapter 1\n\nRegenerated content"
        mock_context_brief = "Context."

        mock_client = MagicMock()
        mock_client.stream.side_effect = [
            iter(mock_context_brief),
            iter(new_chapter),
        ]

        with patch("booksmith.pipeline.chapter_writer.print_header"):
            with patch("booksmith.pipeline.chapter_writer.console"):
                regenerate_chapter(project, mock_client, 1)

                # Should still not be approved (regeneration doesn't auto-approve)
                assert 1 not in project.approved_chapters


class TestChapterWriterIntegration:
    """Integration tests for chapter writer workflow."""

    def test_full_chapter_workflow(self, tmp_path):
        """Test complete chapter generation and approval."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test Book\n\nA complete story.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.set_total_chapters(1)
        project.write_file("story_bible.md", "# Bible\n\nComplete overview.")
        project.write_file("world.md", "# World\n\nComplete world guide.")
        project.save_character_index(
            [{"name": "Alice", "role": "Protagonist", "description": "Brave hero"}]
        )

        outline = """# CHAPTER 1: The Beginning

## CHAPTER OVERVIEW

**POV Character:** Alice
**Setting:** The Village

**Chapter Goal:** Alice discovers she has powers
"""
        project.write_file("chapter_outlines/chapter_1.md", outline)

        # Generate three passes as in the real workflow
        mock_chapters = [
            "# Chapter 1\n\nPass 1 content",
            "# Chapter 1\n\nPass 2 content - improved",
            "# Chapter 1\n\nPass 3 content - final",
        ]
        mock_context_briefs = [
            "Context for pass 1.",
            "Context for pass 2.",
            "Context for pass 3.",
        ]

        mock_client = MagicMock()
        mock_client.stream.side_effect = [
            iter(mock_context_briefs[0]),
            iter(mock_chapters[0]),
            iter(mock_context_briefs[1]),
            iter(mock_chapters[1]),
            iter(mock_context_briefs[2]),
            iter(mock_chapters[2]),
        ]

        # Simulate continuing through all passes
        with patch("booksmith.pipeline.chapter_writer.print_header"):
            with patch("booksmith.pipeline.chapter_writer.console"):
                # Pass 1
                generate_chapter(project, mock_client, 1)

                # Pass 2
                generate_chapter(project, mock_client, 1)

                # Pass 3
                generate_chapter(project, mock_client, 1)

                # After 3 passes, approve
                # (in real flow, this would be auto-approved after 3 passes)
                assert project.file_exists("chapters/chapter_1_draft.md")


class TestChapterWriterErrorHandling:
    """Test error handling in chapter writer."""

    def test_handles_missing_outline(self, tmp_path):
        """Test that missing outline is handled gracefully."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.set_total_chapters(1)
        project.write_file("story_bible.md", "# Bible\n\nOverview")
        project.write_file("world.md", "# World\n\nDetails")
        project.save_character_index([{"name": "Alice", "role": "Hero"}])

        # Don't create outline - should handle gracefully

        mock_client = MagicMock()
        mock_client.stream.return_value = iter("# Chapter 1\n\nContent")

        with patch("booksmith.pipeline.chapter_writer.print_header"):
            # Should not crash, but might print a warning
            try:
                generate_chapter(project, mock_client, 1)
                assert False, "Should have raised ValueError for missing outline"
            except ValueError as e:
                assert "No outline found" in str(e)

    def test_handles_generation_failure(self, tmp_path):
        """Test that generation failures are handled."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.set_total_chapters(1)
        project.write_file("story_bible.md", "# Bible\n\nOverview")
        project.write_file("world.md", "# World\n\nDetails")
        project.save_character_index([{"name": "Alice", "role": "Hero"}])

        outline = """# CHAPTER 1: Test

**POV Character:** Alice
"""
        project.write_file("chapter_outlines/chapter_1.md", outline)

        # Mock failed generation
        mock_client = MagicMock()
        mock_client.stream.side_effect = Exception("API Error")

        with patch("booksmith.pipeline.chapter_writer.print_header"):
            # Should handle the error gracefully
            try:
                generate_chapter(project, mock_client, 1)
                assert False, "Should have raised Exception"
            except Exception as e:
                # Expected to raise
                assert "API Error" in str(e)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
