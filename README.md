# Booksmith

AI-Assisted Book Writing Pipeline using Claude API.

## Installation

```bash
pip install -r requirements.txt
```

Or with uv:
```bash
uv pip install -r requirements.txt
```

## Quick Start

1. **Create a seed file** (e.g., `seed.md`):
```markdown
# My Book Idea

A disgraced detective returns to her hometown to solve a cold case 
that has haunted her for decades. But the town has secrets 
she never imagined.
```

2. **Create a new project**:
```bash
python -m booksmith new my_book --seed seed.md
```

3. **Resume writing**:
```bash
python -m booksmith resume my_book
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `new <name> --seed <file>` | Create new project |
| `resume <name>` | Continue writing |
| `status <name>` | Show project status |
| `chapter <name> --n <N>` | Jump to chapter N |
| `export <name>` | Export manuscript |

## Project Structure

```
projects/
└── my_book/
    ├── project.json
    ├── seed.md
    ├── story_bible.md
    ├── world.md
    ├── characters/
    │   ├── character_index.json
    │   └── <name>.md
    ├── chapter_outlines/
    │   └── chapter_<N>.md
    ├── chapters/
    │   └── chapter_<N>.md
    ├── reviews/
    │   └── chapter_<N>_review.md
    └── summaries/
        └── macro_summary.md
```

## Configuration

Copy `.env.example` to `.env` and configure:

```bash
# API Keys (at least one required)
ANTHROPIC_API_KEY=your_local_api_key
ZENMUX_API_KEY=your_zenmux_api_key

# Model Configuration
ANTHROPIC_DEFAULT_HAIKU_MODEL=glm-4.5-air
ANTHROPIC_DEFAULT_SONNET_MODEL=glm-4.7
ANTHROPIC_DEFAULT_OPUS_MODEL=glm-4.7

# Base URLs
LOCAL_BASE_URL=http://localhost:11434/v1    # For Ollama etc.
ZENMUX_BASE_URL=https://zenmux.ai/api/anthropic
```

Or set environment variables directly.

## Model Assignment

| Stage | Model | Provider |
|-------|-------|----------|
| Story Bible | glm-4.5-air | Local |
| World Builder | glm-4.5-air | Local |
| Characters | glm-4.5-air | Local |
| Chapter Outliner | glm-4.5-air | Local |
| Chapter Writer | glm-4.7 | zenmux.ai |
| AI Reviewer | glm-4.5-air | Local |
| Macro Summary | glm-4.5-air | Local |

## Options

- `--min-words` - Minimum words per chapter (default: 2000)
- `--pov` - Point of view (default: third person limited)
- `--tense` - Tense (default: past)

## Approval Workflow

Each stage shows content and prompts:
- `[A]` Approve - proceed to next stage
- `[E]` Edit - open in $EDITOR, then reload
- `[R]` Regenerate - regenerate with optional extra instruction

Chapter writing adds:
- `[F]` Feedback - give feedback and regenerate
- `[S]` Skip - approve without review
