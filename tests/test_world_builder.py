"""Unit tests for world_builder with mocked AI responses."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from booksmith.pipeline.world_builder import (
    generate_world,
    regenerate_world,
)
from booksmith.storage.project import Project


class TestGenerateWorld:
    """Test world guide generation."""

    def test_generate_world_basic(self, tmp_path):
        """Test basic world guide generation."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory content.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.write_file("story_bible.md", "# Bible\n\nOverview")

        mock_world = "# World Guide\n\nThis is a fantasy world."
        mock_client = MagicMock()
        mock_client.stream.return_value = iter(mock_world)

        with patch("booksmith.pipeline.world_builder.print_header"):
            with patch("booksmith.pipeline.world_builder.format_prompt") as mock_format:
                mock_format.return_value = ("system", "user")
                result = generate_world(project, mock_client)

                assert "fantasy world" in result
                # Should save to file
                assert project.file_exists("world.md")
                content = project.read_file("world.md")
                assert "fantasy world" in content

    def test_generate_world_with_extra_instruction(self, tmp_path):
        """Test world generation with extra instruction."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.write_file("story_bible.md", "# Bible\n\nOverview")

        mock_world = "# World\n\nContent"
        mock_client = MagicMock()
        mock_client.stream.return_value = iter(mock_world)

        with patch("booksmith.pipeline.world_builder.print_header"):
            with patch("booksmith.pipeline.world_builder.format_prompt") as mock_format:
                mock_format.return_value = ("system", "user")
                result = generate_world(
                    project, mock_client, extra_instruction="Make it more detailed"
                )

                # Should have been called
                mock_client.stream.assert_called_once()

    def test_generate_world_saves_to_file(self, tmp_path):
        """Test that generated world guide is saved to file."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.write_file("story_bible.md", "# Bible\n\nOverview")

        mock_world = "# World Guide\n\nDetailed world description"
        mock_client = MagicMock()
        mock_client.stream.return_value = iter(mock_world)

        with patch("booksmith.pipeline.world_builder.print_header"):
            with patch("booksmith.pipeline.world_builder.format_prompt") as mock_format:
                mock_format.return_value = ("system", "user")
                generate_world(project, mock_client)

                # Should save to file
                content = project.read_file("world.md")
                assert "Detailed world description" in content

    def test_generate_world_reads_story_bible(self, tmp_path):
        """Test that world generation reads story bible."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.write_file("story_bible.md", "# Bible\n\nSpecific bible content")

        mock_world = "# World\n\nContent"
        mock_client = MagicMock()
        mock_client.stream.return_value = iter(mock_world)

        with patch("booksmith.pipeline.world_builder.print_header"):
            with patch("booksmith.pipeline.world_builder.format_prompt") as mock_format:
                mock_format.return_value = ("system", "user")
                generate_world(project, mock_client)

                # Should have called format_prompt with story bible
                mock_format.assert_called_once()
                args = mock_format.call_args[1]
                assert "story_bible" in args
                assert "Specific bible content" in str(args)


class TestRegenerateWorld:
    """Test world guide regeneration."""

    def test_regenerate_world_basic(self, tmp_path):
        """Test basic world regeneration."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.write_file("story_bible.md", "# Bible\n\nOverview")

        mock_world = "# World Guide\n\nRegenerated world content"
        mock_client = MagicMock()
        mock_client.stream.return_value = iter(mock_world)

        with patch("booksmith.pipeline.world_builder.print_header"):
            with patch("booksmith.pipeline.world_builder.format_prompt") as mock_format:
                mock_format.return_value = ("system", "user")
                result = regenerate_world(project, mock_client)

                assert "Regenerated world content" in result
                # Should update the file
                content = project.read_file("world.md")
                assert "Regenerated world content" in content

    def test_regenerate_with_extra_instruction(self, tmp_path):
        """Test regeneration with extra instruction."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nStory.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.write_file("story_bible.md", "# Bible\n\nOverview")

        mock_world = "# World\n\nUpdated content"
        mock_client = MagicMock()
        mock_client.stream.return_value = iter(mock_world)

        with patch("booksmith.pipeline.world_builder.print_header"):
            with patch("booksmith.pipeline.world_builder.format_prompt") as mock_format:
                mock_format.return_value = ("system", "user")
                regenerate_world(
                    project, mock_client, extra_instruction="Add more detail"
                )

                # Should have called with extra instruction
                content = project.read_file("world.md")
                assert "Updated content" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
