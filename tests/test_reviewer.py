"""Unit tests for reviewer with mocked AI responses."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from booksmith.pipeline.reviewer import (
    check_placeholders,
    extract_score,
    generate_review,
    get_review,
    generate_outline_review,
)
from booksmith.storage.project import Project


class TestCheckPlaceholders:
    """Test placeholder detection."""

    def test_no_placeholders(self):
        """Test outline without placeholders."""
        outline = """
# Chapter 1

This is a proper outline with specific details.
- Scene 1: Alice enters the castle
- Scene 2: She meets the king
"""
        count, examples = check_placeholders(outline)
        assert count == 0
        assert len(examples) == 0

    def test_single_placeholder(self):
        """Test outline with one placeholder."""
        outline = """
# Chapter 1

- Scene 1: [Specify the opening action]
- Scene 2: Alice meets the king
"""
        count, examples = check_placeholders(outline)
        assert count == 1
        assert len(examples) == 1
        assert "[Specify the opening action]" in examples[0]

    def test_multiple_placeholders(self):
        """Test outline with multiple placeholders."""
        outline = """
# Chapter 1

- Scene 1: [Specify the opening action]
- Scene 2: [Describe the setting]
- Scene 3: [Character name] enters
- Scene 4: [Location details]
"""
        count, examples = check_placeholders(outline)
        assert count == 4
        assert len(examples) == 4

    def test_various_placeholder_types(self):
        """Test detection of various placeholder patterns."""
        outline = """
# Chapter 1

- [Specify the opening scene description]
- [Character name goes here]
- [Describe the location setting]
- [Describe the action sequence]
- [Describe the escalation moment]
- [Describe the climax event]
- [Describe the resolution outcome]
- [Foreshadowing element goes here]
- [Callback reference goes here]
- [SCENE 1 breakdown]
- [POV character perspective]
- [Describe the setting details]
"""
        count, examples = check_placeholders(outline)
        assert count == 12
        assert len(examples) == 10  # Limited to 10

    def test_limits_examples_to_ten(self):
        """Test that only first 10 examples are returned."""
        outline = "\n".join([f"- [Specify placeholder {i}]" for i in range(15)])
        count, examples = check_placeholders(outline)
        assert count == 15
        assert len(examples) == 10


class TestExtractScore:
    """Test score extraction from review text."""

    def test_extract_score_numeric(self):
        """Test extracting numeric score."""
        review = "Good chapter. Score: 8/10"
        score = extract_score(review)
        assert score == 8.0

    def test_extract_score_decimal(self):
        """Test extracting decimal score."""
        review = "Excellent work. Rating: 8.5 out of 10"
        score = extract_score(review)
        assert score == 8.5

    def test_extract_score_various_formats(self):
        """Test extracting score from various formats."""
        formats = [
            ("Score: 7/10", 7.0),
            ("Rating: 7.5 out of 10", 7.5),
            ("quality: 9", 9.0),
            ("overall: 8/10", 8.0),
            ("final score: 6.5", 6.5),
        ]
        for text, expected in formats:
            score = extract_score(text)
            assert score == expected

    def test_extract_score_word_numbers(self):
        """Test extracting score from word numbers."""
        formats = [
            ("seven out of 10", 7.0),
            ("eight out of 10", 8.0),
            ("nine out of 10", 9.0),
        ]
        for text, expected in formats:
            score = extract_score(text)
            assert score == expected

    def test_extract_score_no_match(self):
        """Test when no score is found."""
        review = "Good chapter without a score"
        score = extract_score(review)
        assert score is None

    def test_extract_score_out_of_range(self):
        """Test that out-of-range scores are ignored."""
        review = "Score: 15/10"
        score = extract_score(review)
        assert score is None


class TestGenerateReview:
    """Test chapter review generation."""

    def test_generate_review_basic(self, tmp_path):
        """Test basic review generation."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.set_total_chapters(3)
        project.write_file("story_bible.md", "# Bible\n\nOverview")
        project.write_file("world.md", "# World\n\nDetails")
        project.save_character_index([{"name": "Alice", "role": "Hero"}])

        # Create chapter outline
        outline = """# CHAPTER 1: Test Chapter

**POV Character:** Alice
**Setting:** The Castle
"""
        project.write_file("chapter_outlines/chapter_1.md", outline)

        # Create chapter draft
        draft = "# Chapter 1\n\nOnce upon a time..."
        project.write_file("chapters/chapter_1_draft.md", draft)

        # Mock review generation
        mock_review = "Good chapter. Score: 8/10"
        mock_client = MagicMock()
        mock_client.stream.return_value = iter(mock_review)

        with patch("booksmith.pipeline.reviewer.print_header"):
            with patch("booksmith.pipeline.reviewer.format_prompt") as mock_format:
                mock_format.return_value = ("system", "user")
                review, score = generate_review(project, mock_client, 1)

                assert "Good chapter" in review
                assert score == 8.0
                # Should save review
                assert project.file_exists("reviews/chapter_1_review.md")

    def test_generate_review_uses_final_if_no_draft(self, tmp_path):
        """Test that final version is used if draft doesn't exist."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.set_total_chapters(3)
        project.write_file("story_bible.md", "# Bible\n\nOverview")
        project.write_file("world.md", "# World\n\nDetails")
        project.save_character_index([{"name": "Alice", "role": "Hero"}])

        # Create chapter outline
        outline = """# CHAPTER 1: Test Chapter

**POV Character:** Alice
"""
        project.write_file("chapter_outlines/chapter_1.md", outline)

        # Create final version (not draft)
        final = "# Chapter 1\n\nFinal version"
        project.write_file("chapters/chapter_1.md", final)

        mock_review = "Review. Score: 7/10"
        mock_client = MagicMock()
        mock_client.stream.return_value = iter(mock_review)

        with patch("booksmith.pipeline.reviewer.print_header"):
            with patch("booksmith.pipeline.reviewer.format_prompt") as mock_format:
                mock_format.return_value = ("system", "user")
                review, score = generate_review(project, mock_client, 1)

                assert score == 7.0

    def test_generate_review_default_score(self, tmp_path):
        """Test default score when extraction fails."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.set_total_chapters(3)
        project.write_file("story_bible.md", "# Bible\n\nOverview")
        project.write_file("world.md", "# World\n\nDetails")
        project.save_character_index([{"name": "Alice", "role": "Hero"}])

        # Create chapter outline and draft
        outline = """# CHAPTER 1: Test Chapter

**POV Character:** Alice
"""
        project.write_file("chapter_outlines/chapter_1.md", outline)
        project.write_file("chapters/chapter_1_draft.md", "# Chapter 1\n\nContent")

        # Mock review without score
        mock_review = "Good chapter but no score mentioned"
        mock_client = MagicMock()
        mock_client.stream.return_value = iter(mock_review)

        with patch("booksmith.pipeline.reviewer.print_header"):
            with patch("booksmith.pipeline.reviewer.format_prompt") as mock_format:
                mock_format.return_value = ("system", "user")
                review, score = generate_review(project, mock_client, 1)

                # Should default to 6.0
                assert score == 6.0


class TestGetReview:
    """Test getting existing reviews."""

    def test_get_existing_review(self, tmp_path):
        """Test retrieving existing review."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.set_total_chapters(3)

        # Create existing review
        review = "Good chapter. Score: 8/10"
        project.write_file("reviews/chapter_1_review.md", review)

        retrieved_review, score = get_review(project, 1)

        assert "Good chapter" in retrieved_review
        assert score == 8.0

    def test_get_nonexistent_review(self, tmp_path):
        """Test when review doesn't exist."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.set_total_chapters(3)

        review, score = get_review(project, 1)

        assert review is None
        assert score is None


class TestGenerateOutlineReview:
    """Test outline review generation."""

    def test_generate_outline_review_basic(self, tmp_path):
        """Test basic outline review generation."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.set_total_chapters(3)
        project.write_file("story_bible.md", "# Bible\n\nOverview")
        project.write_file("world.md", "# World\n\nDetails")
        project.save_character_index([{"name": "Alice", "role": "Hero"}])

        # Create chapter outline
        outline = """# CHAPTER 1: Test Chapter

**POV Character:** Alice
**Setting:** The Castle

**Chapter Goal:** Begin journey
"""
        project.write_file("chapter_outlines/chapter_1.md", outline)

        # Mock review generation
        mock_review = "Good outline. Score: 8/10"
        mock_client = MagicMock()
        mock_client.stream.return_value = iter(mock_review)

        with patch("booksmith.pipeline.reviewer.print_header"):
            review, score = generate_outline_review(project, mock_client, 1)

            assert "Good outline" in review
            assert score == 8.0
            # Should save review
            assert project.file_exists("reviews/chapter_1_outline_review.md")

    def test_outline_review_with_placeholders(self, tmp_path):
        """Test outline review detects placeholders."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.set_total_chapters(3)
        project.write_file("story_bible.md", "# Bible\n\nOverview")
        project.write_file("world.md", "# World\n\nDetails")
        project.save_character_index([{"name": "Alice", "role": "Hero"}])

        # Create outline with placeholders
        outline = """# CHAPTER 1: Test Chapter

- Scene 1: [Specify the opening]
- Scene 2: [Describe the setting]
- Scene 3: [Character name] enters
- Scene 4: [Action details]
- Scene 5: [Location specifics]
"""
        project.write_file("chapter_outlines/chapter_1.md", outline)

        # Mock review generation
        mock_review = "Outline has placeholders. Score: 7/10"
        mock_client = MagicMock()
        mock_client.stream.return_value = iter(mock_review)

        with patch("booksmith.pipeline.reviewer.print_header"):
            review, score = generate_outline_review(project, mock_client, 1)

            # Score should be capped at 3.0 due to >3 placeholders
            assert score == 3.0
            assert "placeholders found" in review.lower()

    def test_outline_review_default_score(self, tmp_path):
        """Test default score when extraction fails."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.set_total_chapters(3)
        project.write_file("story_bible.md", "# Bible\n\nOverview")
        project.write_file("world.md", "# World\n\nDetails")
        project.save_character_index([{"name": "Alice", "role": "Hero"}])

        # Create chapter outline
        outline = """# CHAPTER 1: Test Chapter

**POV Character:** Alice
"""
        project.write_file("chapter_outlines/chapter_1.md", outline)

        # Mock review without score
        mock_review = "Good outline but no score mentioned"
        mock_client = MagicMock()
        mock_client.stream.return_value = iter(mock_review)

        with patch("booksmith.pipeline.reviewer.print_header"):
            review, score = generate_outline_review(project, mock_client, 1)

            # Should default to 6.0
            assert score == 6.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
