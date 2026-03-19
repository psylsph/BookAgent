import uuid
from pathlib import Path
from typing import Optional

import ebooklib
from ebooklib import epub

from ..storage.project import Project

# Light brown paper colors for styling
PAPER_BG = "#F5E6D3"
PAPER_TEXT = "#2C2416"
PAPER_HEADER = "#4A3728"


def get_chapters_in_order(project: Project) -> list[tuple[int, str]]:
    """Get all approved chapters in order."""
    chapters = []
    for chapter_num in project.approved_chapters:
        try:
            content = project.get_approved_chapter(chapter_num)
            if content:
                chapters.append((chapter_num, content))
        except Exception:
            continue
    return sorted(chapters, key=lambda x: x[0])


def create_title_page(project: Project) -> epub.EpubHtml:
    """Create a title page."""
    title_page = epub.EpubHtml(
        title=project.title, file_name="title_page.xhtml", lang="en"
    )
    title_page.content = f"""<div style="text-align: center; padding: 3em; page-break-after: always;">
        <h1 style="font-size: 2em; margin-bottom: 1em; color: #4A3728;">{project.title}</h1>
        <p style="font-size: 1.2em; font-style: italic; color: #4A3728;">by BookSmith</p>
    </div>"""
    return title_page


def create_chapter_break(
    project: Project, chapter_num: int, chapter_title: str
) -> epub.EpubHtml:
    """Create a chapter break/title page."""
    chapter_break = epub.EpubHtml(
        title=f"Chapter {chapter_num}",
        file_name=f"chapter_{chapter_num}_break.xhtml",
        lang="en",
    )
    chapter_break.content = f"""<div style="text-align: center; padding: 4em; page-break-after: always;">
        <h2 style="font-size: 1.5em; margin-bottom: 0.5em; color: #4A3728;">Chapter {chapter_num}</h2>
        <p style="font-size: 1em; font-style: italic; color: #4A3728;">{chapter_title}</p>
    </div>"""
    return chapter_break


def create_epub(project: Project, output_path: Optional[Path] = None) -> Path:
    """Create an EPUB from the project manuscript."""
    book = epub.EpubBook()

    # Set metadata
    book.set_identifier(f"booksmith-{project.title.lower().replace(' ', '-')}")
    book.set_title(project.title)
    book.set_language("en")

    # Add author
    book.add_author("BookSmith Generated")

    # Get chapters
    chapters = get_chapters_in_order(project)

    if not chapters:
        raise ValueError("No approved chapters found to export")

    # Create spine
    spine = ["nav"]
    toc = []

    # Add title page first
    title_page = create_title_page(project)
    book.add_item(title_page)
    spine.append(title_page)

    for chapter_num, content in chapters:
        # Create chapter break page
        chapter_break = create_chapter_break(
            project, chapter_num, f"Chapter {chapter_num}"
        )
        book.add_item(chapter_break)
        spine.append(chapter_break)

        # Create chapter content
        chapter_file = epub.EpubHtml(
            title=f"Chapter {chapter_num}",
            file_name=f"chapter_{chapter_num}.xhtml",
            lang="en",
        )

        # Convert markdown-like content to XHTML
        chapter_file.content = convert_to_xhtml(content)

        book.add_item(chapter_file)
        spine.append(chapter_file)
        toc.append(chapter_file)

    # Set spine and TOC
    book.spine = spine
    book.toc = tuple(toc)

    # Add nav file
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    # Write the EPUB
    if output_path is None:
        output_path = project.path / f"{project.title}_manuscript.epub"

    epub.write_epub(str(output_path), book, {})

    return output_path


def convert_to_xhtml(content: str) -> str:
    """Convert markdown-like content to basic XHTML."""
    import re

    # Escape HTML entities
    content = content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # Convert markdown headers with inline styles
    content = re.sub(
        r"^### (.+)$",
        r'<h3 style="color: #4A3728;">\1</h3>',
        content,
        flags=re.MULTILINE,
    )
    content = re.sub(
        r"^## (.+)$",
        r'<h2 style="color: #4A3728;">\1</h2>',
        content,
        flags=re.MULTILINE,
    )
    content = re.sub(
        r"^# (.+)$", r'<h1 style="color: #4A3728;">\1</h1>', content, flags=re.MULTILINE
    )

    # Convert bold and italic
    content = re.sub(r"\*\*\*(.+?)\*\*\*", r"<strong><em>\1</em></strong>", content)
    content = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", content)
    content = re.sub(r"\*(.+?)\*", r"<em>\1</em>", content)

    # Convert paragraphs with inline styles for paper look
    lines = content.split("\n")
    result = []
    in_paragraph = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith(
            ("<h1", "<h2", "<h3", "<p", "<ul", "<ol", "<li", "<block")
        ):
            if in_paragraph:
                result.append("</p>")
                in_paragraph = False
            result.append(line)
        elif stripped == "":
            if in_paragraph:
                result.append("</p>")
                in_paragraph = False
        else:
            if not in_paragraph:
                result.append('<p style="text-indent: 1.5em; margin-bottom: 0.5em;">')
                in_paragraph = True
            result.append(line)

    if in_paragraph:
        result.append("</p>")

    return "\n".join(result)
