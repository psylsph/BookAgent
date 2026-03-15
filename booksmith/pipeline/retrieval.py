from pathlib import Path
from typing import List, Optional

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

STOPWORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "but",
    "in",
    "on",
    "at",
    "to",
    "for",
    "of",
    "with",
    "by",
    "from",
    "as",
    "is",
    "was",
    "are",
    "were",
    "been",
    "be",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "could",
    "should",
    "may",
    "might",
    "must",
    "shall",
    "can",
    "need",
    "dare",
    "ought",
    "used",
    "it",
    "its",
    "this",
    "that",
    "these",
    "those",
    "i",
    "you",
    "he",
    "she",
    "we",
    "they",
    "me",
    "him",
    "her",
    "us",
    "them",
    "my",
    "your",
    "his",
    "our",
    "their",
    "mine",
    "yours",
    "hers",
    "ours",
    "theirs",
    "who",
    "whom",
    "which",
    "what",
    "whose",
    "where",
    "when",
    "why",
    "how",
    "all",
    "each",
    "every",
    "both",
    "few",
    "more",
    "most",
    "other",
    "some",
    "such",
    "no",
    "nor",
    "not",
    "only",
    "own",
    "same",
    "so",
    "than",
    "too",
    "very",
    "just",
    "also",
    "now",
    "here",
    "there",
    "then",
    "once",
    "if",
    "because",
    "until",
    "while",
    "about",
    "against",
    "between",
    "into",
    "through",
    "during",
    "before",
    "after",
    "above",
    "below",
    "up",
    "down",
    "out",
    "off",
    "over",
    "under",
    "again",
    "further",
    "any",
    "many",
    "much",
    "say",
    "said",
}


class BookRetriever:
    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.vectorizer: Optional[TfidfVectorizer] = None
        self.chunks: List[dict] = []
        self._build_index()

    def _load_character_profiles(self) -> List[dict]:
        """Load all character profiles as chunks."""
        chunks = []
        characters_dir = self.project_path / "characters"

        if not characters_dir.exists():
            return chunks

        for md_file in characters_dir.glob("*.md"):
            if md_file.name == "character_index.json":
                continue

            content = md_file.read_text()
            name = md_file.stem.replace("_", " ")

            chunks.append(
                {
                    "source": f"Character: {name}",
                    "source_type": "character",
                    "source_file": str(md_file.relative_to(self.project_path)),
                    "text": content,
                }
            )

        return chunks

    def _load_world_locations(self) -> List[dict]:
        """Load world locations as chunks."""
        chunks = []
        world_file = self.project_path / "world.md"

        if not world_file.exists():
            return chunks

        content = world_file.read_text()
        sections = content.split("\n## ")

        for section in sections[1:]:
            lines = section.split("\n", 1)
            if len(lines) < 2:
                continue

            location_name = lines[0].strip()
            location_desc = lines[1].strip()

            chunks.append(
                {
                    "source": f"World: {location_name}",
                    "source_type": "world",
                    "source_file": "world.md",
                    "text": f"{location_name}\n\n{location_desc}",
                }
            )

        return chunks

    def _load_approved_chapters(self) -> List[dict]:
        """Load approved chapters, chunked by scene breaks."""
        chunks = []
        chapters_dir = self.project_path / "chapters"

        if not chapters_dir.exists():
            return chunks

        for md_file in sorted(chapters_dir.glob("chapter_*.md")):
            try:
                chapter_num = str(int(md_file.stem.split("_")[1]))
            except (ValueError, IndexError):
                continue
            content = md_file.read_text()

            scenes = content.split("\n---\n")

            for i, scene in enumerate(scenes):
                scene = scene.strip()
                if not scene:
                    continue

                chunks.append(
                    {
                        "source": f"Chapter {chapter_num}, Scene {i + 1}",
                        "source_type": "chapter",
                        "source_file": str(md_file.relative_to(self.project_path)),
                        "chapter": int(chapter_num),
                        "text": scene,
                    }
                )

        return chunks

    def _load_macro_summary(self) -> List[dict]:
        """Load macro summary as a chunk."""
        chunks = []
        summary_file = self.project_path / "summaries" / "macro_summary.md"

        if not summary_file.exists():
            return chunks

        content = summary_file.read_text()

        chunks.append(
            {
                "source": "Macro Summary",
                "source_type": "summary",
                "source_file": "summaries/macro_summary.md",
                "text": content,
            }
        )

        return chunks

    def _build_index(self):
        """Build TF-IDF index from all project documents."""
        self.chunks = []

        self.chunks.extend(self._load_character_profiles())
        self.chunks.extend(self._load_world_locations())
        self.chunks.extend(self._load_approved_chapters())
        self.chunks.extend(self._load_macro_summary())

        if not self.chunks:
            return

        texts = [chunk["text"] for chunk in self.chunks]

        self.vectorizer = TfidfVectorizer(
            stop_words=list(STOPWORDS),
            max_features=5000,
            ngram_range=(1, 2),
        )

        self.vectorizer.fit(texts)

    def retrieve(self, query: str, top_n: int = 5) -> List[dict]:
        """Retrieve top N chunks matching the query."""
        if not self.chunks or not self.vectorizer:
            return []

        filtered_query = " ".join(
            w for w in query.lower().split() if w not in STOPWORDS
        )

        query_vec = self.vectorizer.transform([filtered_query])

        texts = [chunk["text"] for chunk in self.chunks]
        chunk_vecs = self.vectorizer.transform(texts)

        similarities = cosine_similarity(query_vec, chunk_vecs)[0]

        top_indices = similarities.argsort()[-top_n:][::-1]

        results = []
        for idx in top_indices:
            if similarities[idx] > 0:
                result = self.chunks[idx].copy()
                result["score"] = float(similarities[idx])
                results.append(result)

        return results

    def retrieve_for_chapter(
        self,
        chapter_outline: str,
        chapter_num: int,
        top_n: int = 8,
    ) -> List[dict]:
        """Retrieve context for writing a specific chapter."""
        all_results = self.retrieve(chapter_outline, top_n * 2)

        filtered_results = []
        for result in all_results:
            if result["source_type"] == "chapter":
                if result.get("chapter") == chapter_num:
                    continue
                if result.get("chapter", 0) >= chapter_num:
                    continue

            filtered_results.append(result)

            if len(filtered_results) >= top_n:
                break

        return filtered_results


def format_retrieved_context(chunks: List[dict]) -> str:
    """Format retrieved chunks for inclusion in chapter writing prompt."""
    if not chunks:
        return "No relevant context found."

    formatted = []

    for chunk in chunks:
        source = chunk["source"]
        text = chunk["text"]

        if len(text) > 500:
            text = text[:500] + "..."

        formatted.append(f"[{source}]\n{text}\n")

    return "\n---\n\n".join(formatted)
