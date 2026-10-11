"""AWS Configuration for Amazon Bedrock Foundation Models."""

import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


class AWSConfig:
    """Manages AWS environment configuration without hardcoded credentials."""

    @classmethod
    def get_region(cls) -> str:
        """Return AWS Region from environment or default to us-east-1."""
        return os.getenv("AWS_REGION", "us-east-1")

    @classmethod
    def get_model_id(cls) -> str:
        """Return Amazon Bedrock Model ID from environment."""
        return os.getenv("BEDROCK_MODEL_ID", "amazon.nova-micro-v1:0")

    _last_live_call: str = "not_called_yet"

    @classmethod
    def is_mock_mode(cls) -> bool:
        """Return True if AWS Mock Mode is enabled for zero-cost demos and tests."""
        raw = os.getenv("AWS_MOCK_MODE", "true").strip().lower()
        return raw in ("true", "1", "yes", "y")

    @classmethod
    def get_last_live_call(cls) -> str:
        """Return the outcome of the last live Bedrock call: 'ok', 'failed', or 'not_called_yet'."""
        return cls._last_live_call

    @classmethod
    def set_last_live_call(cls, status: str) -> None:
        """Record the outcome of the last live Bedrock call ('ok', 'failed', or 'not_called_yet')."""
        cls._last_live_call = status

    @classmethod
    def get_bedrock_runtime_client(cls, region_name: Optional[str] = None):
        """Return a boto3 bedrock-runtime client using the standard IAM credential chain if not in mock mode."""
        if cls.is_mock_mode():
            return None
        # Ensure bearer token is not picked up if set in environment
        os.environ.pop("AWS_BEARER_TOKEN_BEDROCK", None)
        import boto3
        from botocore.config import Config

        region = region_name or cls.get_region()
        # Explicit timeouts (5s connect, 20s read) and max 1 retry so failing calls fall back fast
        boto_config = Config(
            connect_timeout=5,
            read_timeout=20,
            retries={"max_attempts": 2, "mode": "standard"},
        )
        return boto3.client("bedrock-runtime", region_name=region, config=boto_config)

