from typing import Generator, Optional

from ..api_client import APIClient, format_prompt
from ..storage.project import Project
from ..ui.console import console, print_header


def generate_world(
    project: Project,
    client: APIClient,
    extra_instruction: Optional[str] = None,
) -> str:
    """Generate world guide from story bible."""
    print_header("Generating World Guide...")

    story_bible = project.read_file("story_bible.md")

    system_prompt, user_prompt = format_prompt(
        "world_builder",
        story_bible=story_bible,
    )

    if extra_instruction:
        user_prompt += f"\n\n---\n\nAdditional instruction: {extra_instruction}"

    world = client.stream(
        stage="world_builder",
        system=system_prompt,
        user_message=user_prompt,
        project_config=project.config,
    )

    content = ""
    for chunk in world:
        content += chunk

    project.write_file("world.md", content)

    return content


def regenerate_world(
    project: Project,
    client: APIClient,
    extra_instruction: Optional[str] = None,
) -> str:
    """Regenerate world guide with optional extra instruction."""
    return generate_world(project, client, extra_instruction)
