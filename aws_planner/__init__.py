"""AWS Layer for ERP Voice Agent (AWS Builder Challenge).

Integrates Amazon Bedrock Foundation Models to provide intelligent
multi-step supply chain planning over Model Context Protocol (MCP).
"""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "erp_core.settings")

from aws_planner.config import AWSConfig


def __getattr__(name: str):
    if name == "ERPPlannerAgent":
        import django

        django.setup()
        from aws_planner.agent import ERPPlannerAgent

        return ERPPlannerAgent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["AWSConfig", "ERPPlannerAgent"]
