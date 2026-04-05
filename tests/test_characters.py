"""Unit tests for characters module with mocked AI responses."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from booksmith.pipeline.characters import (
    parse_character_list,
    _normalize_character_keys,
    extract_seed_character_names,
    generate_character_list,
    generate_character_profile,
    regenerate_character,
)
from booksmith.storage.project import Project


class TestParseCharacterList:
    """Test character list parsing."""

    def test_parse_json_in_code_block(self):
        """Test parsing JSON from code block."""
        text = """
Here are the characters:

```json
[
    {"name": "Alice", "role": "Hero", "description": "Brave adventurer"},
    {"name": "Bob", "role": "Villain", "description": "Evil wizard"}
]
```
"""
        characters = parse_character_list(text)
        assert len(characters) == 2
        assert characters[0]["name"] == "Alice"
        assert characters[0]["role"] == "Hero"
        assert characters[1]["name"] == "Bob"

    def test_parse_json_array(self):
        """Test parsing JSON array without code block."""
        text = """[{"name": "Alice", "role": "Hero", "description": "Brave"}]"""
        characters = parse_character_list(text)
        assert len(characters) == 1
        assert characters[0]["name"] == "Alice"

    def test_parse_line_format(self):
        """Test parsing line-by-line format."""
        text = """
Alice: Brave hero
Bob: Evil villain
Charlie: Wise mentor
"""
        characters = parse_character_list(text)
        assert len(characters) >= 3
        assert any(c["name"] == "Alice" for c in characters)
        # Check that at least one character has the expected role
        alice = next(c for c in characters if c["name"] == "Alice")
        assert alice["role"] == "Character"
        assert alice["description"] == "Brave hero"

    def test_parse_mixed_case_names(self):
        """Test parsing with various separators."""
        text = """
Alice: The hero
Bob — The villain
Charlie – The mentor
"""
        characters = parse_character_list(text)
        assert len(characters) == 3
        assert characters[0]["name"] == "Alice"
        assert characters[1]["name"] == "Bob"
        assert characters[2]["name"] == "Charlie"

    def test_parse_ignores_headers(self):
        """Test that headers are ignored."""
        text = """
# Character List

Alice: Hero

## Details
"""
        characters = parse_character_list(text)
        assert len(characters) >= 1
        assert any(c["name"] == "Alice" for c in characters)

    def test_parse_empty_text(self):
        """Test parsing empty text."""
        characters = parse_character_list("")
        assert len(characters) == 0

    def test_parse_invalid_json(self):
        """Test that invalid JSON falls back to line parsing."""
        text = """
Some text with [brackets]

Alice: Hero
"""
        characters = parse_character_list(text)
        assert len(characters) >= 1
        assert any(c["name"] == "Alice" for c in characters)


class TestNormalizeCharacterKeys:
    """Test character key normalization."""

    def test_normalize_capitalized_keys(self):
        """Test normalizing capitalized keys."""
        characters = [
            {"Name": "Alice", "Role": "Hero", "Description": "Brave"},
        ]
        normalized = _normalize_character_keys(characters)
        assert normalized[0]["name"] == "Alice"
        assert normalized[0]["role"] == "Hero"
        assert normalized[0]["description"] == "Brave"

    def test_normalize_mixed_case(self):
        """Test normalizing mixed case keys."""
        characters = [
            {"NAME": "Alice", "Role": "Hero"},
        ]
        normalized = _normalize_character_keys(characters)
        assert "name" in normalized[0]
        assert "role" in normalized[0]

    def test_preserves_extra_keys(self):
        """Test that extra keys are preserved."""
        characters = [
            {"name": "Alice", "Age": "25", "Extra": "data"},
        ]
        normalized = _normalize_character_keys(characters)
        assert normalized[0]["name"] == "Alice"
        assert normalized[0]["age"] == "25"
        assert normalized[0]["extra"] == "data"


class TestExtractSeedCharacterNames:
    """Test character name extraction from seed."""

    def test_extract_simple_names(self):
        """Test extracting simple character names."""
        seed = """
Alice walked into the room. Bob was waiting for her.
Charlie stood by the window.
"""
        names = extract_seed_character_names(seed)
        assert "Alice" in names
        assert "Bob" in names
        assert "Charlie" in names

    def test_extract_multiword_names(self):
        """Test extracting multi-word names."""
        seed = """
Mary Jane entered the room. Doctor Strange followed.
"""
        names = extract_seed_character_names(seed)
        # Multi-word names should be captured
        assert len(names) > 0

    def test_filters_common_words(self):
        """Test that common words are filtered out."""
        seed = """
The King and Queen walked through the castle.
Alice followed them.
"""
        names = extract_seed_character_names(seed)
        # "The", "King", "Queen" should be filtered
        assert "Alice" in names
        assert "The" not in names

    def test_removes_duplicates(self):
        """Test that duplicate names are removed."""
        seed = """
Alice talked to Bob. Bob talked to Charlie.
Alice then left.
"""
        names = extract_seed_character_names(seed)
        # Each name should appear only once
        assert names.count("Alice") == 1
        assert names.count("Bob") == 1


class TestGenerateCharacterList:
    """Test character list generation."""

    def test_generate_character_list_basic(self, tmp_path):
        """Test basic character list generation."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nAlice and Bob are characters.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.write_file("story_bible.md", "# Bible\n\nOverview")
        project.write_file("world.md", "# World\n\nDetails")

        # Mock character list generation
        mock_response = """```json
[
    {"name": "Alice", "role": "Hero", "description": "Brave"},
    {"name": "Bob", "role": "Villain", "description": "Evil"}
]
```"""
        mock_client = MagicMock()
        mock_client.generate = MagicMock(return_value=mock_response)

        with patch("booksmith.pipeline.characters.print_header"):
            with patch("booksmith.pipeline.characters.format_prompt") as mock_format:
                mock_format.return_value = ("system", "user")
                result = generate_character_list(project, mock_client)

                assert len(result) == 2
                assert result[0]["name"] == "Alice"
                assert result[1]["name"] == "Bob"

    def test_generate_character_list_saves_to_file(self, tmp_path):
        """Test that character list is saved to file."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nCharacters.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.write_file("story_bible.md", "# Bible\n\nOverview")
        project.write_file("world.md", "# World\n\nDetails")

        mock_response = """```json
[{"name": "Alice", "role": "Hero", "description": "Brave"}]
```"""
        mock_client = MagicMock()
        mock_client.generate = MagicMock(return_value=mock_response)

        with patch("booksmith.pipeline.characters.print_header"):
            with patch("booksmith.pipeline.characters.format_prompt") as mock_format:
                mock_format.return_value = ("system", "user")
                generate_character_list(project, mock_client)

                # Should save to file
                assert project.file_exists("characters/character_list.md")
                content = project.read_file("characters/character_list.md")
                assert "Alice" in content


class TestGenerateCharacterProfile:
    """Test character profile generation."""

    def test_generate_profile_basic(self, tmp_path):
        """Test basic profile generation."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nAlice is a hero.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.write_file("story_bible.md", "# Bible\n\nOverview")
        project.write_file("world.md", "# World\n\nDetails")

        character = {"name": "Alice", "role": "Hero", "description": "Brave"}
        all_characters = [character]

        mock_profile = "# Alice\n\nAlice is a brave hero."
        mock_client = MagicMock()
        mock_client.stream.return_value = iter(mock_profile)

        with patch("booksmith.pipeline.characters.print_header"):
            result = generate_character_profile(
                project, mock_client, character, all_characters
            )

            assert "Alice is a brave hero" in result
            # Should save to file
            assert project.file_exists("characters/Alice.md")

    def test_generate_profile_creates_directory(self, tmp_path):
        """Test that profile generation creates characters directory."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nAlice.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.write_file("story_bible.md", "# Bible\n\nOverview")
        project.write_file("world.md", "# World\n\nDetails")

        character = {"name": "Alice", "role": "Hero", "description": "Brave"}
        all_characters = [character]

        mock_profile = "# Alice\n\nProfile"
        mock_client = MagicMock()
        mock_client.stream.return_value = iter(mock_profile)

        with patch("booksmith.pipeline.characters.print_header"):
            generate_character_profile(project, mock_client, character, all_characters)

            # Should create directory and file
            assert project.file_exists("characters/Alice.md")


class TestRegenerateCharacter:
    """Test character regeneration."""

    def test_regenerate_character_basic(self, tmp_path):
        """Test basic character regeneration."""
        seed_file = tmp_path / "seed.md"
        seed_file.write_text("# Test\n\nAlice.")

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        project = Project.create("test", seed_file, projects_dir)
        project.write_file("story_bible.md", "# Bible\n\nOverview")
        project.write_file("world.md", "# World\n\nDetails")

        # Create existing profile
        project.write_file("characters/Alice.md", "# Alice\n\nOld profile")
        project.save_character_index(
            [{"name": "Alice", "role": "Hero", "description": "Brave"}]
        )

        mock_new_profile = "# Alice\n\nUpdated profile"
        mock_client = MagicMock()
        mock_client.stream.return_value = iter(mock_new_profile)

        with patch("booksmith.pipeline.characters.print_header"):
            result = regenerate_character(project, mock_client, "Alice")

            assert "Updated profile" in result
            # Should update the file
            content = project.read_file("characters/Alice.md")
            assert "Updated profile" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
