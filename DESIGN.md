# BookSmith Design Document

## Overview

BookSmith is an AI-assisted book writing pipeline that orchestrates multiple LLM calls to generate structured book content. It uses a stage-based pipeline with human-in-the-loop approval at each step.

## Architecture

```
booksmith/
├── main.py           # CLI entry point, pipeline orchestration
├── api_client.py     # LLM API abstraction, model routing
├── pipeline/
│   ├── story_bible.py    # Generate story overview
│   ├── world_builder.py # Build world/setting details
│   ├── characters.py    # Generate character profiles
│   ├── chapter_outliner.py # Create chapter outlines
│   ├── chapter_writer.py   # Write chapter content
│   ├── reviewer.py       # AI review of chapters
│   └── retrieval.py     # Context retrieval for prompts
├── storage/
│   └── project.py    # Project file management
├── ui/
│   ├── console.py    # Console UI, approval prompts
│   └── prompts.py    # Prompt templates
└── prompts/          # Text prompt files
```

## Pipeline Stages

| Stage | Input | Output | Model |
|-------|-------|--------|-------|
| Story Bible | seed.md | story_bible.md | Local |
| World Builder | story_bible.md | world.md | Local |
| Characters | story_bible + world.md | characters/*.md | Local |
| Chapter Outliner | story_bible | chapter_outlines/chapter_list.md | Local |
| Chapter Writer | outline + context | chapters/*.md | Local |
| Reviewer | chapter content | reviews/*_review.md | Local |
| Outline Review | chapter outline | reviews/*_outline_review.md | Local |
| Macro Summary | all chapters | summaries/macro_summary.md | Local |

## Approval Workflow

Each stage presents content to the user with options:

- **[A]** Approve - proceed to next stage
- **[R]** Regenerate - regenerate content
- **[F]** Feedback - provide feedback, regenerate with it
- **[E]** Edit - open in $EDITOR, reload changes
- **[S]** Skip - skip remaining (chapter outlines/writing only)

### Chapter Outline Flow

1. Generate chapter list from story bible
2. For each chapter outline:
   - Show to user, get A/R/F/E/S
   - If approved: run AI outline review
   - Show AI feedback, user chooses Continue or Regenerate
3. Save approved list to `chapter_outlines/chapter_list.md`

### Chapter Writing Flow

1. For each chapter:
   - Retrieve relevant context (characters, world, previous chapters)
   - Generate chapter content
   - Run AI reviewer
   - Show review score and content
   - User chooses A/R/F/E/S
   - If approved: update macro summary

## Data Storage

Projects stored in `projects/<name>/`:

```
projects/<name>/
├── project.json       # Project config (model, chapter count, etc.)
├── seed.md           # Original seed content
├── story_bible.md    # Story overview
├── world.md          # World/setting details
├── characters/
│   ├── character_index.json  # Character list with existence flags
│   └── <character>.md        # Individual profiles
├── chapter_outlines/
│   ├── chapter_list.md      # Master chapter list
│   └── chapter_<N>.md       # Individual outlines
├── chapters/
│   └── chapter_<N>.md       # Written chapters
├── reviews/
│   ├── chapter_<N>_review.md
│   └── chapter_<N>_outline_review.md
└── summaries/
    └── macro_summary.md
```

## Model Configuration

Models are selected per-stage via `MODEL_PROVIDER_MAP` in `api_client.py`:

```python
MODEL_PROVIDER_MAP = {
    "story_bible": ("local", ...),
    "world_builder": ("local", ...),
    "characters": ("local", ...),
    "chapter_outliner": ("local", ...),
    "chapter_writer": ("local", ...),
    "reviewer": ("local", ...),
    "outline_reviewer": ("local", ...),
    "macro_summary": ("local", ...),
}
```

All stages use local models by default. Remote models can be configured via `.env`.

Temperature can be set via `.env`:
- `DEFAULT_TEMPERATURE` - fallback for all stages
- `TEMP_<STAGE>` - stage-specific override

## Key Design Decisions

### Why Local Models?

All stages use local models by default. Benefits:
- Faster for structured outputs (outlines, character profiles)
- More consistent for story development
- Lower cost (no API calls to external providers)
- Works offline with Ollama/LM Studio

Remote models can be enabled via `.env` configuration if stronger reasoning is needed.

### Chapter List vs Detailed Outlines

The chapter outliner generates two outputs:
1. **Chapter list** (`chapter_list.md`) - Titles + one-line purposes for all chapters
2. **Individual outlines** (`chapter_N.md`) - Detailed scene-by-scene breakdown per chapter

This separation avoids duplicating detailed content in a single API call.

### Character Profile Stability

Character profiles include seed content in prompts to prevent drift during regeneration. The `character_index.json` tracks which characters have full profiles to avoid unnecessary regeneration on resume.

### Chapter List Parsing

Handles both bullet list and table formats:
```
| 1 | Title | Purpose |
```

### Context Retrieval

Before writing each chapter, retrieves:
- Story bible
- World details  
- Character profiles (relevant ones)
- Previous chapter summaries
- Current chapter outline

## Extending BookSmith

### Adding New Pipeline Stages

1. Add stage name to `MODEL_PROVIDER_MAP` in `api_client.py`
2. Create pipeline module in `booksmith/pipeline/`
3. Add prompt file in `booksmith/prompts/`
4. Add stage handling in `main.py` pipeline loop

### Adding New Model Providers

1. Add provider config in `.env`
2. Add provider handling in `api_client.py`
3. Update `get_model_for_stage()` if needed
