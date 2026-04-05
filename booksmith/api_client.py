import os
import time
from pathlib import Path
from typing import Any, Generator, Optional, cast

import anthropic
from dotenv import load_dotenv

# Load .env file from project root (BookAgent directory)
_env_path = Path(__file__).parent.parent / ".env"
load_dotenv(_env_path)

# API Configuration
ANTHROPIC_AUTH_TOKEN = os.getenv("ANTHROPIC_AUTH_TOKEN", "")
ANTHROPIC_API_KEY = ANTHROPIC_AUTH_TOKEN or os.getenv("ANTHROPIC_API_KEY", "")
API_TIMEOUT_MS = int(os.getenv("API_TIMEOUT_MS", "120000"))
ANTHROPIC_TIMEOUT = API_TIMEOUT_MS / 1000

# Default writing settings
DEFAULT_MIN_WORDS = int(os.getenv("DEFAULT_MIN_WORDS", "1500"))

# Temperature settings
DEFAULT_TEMPERATURE = float(os.getenv("DEFAULT_TEMPERATURE", "0.7"))

# Stage-specific temperature overrides (optional)
# These will only be used if the specific TEMP_* env var is set
# Otherwise DEFAULT_TEMPERATURE is used for all stages
TEMPERATURE_MAP = {}

# Check if stage-specific env vars are set, otherwise use None (will default to DEFAULT_TEMPERATURE)
for stage, env_var in [
    ("story_bible", "TEMP_STORY_BIBLE"),
    ("world_builder", "TEMP_WORLD_BUILDER"),
    ("characters", "TEMP_CHARACTERS"),
    ("chapter_outliner", "TEMP_CHAPTER_OUTLINER"),
    ("chapter_writer", "TEMP_CHAPTER_WRITER"),
    ("context_brief", "TEMP_CONTEXT_BRIEF"),
    ("reviewer", "TEMP_REVIEWER"),
    ("outline_reviewer", "TEMP_OUTLINE_REVIEWER"),
    ("macro_summary", "TEMP_MACRO_SUMMARY"),
]:
    if os.getenv(env_var):
        TEMPERATURE_MAP[stage] = float(os.getenv(env_var))

# Model configuration
ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL") or None
ANTHROPIC_DEFAULT_HAIKU_MODEL = os.getenv(
    "ANTHROPIC_DEFAULT_HAIKU_MODEL", "claude-haiku-4-20250514"
)
ANTHROPIC_DEFAULT_SONNET_MODEL = os.getenv(
    "ANTHROPIC_DEFAULT_SONNET_MODEL", "claude-sonnet-4-20250514"
)
ANTHROPIC_DEFAULT_OPUS_MODEL = os.getenv(
    "ANTHROPIC_DEFAULT_OPUS_MODEL", "claude-opus-4-20250514"
)
ANTHROPIC_HAIKU_CONTEXT = int(os.getenv("ANTHROPIC_HAIKU_CONTEXT", "128000"))
ANTHROPIC_SONNET_CONTEXT = int(os.getenv("ANTHROPIC_SONNET_CONTEXT", "128000"))
ANTHROPIC_OPUS_CONTEXT = int(os.getenv("ANTHROPIC_OPUS_CONTEXT", "128000"))

# Provider mappings for each pipeline stage
MODEL_PROVIDER_MAP = {
    "story_bible": ("local", ANTHROPIC_DEFAULT_HAIKU_MODEL, ANTHROPIC_HAIKU_CONTEXT),
    "world_builder": ("local", ANTHROPIC_DEFAULT_HAIKU_MODEL, ANTHROPIC_HAIKU_CONTEXT),
    "characters": ("local", ANTHROPIC_DEFAULT_HAIKU_MODEL, ANTHROPIC_HAIKU_CONTEXT),
    "chapter_outliner": (
        "local",
        ANTHROPIC_DEFAULT_HAIKU_MODEL,
        ANTHROPIC_HAIKU_CONTEXT,
    ),
    "context_brief": (
        "local",
        ANTHROPIC_DEFAULT_HAIKU_MODEL,
        ANTHROPIC_HAIKU_CONTEXT,
    ),
    "chapter_writer": (
        "remote",
        ANTHROPIC_DEFAULT_SONNET_MODEL,
        ANTHROPIC_SONNET_CONTEXT,
    ),
    "reviewer": ("remote", ANTHROPIC_DEFAULT_SONNET_MODEL, ANTHROPIC_SONNET_CONTEXT),
    "outline_reviewer": (
        "local",
        ANTHROPIC_DEFAULT_HAIKU_MODEL,
        ANTHROPIC_HAIKU_CONTEXT,
    ),
    "macro_summary": ("local", ANTHROPIC_DEFAULT_HAIKU_MODEL, ANTHROPIC_HAIKU_CONTEXT),
}


class APIClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        max_retries: int = 3,
        timeout: int = ANTHROPIC_TIMEOUT,
    ):
        self.api_key = api_key or ANTHROPIC_API_KEY
        self.max_retries = max_retries
        self.timeout = timeout
        self._clients = {}

    def _get_client(self, provider: str) -> anthropic.Anthropic:
        if provider not in self._clients:
            self._clients[provider] = anthropic.Anthropic(
                api_key=self.api_key,
                base_url=ANTHROPIC_BASE_URL if provider == "remote" else None,
                timeout=self.timeout,
            )
        return self._clients[provider]

    def get_model_for_stage(
        self, stage: str, project_config: Optional[dict] = None
    ) -> str:
        """Get model for a given pipeline stage."""
        # Prefer stage-specific model from MODEL_PROVIDER_MAP over project config
        # (project config model is typically used for chapter writing)
        _, model, _ = MODEL_PROVIDER_MAP.get(
            stage, ("local", ANTHROPIC_DEFAULT_HAIKU_MODEL, ANTHROPIC_HAIKU_CONTEXT)
        )
        return model

    def get_context_for_stage(self, stage: str) -> int:
        """Get context window size for a given pipeline stage."""
        _, _, context = MODEL_PROVIDER_MAP.get(
            stage, ("local", ANTHROPIC_DEFAULT_HAIKU_MODEL, ANTHROPIC_HAIKU_CONTEXT)
        )
        return context

    def get_provider_for_stage(self, stage: str) -> str:
        """Get provider (local/remote) for a given pipeline stage."""
        provider, _, _ = MODEL_PROVIDER_MAP.get(
            stage, ("local", ANTHROPIC_DEFAULT_HAIKU_MODEL, ANTHROPIC_HAIKU_CONTEXT)
        )
        return provider

    def get_temperature_for_stage(self, stage: str) -> float:
        """Get temperature for a given pipeline stage."""
        return TEMPERATURE_MAP.get(stage, DEFAULT_TEMPERATURE)

    def stream(
        self,
        stage: str,
        system: str,
        user_message: str,
        project_config: Optional[dict] = None,
    ) -> Generator[str, None, None]:
        """Stream a response from the API for a given stage."""
        provider = self.get_provider_for_stage(stage)
        model = self.get_model_for_stage(stage, project_config)
        context_size = self.get_context_for_stage(stage)
        temperature = self.get_temperature_for_stage(stage)
        client = self._get_client(provider)

        # Cap max_tokens for chapter writing to prevent excessive length
        # Assuming ~1.3 tokens per word, 5000 words ≈ 6500 tokens
        if stage == "chapter_writer":
            max_tokens = min(context_size, 8192)  # Cap at 8k tokens for chapter writing
        else:
            max_tokens = context_size

        for attempt in range(self.max_retries):
            try:
                with client.messages.stream(
                    model=model,
                    system=system,
                    messages=[{"role": "user", "content": user_message}],
                    max_tokens=max_tokens,
                    temperature=temperature,
                ) as stream:
                    for text in stream.text_stream:
                        yield text
                return
            except Exception as e:
                if attempt < self.max_retries - 1:
                    wait_time = 2**attempt
                    time.sleep(wait_time)
                    continue

                # Fallback to non-streaming if streaming fails
                try:
                    response = client.messages.create(
                        model=model,
                        system=system,
                        messages=[{"role": "user", "content": user_message}],
                        max_tokens=min(max_tokens, 8192),
                    )
                    for block in cast(Any, response.content):
                        if hasattr(block, "text"):
                            yield cast(Any, block).text
                        elif hasattr(block, "type") and block.type == "text":
                            yield cast(Any, block).text
                    return
                except Exception:
                    raise e

    def generate(
        self,
        stage: str,
        system: str,
        user_message: str,
        project_config: Optional[dict] = None,
    ) -> str:
        """Generate a complete response (non-streaming)."""
        provider = self.get_provider_for_stage(stage)
        model = self.get_model_for_stage(stage, project_config)
        context_size = self.get_context_for_stage(stage)
        temperature = self.get_temperature_for_stage(stage)
        client = self._get_client(provider)

        last_error = None
        for attempt in range(self.max_retries):
            try:
                response = client.messages.create(
                    model=model,
                    system=system,
                    messages=[{"role": "user", "content": user_message}],
                    max_tokens=context_size,
                    temperature=temperature,
                )
                # pyright: ignore[attr-defined]
                for block in response.content:
                    if hasattr(block, "text"):
                        return block.text
                    elif hasattr(block, "type") and block.type == "text":
                        return block.text
                raise Exception("No text content in response")
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    wait_time = 2**attempt
                    time.sleep(wait_time)
                    continue
                break

        raise last_error or Exception("Failed to generate response")


def load_prompt_template(template_name: str) -> tuple[str, str]:
    """Load a prompt template file and return (system_prompt, user_prompt)."""
    import pathlib

    prompt_dir = pathlib.Path(__file__).parent / "prompts"
    template_path = prompt_dir / f"{template_name}.txt"

    if not template_path.exists():
        raise FileNotFoundError(f"Prompt template not found: {template_path}")

    content = template_path.read_text()

    system_marker = "---SYSTEM---"
    user_marker = "---USER---"

    system_start = content.find(system_marker)
    user_start = content.find(user_marker)

    if system_start == -1 or user_start == -1:
        raise ValueError(f"Invalid prompt template format: {template_name}")

    system_prompt = content[system_start + len(system_marker) : user_start].strip()
    user_prompt = content[user_start + len(user_marker) :].strip()

    return system_prompt, user_prompt


def format_prompt(template_name: str, **kwargs) -> tuple[str, str]:
    """Load and format a prompt template with provided variables."""
    system, user = load_prompt_template(template_name)

    try:
        system = system.format(**kwargs)
    except KeyError as e:
        raise ValueError(f"Missing template variable: {e}")

    try:
        user = user.format(**kwargs)
    except KeyError as e:
        raise ValueError(f"Missing template variable: {e}")

    return system, user
