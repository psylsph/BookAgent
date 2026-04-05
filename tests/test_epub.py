"""Unit tests for epub export functionality."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from booksmith.export.epub import (
    get_chapters_in_order,
    create_title_page,
    create_chapter_break,
    convert_to_xhtml,
    create_epub,
)
from booksmith.storage.project import Project


class TestGetChaptersInOrder:
    """Test getting chapters in order."""

    def test_get_chapters_empty(self, tmp_path):
        """Test with no approved chapters."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)

        chapters = get_chapters_in_order(project)
        assert len(chapters) == 0

    def test_get_chapters_in_order(self, tmp_path):
        """Test getting chapters in numerical order."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.set_total_chapters(3)

        # Add chapters out of order
        project.write_file("chapters/chapter_3.md", "# Chapter 3\n\nContent 3")
        project.write_file("chapters/chapter_1.md", "# Chapter 1\n\nContent 1")
        project.write_file("chapters/chapter_2.md", "# Chapter 2\n\nContent 2")

        project.update_chapter_status(3, approved=True)
        project.update_chapter_status(1, approved=True)
        project.update_chapter_status(2, approved=True)

        chapters = get_chapters_in_order(project)
        assert len(chapters) == 3
        assert chapters[0][0] == 1
        assert chapters[1][0] == 2
        assert chapters[2][0] == 3

    def test_get_chapters_skips_missing(self, tmp_path):
        """Test that missing chapters are skipped."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.set_total_chapters(3)

        # Only create chapters 1 and 3
        project.write_file("chapters/chapter_1.md", "# Chapter 1\n\nContent 1")
        project.write_file("chapters/chapter_3.md", "# Chapter 3\n\nContent 3")

        project.update_chapter_status(1, approved=True)
        project.update_chapter_status(3, approved=True)
        # Chapter 2 is in approved_chapters but file doesn't exist
        project.config["approved_chapters"] = [1, 2, 3]
        project.save_config(project.config)

        chapters = get_chapters_in_order(project)
        assert len(chapters) == 2
        assert chapters[0][0] == 1
        assert chapters[1][0] == 3


class TestCreateTitlePage:
    """Test title page creation."""

    def test_create_title_page(self, tmp_path):
        """Test creating title page."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)

        title_page = create_title_page(project)

        assert title_page.title == "Test"
        assert "Test" in title_page.content
        assert "BookSmith" in title_page.content


class TestCreateChapterBreak:
    """Test chapter break page creation."""

    def test_create_chapter_break(self, tmp_path):
        """Test creating chapter break page."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)

        chapter_break = create_chapter_break(project, 1, "The Beginning")

        assert chapter_break.title == "Chapter 1"
        assert "Chapter 1" in chapter_break.content
        assert "The Beginning" in chapter_break.content


class TestConvertToXhtml:
    """Test markdown to XHTML conversion."""

    def test_convert_headers(self):
        """Test header conversion."""
        content = """# Title 1
## Title 2
### Title 3"""
        result = convert_to_xhtml(content)

        assert '<h1 style="color: #4A3728;">Title 1</h1>' in result
        assert '<h2 style="color: #4A3728;">Title 2</h2>' in result
        assert '<h3 style="color: #4A3728;">Title 3</h3>' in result

    def test_convert_bold_italic(self):
        """Test bold and italic conversion."""
        content = """**bold text**
*italic text*
***bold italic***"""
        result = convert_to_xhtml(content)

        assert "<strong>bold text</strong>" in result
        assert "<em>italic text</em>" in result
        assert "<strong><em>bold italic</em></strong>" in result

    def test_escape_html(self):
        """Test HTML escaping."""
        content = "Text with <tag> & entities"
        result = convert_to_xhtml(content)

        assert "&lt;tag&gt;" in result
        assert "&amp;" in result

    def test_convert_paragraphs(self):
        """Test paragraph conversion."""
        content = """Line 1
Line 2

Line 3"""
        result = convert_to_xhtml(content)

        assert '<p style="text-indent: 1.5em;' in result
        assert "</p>" in result

    def test_convert_mixed_content(self):
        """Test mixed markdown content."""
        content = """# Chapter 1

This is a paragraph with **bold** and *italic* text.

## Section Header

Another paragraph here."""
        result = convert_to_xhtml(content)

        assert '<h1 style="color: #4A3728;">Chapter 1</h1>' in result
        assert "<strong>bold</strong>" in result
        assert "<em>italic</em>" in result
        assert '<h2 style="color: #4A3728;">Section Header</h2>' in result


class TestCreateEpub:
    """Test EPUB creation."""

    def test_create_epub_with_chapters(self, tmp_path):
        """Test creating EPUB with chapters."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.set_total_chapters(2)

        # Create and approve chapters
        project.write_file("chapters/chapter_1.md", "# Chapter 1\n\nContent 1")
        project.write_file("chapters/chapter_2.md", "# Chapter 2\n\nContent 2")

        project.update_chapter_status(1, approved=True)
        project.update_chapter_status(2, approved=True)

        output_path = tmp_path / "output.epub"

        with patch("ebooklib.epub.write_epub") as mock_write:
            result = create_epub(project, output_path)

            assert result == output_path
            mock_write.assert_called_once()

    def test_create_epub_no_chapters(self, tmp_path):
        """Test creating EPUB with no chapters raises error."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)

        with pytest.raises(ValueError, match="No approved chapters"):
            create_epub(project)

    def test_create_epub_default_output_path(self, tmp_path):
        """Test that default output path is used if none provided."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.set_total_chapters(1)

        project.write_file("chapters/chapter_1.md", "# Chapter 1\n\nContent")
        project.update_chapter_status(1, approved=True)

        with patch("ebooklib.epub.write_epub") as mock_write:
            result = create_epub(project, None)

            # Should default to project path
            assert "test" in str(result).lower()

    def test_create_epub_sets_metadata(self, tmp_path):
        """Test that EPUB metadata is set correctly."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# My Book\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.set_total_chapters(1)

        project.write_file("chapters/chapter_1.md", "# Chapter 1\n\nContent")
        project.update_chapter_status(1, approved=True)

        output_path = tmp_path / "output.epub"

        with patch("ebooklib.epub.write_epub"):
            with patch("ebooklib.epub.EpubBook") as mock_book_class:
                mock_book = MagicMock()
                mock_book_class.return_value = mock_book

                create_epub(project, output_path)

                # Should set metadata
                mock_book.set_identifier.assert_called()
                # The title comes from config, which might be "test" (project name)
                mock_book.set_title.assert_called()
                mock_book.set_language.assert_called_with("en")
                mock_book.add_author.assert_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
