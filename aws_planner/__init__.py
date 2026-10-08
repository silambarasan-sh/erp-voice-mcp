"""AWS Layer for ERP Voice Agent (AWS Builder Challenge).

Integrates Amazon Bedrock and AWS Strands Agents SDK to provide intelligent
multi-step supply chain planning over Model Context Protocol (MCP).
"""

from aws_planner.config import AWSConfig
from aws_planner.agent import ERPPlannerAgent

__all__ = ["AWSConfig", "ERPPlannerAgent"]
