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

4. **Or with YOLO mode** (auto-approve, single AI review pass):
```bash
python -m booksmith --yolo resume my_book
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `new <name> --seed <file>` | Create new project |
| `resume <name>` | Continue writing |
| `resume <name> --yolo` | Auto-approve all stages |
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
    │   ├── chapter_list.md
    │   └── chapter_<N>.md
    ├── chapters/
    │   └── chapter_<N>.md
    ├── reviews/
    │   ├── chapter_<N>_review.md
    │   └── chapter_<N>_outline_review.md
    └── summaries/
        └── macro_summary.md
```

## Configuration

Copy `.env.example` to `.env` and configure:

```bash
# API Key
ANTHROPIC_API_KEY=your_api_key

# Remote model (zenmux or other providers)
ANTHROPIC_BASE_URL=https://zenmux.ai/api/anthropic
ANTHROPIC_REMOTE_MODEL=deepseek/deepseek-v3.2-exp
ANTHROPIC_REMOTE_CONTEXT=128000

# Local model (Ollama, LM Studio, etc.)
LOCAL_BASE_URL=http://localhost:11434/v1
ANTHROPIC_LOCAL_MODEL=mistralai/mistral-nemo-instruct-2407
ANTHROPIC_LOCAL_CONTEXT=32768

# Writing settings
DEFAULT_MIN_WORDS=2000

# Temperature per stage (optional)
DEFAULT_TEMPERATURE=0.7
TEMP_CHAPTER_OUTLINER=1.0
TEMP_CHAPTER_WRITER=1.0
TEMP_REVIEWER=0.3
```

## Model Assignment by Stage

| Stage | Provider | Model | Temperature |
|-------|----------|-------|-------------|
| Story Bible | local | ANTHROPIC_LOCAL_MODEL | 0.7 |
| World Builder | local | ANTHROPIC_LOCAL_MODEL | 0.7 |
| Characters | local | ANTHROPIC_LOCAL_MODEL | 0.7 |
| Chapter Outliner | local | ANTHROPIC_LOCAL_MODEL | 1.0 |
| Chapter Writer | local | ANTHROPIC_LOCAL_MODEL | 1.0 |
| Reviewer | local | ANTHROPIC_LOCAL_MODEL | 0.3 |
| Outline Review | local | ANTHROPIC_LOCAL_MODEL | 0.3 |
| Macro Summary | local | ANTHROPIC_LOCAL_MODEL | 0.3 |

## Approval Workflow

Each stage shows content and prompts:
- `[A]` Approve - proceed to next stage
- `[E]` Edit - open in $EDITOR, then reload
- `[R]` Regenerate - regenerate content
- `[F]` Feedback - give feedback and regenerate
- `[S]` Skip - skip to next (chapter outlines and chapters)
- Lowercase input also works (a, r, f, e, s)

### YOLO Mode

Use `--yolo` flag for hands-off operation:
```bash
python -m booksmith --yolo resume my_book
```

YOLO mode:
- Auto-approves outline/chapter generation
- Runs AI review and **regenerates with AI feedback** automatically
- Single pass per chapter (no regeneration loop)

### Chapter Outline Review Flow

1. Generate chapter list from story bible
2. For each chapter:
   - Show outline to user
   - User can A/R/F/E/S
   - If approved, run AI outline review
   - Show AI feedback, user can Continue or Regenerate with feedback
3. Proceed to chapter writing loop

### Chapter Writing Flow

1. Generate chapter from outline
2. Run AI reviewer
3. Show review score and content
4. User can A/R/F/E/S
5. If approved, update macro summary
6. Proceed to next chapter
