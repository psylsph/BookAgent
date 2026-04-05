"""Unit tests for chapter outliner with mocked AI responses."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch, call
from typing import Generator

import pytest

from booksmith.pipeline.chapter_outliner import (
    parse_chapter_list,
    extract_act_structure,
    is_placeholder_value,
    normalize_outline_format,
    generate_chapter_list,
    generate_chapter_outline,
    regenerate_chapter_outline,
    generate_chapter_list_with_feedback,
)
from booksmith.storage.project import Project
from booksmith.api_client import APIClient


class TestParseChapterList:
    """Test chapter list parsing logic."""

    def test_parse_table_format(self):
        """Test parsing table format."""
        text = """| # | Title | Purpose |
|---|-------|---------|
| 1 | The Beginning | Introduction |
| 2 | The Journey | Rising action |
| 3 | The End | Resolution |"""

        chapters = parse_chapter_list(text)
        assert len(chapters) == 3
        assert chapters[0]["number"] == 1
        assert chapters[0]["title"] == "The Beginning"
        assert chapters[0]["purpose"] == "Introduction"

    def test_parse_numbered_list_format(self):
        """Test parsing numbered list format."""
        text = """1. Chapter One - First chapter
2. Chapter Two - Second chapter
3. Chapter Three - Third chapter"""

        chapters = parse_chapter_list(text)
        assert len(chapters) == 3
        assert chapters[0]["number"] == 1
        assert chapters[0]["title"] == "Chapter One"

    def test_parse_mixed_format(self):
        """Test parsing mixed formats."""
        text = """1. First Chapter - Purpose one
| 2 | Second Chapter | Purpose two |
3. Third Chapter - Purpose three"""

        chapters = parse_chapter_list(text)
        assert len(chapters) == 3
        assert chapters[0]["title"] == "First Chapter"
        assert chapters[1]["title"] == "Second Chapter"

    def test_parse_empty_string(self):
        """Test parsing empty input."""
        chapters = parse_chapter_list("")
        assert chapters == []

    def test_parse_only_headers(self):
        """Test parsing with only table headers."""
        text = """| # | Title | Purpose |
|---|-------|---------|"""

        chapters = parse_chapter_list(text)
        assert chapters == []

    def test_chapters_are_sorted(self):
        """Test that chapters are sorted by number."""
        text = """| 3 | Chapter Three | Third |
| 1 | Chapter One | First |
| 2 | Chapter Two | Second |"""

        chapters = parse_chapter_list(text)
        assert chapters[0]["number"] == 1
        assert chapters[1]["number"] == 2
        assert chapters[2]["number"] == 3


class TestExtractActStructure:
    """Test act structure extraction."""

    def test_explicit_acts(self):
        """Test extracting explicitly defined acts."""
        text = """
        Act 1: Setup - Introduction to characters
        Act 2: Confrontation - Rising action
        Act 3: Resolution - Conclusion
        """

        acts = extract_act_structure(text)
        assert len(acts) == 3
        assert acts[0]["number"] == 1
        assert "Setup" in acts[0]["description"]

    def test_roman_numeral_acts(self):
        """Test extracting acts with Roman numerals."""
        text = """
        Act I: The Beginning
        Act II: The Middle
        Act III: The End
        """

        acts = extract_act_structure(text)
        assert len(acts) == 3

    def test_no_acts_defaults_to_three(self):
        """Test default to 3 acts when none found."""
        text = "This is just a story without explicit acts."

        acts = extract_act_structure(text)
        assert len(acts) == 3
        assert acts[0]["number"] == 1
        assert (
            acts[0]["description"]
            == "Setup - Introduce characters, world, and inciting incident"
        )

    def test_part_format(self):
        """Test extracting Part format."""
        text = """
        Part 1: The Journey Begins
        Part 2: Challenges Arise
        """

        acts = extract_act_structure(text)
        assert len(acts) == 2


class TestIsPlaceholderValue:
    """Test placeholder value detection."""

    def test_detects_specify(self):
        """Test detection of [Specify] placeholder."""
        assert is_placeholder_value("[Specify]")
        assert is_placeholder_value("[Specify character]")
        assert is_placeholder_value("[Something]")

    def test_detects_describe(self):
        """Test detection of [Describe] placeholder."""
        assert is_placeholder_value("[Describe what happens]")
        assert is_placeholder_value("[Describe]")

    def test_detects_character(self):
        """Test detection of [Character] placeholder."""
        assert is_placeholder_value("[Character name]")
        assert is_placeholder_value("[Character]")

    def test_detects_location(self):
        """Test detection of [Location] placeholder."""
        assert is_placeholder_value("[Location]")
        assert is_placeholder_value("[Setting: Location]")

    def test_detects_scene_placeholders(self):
        """Test detection of scene-related placeholders."""
        assert is_placeholder_value("[Opening]")
        assert is_placeholder_value("[Escalation]")
        assert is_placeholder_value("[Climax]")
        assert is_placeholder_value("[Resolution]")
        assert is_placeholder_value("[Scene 1]")

    def test_real_values_not_placeholders(self):
        """Test that real values are not detected as placeholders."""
        assert not is_placeholder_value("Alice")
        assert not is_placeholder_value("The Castle")
        assert not is_placeholder_value("Scene where they meet")
        assert not is_placeholder_value("Elena discovers the truth")

    def test_case_insensitive(self):
        """Test case-insensitive placeholder detection."""
        assert is_placeholder_value("[specify]")
        assert is_placeholder_value("[SPECIFY]")
        assert is_placeholder_value("[ChaRacTer]")


class TestNormalizeOutlineFormat:
    """Test outline normalization logic."""

    def test_normalizes_complete_outline(self):
        """Test normalization of a complete outline."""
        outline = """# CHAPTER 1: TEST TITLE

## CHAPTER OVERVIEW

**POV Character:** Alice
**Setting:** The Castle
**Characters Present:** Alice, Bob

**Chapter Goal:** Find the treasure
**Emotional Arc:** Tension to relief

## SCENE BREAKDOWN

### Scene 1: The Discovery
**Setting:** The Castle
**POV:** Alice
**Action:** Alice finds a map. Bob enters. They argue about the treasure.

### Scene 2: The Journey
**Setting:** The Forest
**POV:** Alice
**Action:** Alice travels through the forest. She encounters obstacles. She finds clues.

### Scene 3: The Revelation
**Setting:** The Cave
**POV:** Alice
**Action:** Alice reaches the cave. She discovers the treasure. Bob appears.

## STORY CONNECTIONS

**Connection to the Seed Story / Prologue:** Setup from seed

**Connection to Chapter 2:** Cliffhanger

## FORESHADOWING & CALLBACKS

- The map will be important
- Reference to seed story
"""

        normalized = normalize_outline_format(outline, 1, "Test Title")

        assert "POV Character:** Alice" in normalized
        assert "Setting:** The Castle" in normalized
        assert "Goal:** Find the treasure" in normalized
        assert "Scene 1: The Discovery" in normalized

    def test_handles_missing_fields(self):
        """Test handling of missing fields."""
        outline = """# CHAPTER 1: TEST

## CHAPTER OVERVIEW

**POV Character:** [Specify]
**Setting:** [Location]

**Chapter Goal:** [Goal]

## SCENE BREAKDOWN

### Scene 1: Title
**Setting:** [Location]
**POV:** [Character]
**Action:** [Action]

"""

        normalized = normalize_outline_format(outline, 1, "Test")

        # Should preserve placeholders if extraction fails
        assert "[Specify]" in normalized or "Alice" in normalized  # Either is fine

    def test_extracts_scenes(self):
        """Test scene extraction."""
        outline = """
### Scene 1: Opening
**Setting:** Location 1
**POV:** Character 1
**Action:** Action 1

### Scene 2: Middle
**Setting:** Location 2
**POV:** Character 2
**Action:** Action 2
"""

        normalized = normalize_outline_format(outline, 1, "Test")
        assert "Scene 1: Opening" in normalized
        assert "Scene 2: Middle" in normalized

    def test_handles_malformed_scenes(self):
        """Test handling of malformed scene definitions."""
        outline = """
**Scene:** The Confrontation
Alice meets Bob at the bridge.

**Another Scene:** Escape
They run away together.
"""

        normalized = normalize_outline_format(outline, 1, "Test")
        # Should not crash, should produce some output
        assert len(normalized) > 0


class TestGenerateChapterList:
    """Test chapter list generation with mocked AI."""

    def test_generate_chapter_list_success(self, tmp_path):
        """Test successful chapter list generation."""
        # Create project
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test Book\n\nA story.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.write_file("story_bible.md", "# Story Bible\n\nOverview")
        project.write_file("world.md", "# World\n\nDetails")
        project.save_character_index(
            [{"name": "Alice", "role": "Hero", "description": "Brave"}]
        )

        # Mock AI response
        mock_response = """| # | Title | Purpose |
|---|-------|---------|
| 1 | Chapter One | Introduction |
| 2 | Chapter Two | Rising action |"""

        mock_client = MagicMock(spec=APIClient)
        mock_client.generate.return_value = mock_response

        chapters = generate_chapter_list(project, mock_client)

        assert len(chapters) == 2
        assert chapters[0]["number"] == 1
        assert chapters[0]["title"] == "Chapter One"

        # Verify file was saved
        content = project.read_file("chapter_outlines/chapter_list.md")
        assert "Chapter One" in content
        assert "Chapter Two" in content

    def test_generate_chapter_list_with_feedback(self, tmp_path):
        """Test chapter list regeneration with feedback."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.write_file("story_bible.md", "# Bible\n\nOverview")
        project.write_file("world.md", "# World\n\nDetails")
        project.save_character_index([{"name": "Alice", "role": "Hero"}])

        # Response with feedback incorporated
        response = """| # | Title | Purpose |
|---|-------|---------|
| 1 | Improved Chapter | Better introduction |"""

        mock_client = MagicMock(spec=APIClient)
        mock_client.generate.return_value = response

        chapters = generate_chapter_list_with_feedback(
            project, mock_client, "Make it better"
        )

        assert len(chapters) == 1
        assert chapters[0]["title"] == "Improved Chapter"

        # Verify feedback was included in prompt
        call_args = mock_client.generate.call_args
        prompt = call_args[1]["user_message"]
        assert "Make it better" in prompt


class TestGenerateChapterOutline:
    """Test chapter outline generation with mocked AI."""

    def test_generate_success_no_placeholders(self, tmp_path):
        """Test successful outline generation without placeholders."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.write_file("story_bible.md", "# Bible\n\nOverview")
        project.write_file("world.md", "# World\n\nDetails")
        project.save_character_index(
            [{"name": "Alice", "role": "Hero", "description": "Brave"}]
        )

        # Write chapter list
        chapter_list_content = """| # | Title | Purpose |
|---|-------|---------|
| 1 | Test Chapter | Introduction |"""
        project.write_file("chapter_outlines/chapter_list.md", chapter_list_content)

        # Mock AI response - no placeholders
        mock_outline = """# CHAPTER 1: TEST CHAPTER

## CHAPTER OVERVIEW

**POV Character:** Alice
**Setting:** The Castle
**Characters Present:** Alice, Bob

**Chapter Goal:** Begin the journey
**Emotional Arc:** Hopeful to determined

## SCENE BREAKDOWN

### Scene 1: Departure
**Setting:** The Castle
**POV:** Alice
**Action:** Alice prepares to leave. She gathers supplies. Bob wishes her luck.

### Scene 2: The Forest
**Setting:** The Forest
**POV:** Alice
**Action:** Alice enters the forest. She hears strange sounds. She finds a marker.

### Scene 3: Discovery
**Setting:** The Clearing
**POV:** Alice
**Action:** Alice reaches a clearing. She discovers an ancient ruin. She investigates.

## STORY CONNECTIONS

**Connection to the Seed Story / Prologue:** Follows from setup

**Connection to Chapter 2:** Sets up next chapter

## FORESHADOWING & CALLBACKS

- The ancient ruin holds secrets
- Reference to prologue events
"""

        mock_client = MagicMock(spec=APIClient)
        mock_client.generate.return_value = mock_outline

        chapters = [{"number": 1, "title": "Test Chapter", "purpose": "Introduction"}]

        outline = generate_chapter_outline(project, mock_client, chapters[0], chapters)

        assert "Alice" in outline
        assert "The Castle" in outline
        assert "Departure" in outline

        # Verify file was saved
        saved_outline = project.read_file("chapter_outlines/chapter_1.md")
        assert "Alice" in saved_outline

    def test_generate_with_placeholders_regenerates(self, tmp_path):
        """Test that outlines with placeholders trigger regeneration."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.write_file("story_bible.md", "# Bible\n\nOverview")
        project.write_file("world.md", "# World\n\nDetails")
        project.save_character_index([{"name": "Alice", "role": "Hero"}])

        chapter_list_content = """| # | Title | Purpose |
|---|-------|---------|
| 1 | Test Chapter | Introduction |"""
        project.write_file("chapter_outlines/chapter_list.md", chapter_list_content)

        # First response - with placeholders
        bad_outline = """# CHAPTER 1: TEST CHAPTER

## CHAPTER OVERVIEW

**POV Character:** [Specify]
**Setting:** [Location]
**Characters Present:** [List characters]

**Chapter Goal:** [Specify]
"""

        # Second response - without placeholders
        good_outline = """# CHAPTER 1: TEST CHAPTER

## CHAPTER OVERVIEW

**POV Character:** Alice
**Setting:** The Castle
**Characters Present:** Alice, Bob

**Chapter Goal:** Begin the journey
"""

        mock_client = MagicMock(spec=APIClient)
        mock_client.generate.side_effect = [bad_outline, good_outline]

        chapters = [{"number": 1, "title": "Test Chapter", "purpose": "Introduction"}]

        outline = generate_chapter_outline(project, mock_client, chapters[0], chapters)

        # Should have called generate twice (first failed, second succeeded)
        assert mock_client.generate.call_count == 2
        assert "Alice" in outline

    def test_generate_max_attempts_reached(self, tmp_path):
        """Test behavior when max attempts reached."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.write_file("story_bible.md", "# Bible\n\nOverview")
        project.write_file("world.md", "# World\n\nDetails")
        project.save_character_index([{"name": "Alice", "role": "Hero"}])

        chapter_list_content = """| # | Title | Purpose |
|---|-------|---------|
| 1 | Test Chapter | Introduction |"""
        project.write_file("chapter_outlines/chapter_list.md", chapter_list_content)

        # All responses have placeholders
        bad_outline = """# CHAPTER 1: TEST

**POV Character:** [Specify]
**Setting:** [Location]
"""

        mock_client = MagicMock(spec=APIClient)
        mock_client.generate.return_value = bad_outline

        chapters = [{"number": 1, "title": "Test Chapter", "purpose": "Introduction"}]

        outline = generate_chapter_outline(project, mock_client, chapters[0], chapters)

        # Should have tried max_attempts times
        assert mock_client.generate.call_count == 3
        # Should still save the best attempt
        saved = project.read_file("chapter_outlines/chapter_1.md")
        assert len(saved) > 0

    def test_generate_with_user_feedback(self, tmp_path):
        """Test generation with user feedback."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.write_file("story_bible.md", "# Bible\n\nOverview")
        project.write_file("world.md", "# World\n\nDetails")
        project.save_character_index([{"name": "Alice", "role": "Hero"}])

        chapter_list_content = """| # | Title | Purpose |
|---|-------|---------|
| 1 | Test Chapter | Introduction |"""
        project.write_file("chapter_outlines/chapter_list.md", chapter_list_content)

        # Response after feedback
        mock_outline = """# CHAPTER 1: TEST CHAPTER

## CHAPTER OVERVIEW

**POV Character:** Alice
**Setting:** The Castle

**Chapter Goal:** Begin the journey
"""

        mock_client = MagicMock(spec=APIClient)
        mock_client.generate.return_value = mock_outline

        chapters = [{"number": 1, "title": "Test Chapter", "purpose": "Introduction"}]

        outline = generate_chapter_outline(
            project,
            mock_client,
            chapters[0],
            chapters,
            feedback="Make it more exciting",
        )

        # Verify the feedback was included in the prompt
        call_args = mock_client.generate.call_args
        prompt = call_args[1]["user_message"]
        assert "Make it more exciting" in prompt

    def test_regeneration_notice_added(self, tmp_path):
        """Test that regeneration adds timestamp notice."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.write_file("story_bible.md", "# Bible\n\nOverview")
        project.write_file("world.md", "# World\n\nDetails")
        project.save_character_index([{"name": "Alice", "role": "Hero"}])

        chapter_list_content = """| # | Title | Purpose |
|---|-------|---------|
| 1 | Test Chapter | Introduction |"""
        project.write_file("chapter_outlines/chapter_list.md", chapter_list_content)

        mock_outline = """# CHAPTER 1: TEST CHAPTER

## CHAPTER OVERVIEW

**POV Character:** Alice
**Setting:** The Castle
"""

        mock_client = MagicMock(spec=APIClient)
        mock_client.generate.return_value = mock_outline

        chapters = [{"number": 1, "title": "Test Chapter", "purpose": "Introduction"}]

        outline = generate_chapter_outline(
            project, mock_client, chapters[0], chapters, feedback="Improve this"
        )

        # Check for regeneration notice
        saved = project.read_file("chapter_outlines/chapter_1.md")
        assert "regenerated with feedback" in saved.lower()


class TestRegenerateChapterOutline:
    """Test chapter outline regeneration."""

    def test_regenerate_from_chapter_list(self, tmp_path):
        """Test regeneration loads chapter info from list."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)

        # Create required files
        project.write_file("story_bible.md", "# Story Bible\n\nOverview")
        project.write_file("world.md", "# World\n\nDetails")
        project.save_character_index([{"name": "Alice", "role": "Hero"}])

        # Write chapter list
        chapter_list = """| # | Title | Purpose |
|---|-------|---------|
| 1 | First Chapter | Setup |
| 2 | Second Chapter | Action |"""
        project.write_file("chapter_outlines/chapter_list.md", chapter_list)

        mock_outline = """# CHAPTER 1: FIRST CHAPTER

## CHAPTER OVERVIEW

**POV Character:** Alice
**Setting:** The Castle
"""

        mock_client = MagicMock(spec=APIClient)
        mock_client.generate.return_value = mock_outline

        regenerate_chapter_outline(project, mock_client, 1)

        # Should have loaded chapter info from list
        call_args = mock_client.generate.call_args
        prompt = call_args[1]["user_message"]
        assert "First Chapter" in prompt
        assert "Setup" in prompt

    def test_regenerate_without_chapter_list(self, tmp_path):
        """Test regeneration falls back to file parsing."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)

        # Create required files
        project.write_file("story_bible.md", "# Story Bible\n\nOverview")
        project.write_file("world.md", "# World\n\nDetails")
        project.save_character_index([{"name": "Alice", "role": "Hero"}])

        # Write individual outline files (no chapter list)
        project.write_file(
            "chapter_outlines/chapter_1.md",
            "# CHAPTER 1: First Chapter\n\nOutline here.",
        )
        project.write_file(
            "chapter_outlines/chapter_2.md",
            "# CHAPTER 2: Second Chapter\n\nOutline here.",
        )

        mock_outline = """# CHAPTER 1: FIRST CHAPTER

## CHAPTER OVERVIEW

**POV Character:** Alice
"""

        mock_client = MagicMock(spec=APIClient)
        mock_client.generate.return_value = mock_outline

        regenerate_chapter_outline(project, mock_client, 1)

        # Should have generated successfully
        assert mock_client.generate.called

    def test_regenerate_with_feedback(self, tmp_path):
        """Test regeneration includes feedback in prompt."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)

        # Create required files
        project.write_file("story_bible.md", "# Story Bible\n\nOverview")
        project.write_file("world.md", "# World\n\nDetails")
        project.save_character_index([{"name": "Alice", "role": "Hero"}])

        chapter_list = """| # | Title | Purpose |
|---|-------|---------|
| 1 | Test Chapter | Intro |"""
        project.write_file("chapter_outlines/chapter_list.md", chapter_list)

        mock_outline = """# CHAPTER 1: TEST CHAPTER

## CHAPTER OVERVIEW

**POV Character:** Alice
"""

        mock_client = MagicMock(spec=APIClient)
        mock_client.generate.return_value = mock_outline

        feedback = "Make Alice more proactive"
        regenerate_chapter_outline(project, mock_client, 1, feedback=feedback)

        # Verify feedback was included
        call_args = mock_client.generate.call_args
        prompt = call_args[1]["user_message"]
        assert "Make Alice more proactive" in prompt

    def test_regenerate_nonexistent_chapter_raises_error(self, tmp_path):
        """Test that regenerating non-existent chapter raises error."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)

        chapter_list = """| # | Title | Purpose |
|---|-------|---------|
| 1 | Test Chapter | Intro |"""
        project.write_file("chapter_outlines/chapter_list.md", chapter_list)

        mock_client = MagicMock(spec=APIClient)

        with pytest.raises(ValueError, match="Chapter not found"):
            regenerate_chapter_outline(project, mock_client, 999)


class TestPlaceholderDetection:
    """Test placeholder detection in outlines."""

    def test_check_placeholders_finds_common_placeholders(self):
        """Test that common placeholders are detected."""
        from booksmith.pipeline.reviewer import check_placeholders

        outline = """
        **POV Character:** [Specify]
        **Setting:** [Location]
        **Action:** [Describe what happens]
        """

        count, examples = check_placeholders(outline)

        assert count >= 3
        assert len(examples) > 0
        assert any("[Specify]" in ex for ex in examples)

    def test_check_placeholders_finds_scene_placeholders(self):
        """Test that scene placeholders are detected."""
        from booksmith.pipeline.reviewer import check_placeholders

        outline = """
        ### Scene 1: [Opening]
        **Action:** [Describe action]
        """

        count, examples = check_placeholders(outline)

        assert count >= 2

    def test_check_placeholders_clean_outline(self):
        """Test that clean outline has no placeholders."""
        from booksmith.pipeline.reviewer import check_placeholders

        outline = """
        **POV Character:** Alice
        **Setting:** The Castle
        **Action:** Alice enters the castle and finds the treasure.
        """

        count, examples = check_placeholders(outline)

        assert count == 0
        assert len(examples) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
