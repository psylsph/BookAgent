import pytest
import os
from pathlib import Path


class TestAPIConnection:
    """Integration tests for API connectivity."""

    def test_remote_configured(self):
        """Check remote endpoint is configured."""
        from booksmith.api_client import ANTHROPIC_BASE_URL

        # ANTHROPIC_BASE_URL can be None (SDK default) or a URL
        if ANTHROPIC_BASE_URL is not None:
            assert ANTHROPIC_BASE_URL.startswith("http")

    def test_models_configured(self):
        """Check models are configured."""
        from booksmith.api_client import (
            ANTHROPIC_DEFAULT_HAIKU_MODEL,
            ANTHROPIC_DEFAULT_SONNET_MODEL,
        )

        assert ANTHROPIC_DEFAULT_HAIKU_MODEL is not None
        assert ANTHROPIC_DEFAULT_SONNET_MODEL is not None

    def test_context_sizes_configured(self):
        """Check context sizes are configured."""
        from booksmith.api_client import (
            ANTHROPIC_HAIKU_CONTEXT,
            ANTHROPIC_SONNET_CONTEXT,
        )

        assert ANTHROPIC_HAIKU_CONTEXT > 0
        assert ANTHROPIC_SONNET_CONTEXT > 0

    def test_api_client_can_connect(self):
        """Test that API client can be created."""
        from booksmith.api_client import APIClient

        client = APIClient()

        # Just verify client is created - actual API call needs valid key
        assert client is not None

    def test_env_file_exists(self):
        """Check .env file exists."""
        env_path = Path(__file__).parent.parent / ".env"
        assert env_path.exists(), ".env file not found"

    def test_env_has_required_vars(self):
        """Check .env has required variables."""
        from booksmith.api_client import (
            ANTHROPIC_DEFAULT_SONNET_MODEL,
            ANTHROPIC_DEFAULT_HAIKU_MODEL,
        )

        # These should be loaded from .env
        assert ANTHROPIC_DEFAULT_SONNET_MODEL is not None
        assert ANTHROPIC_DEFAULT_HAIKU_MODEL is not None


class TestAPIIntegration:
    """Actual API integration tests - these will be skipped if no valid API key."""

    @pytest.mark.integration
    def test_remote_generate_simple(self):
        """Test remote API with a simple prompt."""
        from booksmith.api_client import APIClient

        client = APIClient()

        # Skip if no valid API key
        if not os.getenv("ANTHROPIC_AUTH_TOKEN") and not os.getenv("ANTHROPIC_API_KEY"):
            pytest.skip("No ANTHROPIC_AUTH_TOKEN configured")

        response = client.generate(
            stage="chapter_writer",
            system="You are a helpful assistant.",
            user_message="Say 'hello' in exactly 3 words.",
        )

        assert response is not None
        assert len(response) > 0
        assert "hello" in response.lower()

    @pytest.mark.integration
    def test_local_generate_simple(self):
        """Test local API with a simple prompt."""
        from booksmith.api_client import APIClient

        client = APIClient()

        # Skip if no API key
        if not os.getenv("ANTHROPIC_AUTH_TOKEN") and not os.getenv("ANTHROPIC_API_KEY"):
            pytest.skip("No ANTHROPIC_AUTH_TOKEN configured")

        response = client.generate(
            stage="story_bible",
            system="You are a helpful assistant.",
            user_message="Say 'test' in exactly 1 word.",
        )

        assert response is not None
        assert len(response) > 0

    @pytest.mark.integration
    def test_stream_works(self):
        """Test streaming works (or falls back correctly)."""
        from booksmith.api_client import APIClient

        client = APIClient()

        if not os.getenv("ANTHROPIC_AUTH_TOKEN") and not os.getenv("ANTHROPIC_API_KEY"):
            pytest.skip("No ANTHROPIC_AUTH_TOKEN configured")

        chunks = []
        for chunk in client.stream(
            stage="chapter_writer",
            system="You are a helpful assistant.",
            user_message="Count from 1 to 3.",
        ):
            chunks.append(chunk)

        # Should get some chunks or fallback to full response
        result = "".join(chunks)
        assert len(result) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration"])
