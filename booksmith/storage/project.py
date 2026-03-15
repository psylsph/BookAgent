import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from booksmith.api_client import ANTHROPIC_LOCAL_MODEL

DEFAULT_CONFIG = {
    "min_words_per_chapter": 2000,
    "model": ANTHROPIC_LOCAL_MODEL,
    "pov": "third person limited",
    "tense": "past",
    "tone": "literary",
}


class Project:
    def __init__(self, path: Path):
        self.path = path
        self._config: Optional[dict] = None

    @property
    def config(self) -> dict:
        if self._config is None:
            self._config = self.load_config()
        return self._config

    @property
    def title(self) -> str:
        return self.config.get("title", self.path.name)

    @property
    def status(self) -> str:
        return self.config.get("status", "initializing")

    @property
    def current_chapter(self) -> int:
        return self.config.get("current_chapter", 0)

    @property
    def total_chapters(self) -> int:
        return self.config.get("total_chapters_planned", 0)

    @property
    def approved_chapters(self) -> list[int]:
        return self.config.get("approved_chapters", [])

    @property
    def seed_file(self) -> str:
        return self.config.get("seed_file", "seed.md")

    @staticmethod
    def create(
        name: str, seed_path: Path, projects_dir: Optional[Path] = None
    ) -> "Project":
        """Create a new project with folder structure."""
        if projects_dir is None:
            projects_dir = Path.cwd() / "projects"

        project_path = projects_dir / name

        if project_path.exists():
            raise FileExistsError(f"Project already exists: {project_path}")

        project_path.mkdir(parents=True)
        (project_path / "characters").mkdir()
        (project_path / "chapter_outlines").mkdir()
        (project_path / "chapters").mkdir()
        (project_path / "reviews").mkdir()
        (project_path / "summaries").mkdir()

        seed_dest = project_path / "seed.md"
        shutil.copy2(seed_path, seed_dest)

        title = name.replace("_", " ").replace("-", " ").title()
        config = {
            "title": title,
            "seed_file": "seed.md",
            "status": "writing",
            "current_chapter": 0,
            "total_chapters_planned": 0,
            "approved_chapters": [],
            **DEFAULT_CONFIG,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }

        (project_path / "project.json").write_text(json.dumps(config, indent=2))

        return Project(project_path)

    @staticmethod
    def load(path: Path) -> "Project":
        """Load an existing project."""
        if not (path / "project.json").exists():
            raise FileNotFoundError(f"No project found at: {path}")
        return Project(path)

    def load_config(self) -> dict:
        """Load project configuration."""
        config_path = self.path / "project.json"
        if not config_path.exists():
            raise FileNotFoundError(f"No project config at: {config_path}")
        return json.loads(config_path.read_text())

    def save_config(self, config: Optional[dict] = None):
        """Save project configuration."""
        if config is None:
            config = self._config
        if config is None:
            config = {}
        config["updated_at"] = datetime.now().isoformat()
        (self.path / "project.json").write_text(json.dumps(config, indent=2))
        self._config = config

    def update_chapter_status(self, chapter_num: int, approved: bool = False):
        """Update the current chapter and optionally mark as approved."""
        config = self.load_config()

        if approved:
            if chapter_num not in config.get("approved_chapters", []):
                config.setdefault("approved_chapters", []).append(chapter_num)

        config["current_chapter"] = chapter_num
        self.save_config(config)

    def set_total_chapters(self, count: int):
        """Set the total planned chapter count."""
        config = self.load_config()
        config["total_chapters_planned"] = count
        self.save_config(config)

    def set_status(self, status: str):
        """Update project status."""
        config = self.load_config()
        config["status"] = status
        self.save_config(config)

    def read_file(self, filename: str) -> str:
        """Read a file from the project."""
        file_path = self.path / filename
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        return file_path.read_text()

    def write_file(self, filename: str, content: str):
        """Write content to a file in the project."""
        file_path = self.path / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)

    def file_exists(self, filename: str) -> bool:
        """Check if a file exists in the project."""
        return (self.path / filename).exists()

    def get_characters(self) -> list[dict]:
        """Load character index."""
        index_path = self.path / "characters" / "character_index.json"
        if not index_path.exists():
            return []
        return json.loads(index_path.read_text())

    def save_character_index(self, characters: list[dict]):
        """Save character index."""
        index_path = self.path / "characters" / "character_index.json"
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(json.dumps(characters, indent=2))

    def get_chapter_outline(self, chapter_num: int) -> Optional[str]:
        """Load a chapter outline."""
        outline_path = self.path / "chapter_outlines" / f"chapter_{chapter_num}.md"
        if not outline_path.exists():
            return None
        return outline_path.read_text()

    def get_approved_chapter(self, chapter_num: int) -> Optional[str]:
        """Load an approved chapter."""
        chapter_path = self.path / "chapters" / f"chapter_{chapter_num}.md"
        if not chapter_path.exists():
            return None
        return chapter_path.read_text()

    def get_macro_summary(self) -> Optional[str]:
        """Load macro summary."""
        summary_path = self.path / "summaries" / "macro_summary.md"
        if not summary_path.exists():
            return None
        return summary_path.read_text()


def find_project(name: str, projects_dir: Optional[Path] = None) -> Project:
    """Find a project by name."""
    if projects_dir is None:
        projects_dir = Path.cwd() / "projects"

    project_path = projects_dir / name

    if not project_path.exists():
        raise FileNotFoundError(f"Project not found: {name}")

    return Project.load(project_path)


def list_projects(projects_dir: Optional[Path] = None) -> list[Project]:
    """List all projects."""
    if projects_dir is None:
        projects_dir = Path.cwd() / "projects"

    if not projects_dir.exists():
        return []

    projects = []
    for path in projects_dir.iterdir():
        if path.is_dir() and (path / "project.json").exists():
            projects.append(Project.load(path))

    return sorted(projects, key=lambda p: p.config.get("updated_at", ""), reverse=True)
