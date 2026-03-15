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
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_TIMEOUT = int(os.getenv("ANTHROPIC_TIMEOUT", "120"))

# Default writing settings
DEFAULT_MIN_WORDS = int(os.getenv("DEFAULT_MIN_WORDS", "2000"))

# Temperature settings
DEFAULT_TEMPERATURE = float(os.getenv("DEFAULT_TEMPERATURE", "0.7"))

# Stage-specific temperature overrides (optional)
TEMPERATURE_MAP = {
    "story_bible": float(os.getenv("TEMP_STORY_BIBLE", "0.7")),
    "world_builder": float(os.getenv("TEMP_WORLD_BUILDER", "0.7")),
    "characters": float(os.getenv("TEMP_CHARACTERS", "0.7")),
    "chapter_outliner": float(os.getenv("TEMP_CHAPTER_OUTLINER", "0.7")),
    "chapter_writer": float(os.getenv("TEMP_CHAPTER_WRITER", "0.8")),
    "reviewer": float(os.getenv("TEMP_REVIEWER", "0.5")),
    "outline_reviewer": float(os.getenv("TEMP_OUTLINE_REVIEWER", "0.5")),
    "macro_summary": float(os.getenv("TEMP_MACRO_SUMMARY", "0.5")),
}

# Remote config (zenmux or other providers)
ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "")
ANTHROPIC_REMOTE_MODEL = os.getenv("ANTHROPIC_REMOTE_MODEL", "claude-sonnet-4-20250514")
ANTHROPIC_REMOTE_CONTEXT = int(os.getenv("ANTHROPIC_REMOTE_CONTEXT", "128000"))

# Local config
LOCAL_BASE_URL = os.getenv("LOCAL_BASE_URL", "")
ANTHROPIC_LOCAL_MODEL = os.getenv(
    "ANTHROPIC_LOCAL_MODEL", "mistralai/mistral-nemo-instruct-2407"
)
ANTHROPIC_LOCAL_CONTEXT = int(os.getenv("ANTHROPIC_LOCAL_CONTEXT", "32768"))

# Provider mappings for each pipeline stage
MODEL_PROVIDER_MAP = {
    "story_bible": ("local", ANTHROPIC_LOCAL_MODEL, ANTHROPIC_LOCAL_CONTEXT),
    "world_builder": ("local", ANTHROPIC_LOCAL_MODEL, ANTHROPIC_LOCAL_CONTEXT),
    "characters": ("local", ANTHROPIC_LOCAL_MODEL, ANTHROPIC_LOCAL_CONTEXT),
    "chapter_outliner": ("local", ANTHROPIC_LOCAL_MODEL, ANTHROPIC_LOCAL_CONTEXT),
    "chapter_writer": ("local", ANTHROPIC_LOCAL_MODEL, ANTHROPIC_LOCAL_CONTEXT),
    "reviewer": ("local", ANTHROPIC_LOCAL_MODEL, ANTHROPIC_LOCAL_CONTEXT),
    "outline_reviewer": ("local", ANTHROPIC_LOCAL_MODEL, ANTHROPIC_LOCAL_CONTEXT),
    "macro_summary": ("local", ANTHROPIC_LOCAL_MODEL, ANTHROPIC_LOCAL_CONTEXT),
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
            base_url = None
            if provider == "remote":
                base_url = ANTHROPIC_BASE_URL
            elif provider == "local":
                base_url = LOCAL_BASE_URL if LOCAL_BASE_URL else None

            self._clients[provider] = anthropic.Anthropic(
                api_key=self.api_key,
                base_url=base_url,
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
            stage, ("local", ANTHROPIC_LOCAL_MODEL, ANTHROPIC_LOCAL_CONTEXT)
        )
        return model

    def get_context_for_stage(self, stage: str) -> int:
        """Get context window size for a given pipeline stage."""
        _, _, context = MODEL_PROVIDER_MAP.get(
            stage, ("local", ANTHROPIC_LOCAL_MODEL, ANTHROPIC_LOCAL_CONTEXT)
        )
        return context

    def get_provider_for_stage(self, stage: str) -> str:
        """Get provider (local/remote) for a given pipeline stage."""
        provider, _, _ = MODEL_PROVIDER_MAP.get(
            stage, ("local", ANTHROPIC_LOCAL_MODEL, ANTHROPIC_LOCAL_CONTEXT)
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

        for attempt in range(self.max_retries):
            try:
                with client.messages.stream(
                    model=model,
                    system=system,
                    messages=[{"role": "user", "content": user_message}],
                    max_tokens=context_size,
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
                        max_tokens=8192,
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
