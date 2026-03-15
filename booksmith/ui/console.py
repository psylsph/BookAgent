import os
import subprocess
from typing import Generator, Optional

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Confirm, Prompt


console = Console()


def print_header(text: str):
    """Print a header message."""
    console.print(f"[cyan]{text}[/cyan]")


def print_success(text: str):
    """Print a success message."""
    console.print(f"[green]{text}[/green]")


def print_error(text: str):
    """Print an error message."""
    console.print(f"[red]{text}[/red]")


def print_warning(text: str):
    """Print a warning message."""
    console.print(f"[yellow]{text}[/yellow]")


def print_panel(content: str, title: str, border_style: str = "cyan"):
    """Print content in a panel."""
    console.print(Panel(content, title=title, border_style=border_style))


def print_markdown(
    content: str, title: Optional[str] = None, border_style: str = "cyan"
):
    """Print markdown content in a panel."""
    panel = Panel(
        Markdown(content),
        title=title,
        border_style=border_style,
    )
    console.print(panel)


def stream_to_panel(
    generator: Generator[str, None, None],
    title: str,
    border_style: str = "blue",
) -> str:
    """Stream content to a live panel and return the full text."""
    buffer = ""
    with Live(console=console, refresh_per_second=15) as live:
        for chunk in generator:
            buffer += chunk
            live.update(Panel(buffer, title=title, border_style=border_style))
    return buffer


def ask_approval(prompt: str = "What would you like to do?") -> str:
    """Ask for approval with [A]pprove / [E]dit / [R]egenerate options."""
    choice = Prompt.ask(
        f"{prompt} [[A]pprove/[E]dit/[R]egenerate]",
        choices=["A", "E", "R"],
        default="A",
    )
    return choice


def ask_chapter_approval(prompt: str = "What would you like to do?") -> str:
    """Ask for chapter approval with [A]pprove / [R]egenerate / [F]eedback / [E]dit / [S]kip options."""
    choice = Prompt.ask(
        f"{prompt} [[A]pprove/[R]egenerate/[F]eedback/[E]dit/[S]kip]",
        choices=["A", "R", "F", "E", "S"],
        default="A",
    )
    return choice


def ask_choice(prompt: str, choices: list[str], default: Optional[str] = None) -> str:
    """Ask user to choose from a list of options with full words."""
    if default is None:
        default = choices[0]

    # Map choices to their full words
    word_map = {
        "A": "pprove",
        "R": "egenerate",
        "F": "eedback",
        "E": "dit",
        "S": "kip",
        "C": "ontinue",
    }

    choice_parts = []
    for c in choices:
        word = word_map.get(c, c.lower())
        if c == default:
            choice_parts.append(f"[{c}]{word}*")
        else:
            choice_parts.append(f"[{c}]{word}")

    choice_str = "/".join(choice_parts)

    # Accept both upper and lowercase
    choices_lower = [c.lower() for c in choices]
    choices_all = choices + choices_lower

    result = Prompt.ask(
        f"{prompt} {choice_str}",
        choices=choices_all,
        default=default.upper(),
        show_choices=False,
    )
    return result.upper() if result else choices[0]


def confirm(prompt: str, default: bool = False) -> bool:
    """Ask for confirmation."""
    return Confirm.ask(prompt, default=default)


def edit_in_editor(file_path: str) -> bool:
    """Open a file in $EDITOR and return True if changes were made."""
    editor = os.environ.get("EDITOR")

    if not editor:
        console.print(
            "[yellow]$EDITOR not set. Please edit the file manually and press Enter.[/yellow]"
        )
        input()
        return True

    try:
        subprocess.run([editor, file_path], check=True)
        return True
    except subprocess.CalledProcessError:
        return False


def count_words(text: str) -> int:
    """Count words in text."""
    return len(text.split())


def display_diff(old_text: str, new_text: str, title: str = "Changes"):
    """Display a simple diff of changes."""
    old_lines = old_text.split("\n")
    new_lines = new_text.split("\n")

    console.print(f"\n[cyan]{title}[/cyan]")
    console.print(f"[dim]Lines removed: {len(old_lines)} → {len(new_lines)}[/dim]")
    console.print(
        f"[dim]Words: {count_words(old_text)} → {count_words(new_text)}[/dim]\n"
    )


def display_project_status(project):
    """Display project status."""
    config = project.config

    console.print(
        Panel(
            f"[bold]{config['title']}[/bold]\n\n"
            f"Status: {config['status']}\n"
            f"Current Chapter: {config.get('current_chapter', 0)}\n"
            f"Approved Chapters: {len(config.get('approved_chapters', []))}\n"
            f"Total Chapters Planned: {config.get('total_chapters_planned', 0)}\n"
            f"Min Words per Chapter: {config.get('min_words_per_chapter', 2000)}\n"
            f"Model: {config.get('model', 'N/A')}\n"
            f"POV: {config.get('pov', 'N/A')}\n"
            f"Tense: {config.get('tense', 'N/A')}",
            title="Project Status",
            border_style="cyan",
        )
    )
