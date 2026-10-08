"""Check command for validating live Amazon Bedrock connectivity.

Usage:
    python -m aws_planner.check
"""

import os
import sys
import time
from dotenv import load_dotenv

# Ensure UTF-8 output if possible on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

from aws_planner.config import AWSConfig


def suggest_inference_profile(model_id: str) -> str:
    """Return the recommended cross-region inference profile ID for a given model ID."""
    if model_id.startswith("us.") or model_id.startswith("eu.") or model_id.startswith("apac."):
        return model_id
    if "nova-micro" in model_id:
        return "us.amazon.nova-micro-v1:0"
    if "nova-lite" in model_id:
        return "us.amazon.nova-lite-v1:0"
    if "nova-pro" in model_id:
        return "us.amazon.nova-pro-v1:0"
    if "claude-3-5-sonnet" in model_id:
        return "us.anthropic.claude-3-5-sonnet-20241022-v2:0"
    if "claude-3-5-haiku" in model_id:
        return "us.anthropic.claude-3-5-haiku-20241022-v1:0"
    return f"us.{model_id}"


def check_bedrock() -> int:
    """Make one lightweight Converse call to Amazon Bedrock and report status."""
    region = AWSConfig.get_region()
    model_id = AWSConfig.get_model_id()
    has_token = AWSConfig.has_bearer_token()

    print("==================================================")
    print("       Amazon Bedrock Connectivity Check          ")
    print("==================================================")
    print(f"AWS Region : {region}")
    print(f"Model ID   : {model_id}")
    if has_token:
        print("Auth Method: AWS_BEARER_TOKEN_BEDROCK (configured, secret masked)")
    else:
        print("Auth Method: Standard AWS credentials / IAM")
    print("--------------------------------------------------")
    print("Sending test prompt: 'Say hello in one short sentence.' ...")

    try:
        import boto3

        client = boto3.client("bedrock-runtime", region_name=region)
        start_time = time.time()
        response = client.converse(
            modelId=model_id,
            messages=[
                {
                    "role": "user",
                    "content": [{"text": "Say hello in one short sentence."}],
                }
            ],
            inferenceConfig={"temperature": 0.1, "maxTokens": 60},
        )
        latency = time.time() - start_time
        reply = response.get("output", {}).get("message", {}).get("content", [{}])[0].get("text", "").strip()

        print("--------------------------------------------------")
        print("Status     : SUCCESS (200 OK)")
        print(f"Latency    : {latency:.2f}s")
        print(f"Reply      : \"{reply}\"")
        print("==================================================")
        return 0

    except Exception as exc:
        err_msg = str(exc)
        exc_type = type(exc).__name__

        print("--------------------------------------------------")
        print("Status     : FAILED")
        print(f"Error Type : {exc_type}")
        print(f"Details    : {err_msg}")

        err_lower = err_msg.lower()
        if (
            "inference profile" in err_lower
            or "cross-region" in err_lower
            or "on-demand throughput isn't supported" in err_lower
        ):
            suggested_profile = suggest_inference_profile(model_id)
            print("--------------------------------------------------")
            print("[!] ACTION REQUIRED: Model requires an Inference Profile!")
            print(f"Exact Profile ID to use: {suggested_profile}")
            print("To fix, set in your .env:")
            print(f"    BEDROCK_MODEL_ID={suggested_profile}")

        elif "service control policy" in err_lower or "explicit deny" in err_lower:
            print("--------------------------------------------------")
            print("[!] ACTION REQUIRED: AWS Organizations Service Control Policy (SCP) Deny!")
            print("The AWS Organizations SCP attached to this account explicitly denies")
            print("'bedrock:CallWithBearerToken'. Contact your AWS administrator to allow this action.")

        print("==================================================")
        return 1


if __name__ == "__main__":
    sys.exit(check_bedrock())
