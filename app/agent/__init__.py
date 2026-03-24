"""Agent package — hybrid AI decision engine.

Architecture:
- rules.py      → Deterministic rule engine (checked first)
- engine.py     → Orchestrator: rules → CrewAI → fallback
- prompts.py    → System prompt and user prompt builder
- llm_client.py → LiteLLM config (multi-provider layer for CrewAI)

CrewAI is the agent framework. LiteLLM is the provider layer.
"""
# Auto-configure LiteLLM environment on first import
from app.agent.llm_client import configure_litellm as _configure
_configure()
