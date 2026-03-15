import pytest
import os
from pathlib import Path


class TestAPIConnection:
    """Integration tests for API connectivity."""

    def test_remote_configured(self):
        """Check remote endpoint is configured."""
        from booksmith.api_client import ANTHROPIC_BASE_URL

        assert ANTHROPIC_BASE_URL is not None

    def test_local_configured(self):
        """Check local endpoint is configured."""
        from booksmith.api_client import LOCAL_BASE_URL

        # Local might be None or a URL
        if LOCAL_BASE_URL:
            assert LOCAL_BASE_URL.startswith("http")

    def test_models_configured(self):
        """Check models are configured."""
        from booksmith.api_client import (
            ANTHROPIC_LOCAL_MODEL,
            ANTHROPIC_REMOTE_MODEL,
        )

        assert ANTHROPIC_LOCAL_MODEL is not None
        assert ANTHROPIC_REMOTE_MODEL is not None

    def test_context_sizes_configured(self):
        """Check context sizes are configured."""
        from booksmith.api_client import (
            ANTHROPIC_LOCAL_CONTEXT,
            ANTHROPIC_REMOTE_CONTEXT,
        )

        assert ANTHROPIC_LOCAL_CONTEXT == 32768
        assert ANTHROPIC_REMOTE_CONTEXT == 128000

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
            ANTHROPIC_BASE_URL,
            ANTHROPIC_REMOTE_MODEL,
            ANTHROPIC_LOCAL_MODEL,
        )

        # These should be loaded from .env
        assert ANTHROPIC_REMOTE_MODEL is not None
        assert ANTHROPIC_LOCAL_MODEL is not None


class TestAPIIntegration:
    """Actual API integration tests - these will be skipped if no valid API key."""

    @pytest.mark.integration
    def test_remote_generate_simple(self):
        """Test remote API with a simple prompt."""
        from booksmith.api_client import APIClient

        client = APIClient()

        # Skip if no valid API key
        if not os.getenv("ANTHROPIC_API_KEY"):
            pytest.skip("No ANTHROPIC_API_KEY configured")

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
        from booksmith.api_client import APIClient, LOCAL_BASE_URL

        # Skip if no local URL configured
        if not LOCAL_BASE_URL:
            pytest.skip("No LOCAL_BASE_URL configured")

        client = APIClient()

        # Skip if no API key
        if not os.getenv("ANTHROPIC_API_KEY"):
            pytest.skip("No ANTHROPIC_API_KEY configured")

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

        if not os.getenv("ANTHROPIC_API_KEY"):
            pytest.skip("No ANTHROPIC_API_KEY configured")

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
