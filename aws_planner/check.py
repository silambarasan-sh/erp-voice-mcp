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
    # Ensure bearer token is not picked up if set in environment
    os.environ.pop("AWS_BEARER_TOKEN_BEDROCK", None)

    region = AWSConfig.get_region()
    model_id = AWSConfig.get_model_id()

    import boto3

    # Inspect boto3 credential method safely without exposing secrets
    auth_method = "Standard AWS credentials / IAM"
    try:
        session = boto3.Session(region_name=region)
        creds = session.get_credentials()
        if creds:
            method_name = getattr(creds, "method", "")
            if method_name == "env":
                auth_method = "IAM User Access Key (AWS_ACCESS_KEY_ID via env)"
            elif method_name in ("shared-credentials-file", "config-file", "config"):
                auth_method = f"AWS CLI Profile / Credentials File ({method_name})"
            elif method_name in ("iam-role", "assume-role", "ecs-container", "ec2-instance-metadata"):
                auth_method = f"IAM Role ({method_name})"
            elif method_name:
                auth_method = f"IAM Credentials ({method_name})"
    except Exception:
        pass

    print("==================================================")
    print("       Amazon Bedrock Connectivity Check          ")
    print("==================================================")
    print(f"AWS Region : {region}")
    print(f"Model ID   : {model_id}")
    print(f"Auth Method: {auth_method}")
    print("--------------------------------------------------")
    print("Sending test prompt: 'Say hello in one short sentence.' ...")

    try:
        from botocore.config import Config

        boto_config = Config(
            connect_timeout=5,
            read_timeout=20,
            retries={"max_attempts": 2, "mode": "standard"},
        )
        client = boto3.client("bedrock-runtime", region_name=region, config=boto_config)
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

        AWSConfig.set_last_live_call("ok")
        print("--------------------------------------------------")
        print("Status     : SUCCESS (200 OK)")
        print(f"Latency    : {latency:.2f}s")
        print(f"Reply      : \"{reply}\"")
        print("==================================================")
        return 0

    except Exception as exc:
        AWSConfig.set_last_live_call("failed")
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

        elif "service control policy" in err_lower or "explicit deny" in err_lower or "callwithbearertoken" in err_lower:
            print("--------------------------------------------------")
            print("[!] ACTION REQUIRED: AWS Organizations Service Control Policy (SCP) Deny!")
            print("An AWS Organizations SCP attached to this account explicitly denied this action.")
            print("Ensure bearer-token API keys are not used ('bedrock:CallWithBearerToken' is blocked) and that")
            print("IAM credentials (AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY) with AmazonBedrockLimitedAccess are used.")

        print("==================================================")
        return 1


if __name__ == "__main__":
    sys.exit(check_bedrock())
