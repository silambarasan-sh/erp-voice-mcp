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

    @classmethod
    def is_mock_mode(cls) -> bool:
        """Return True if AWS Mock Mode is enabled for zero-cost demos and tests."""
        raw = os.getenv("AWS_MOCK_MODE", "true").strip().lower()
        return raw in ("true", "1", "yes", "y")

    @classmethod
    def has_bearer_token(cls) -> bool:
        """Return True if AWS_BEARER_TOKEN_BEDROCK is set in environment (never logs or returns value)."""
        return bool(os.getenv("AWS_BEARER_TOKEN_BEDROCK", "").strip())

    @classmethod
    def get_bedrock_runtime_client(cls, region_name: Optional[str] = None):
        """Return a boto3 bedrock-runtime client if not in mock mode."""
        if cls.is_mock_mode():
            return None
        import boto3

        region = region_name or cls.get_region()
        return boto3.client("bedrock-runtime", region_name=region)

