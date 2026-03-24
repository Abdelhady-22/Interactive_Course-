"""Agent package — hybrid AI decision engine with cross-paragraph intelligence.

Architecture:
- sequence_analyzer.py → Pre-processes paragraphs to detect pinning sequences
- rules.py             → 6 deterministic rules (checked first, free + instant)
- engine.py            → Orchestrator: sequences → rules → CrewAI → fallback
- prompts.py           → System prompt (14 layout modes + continuity) + user prompt
- llm_client.py        → LiteLLM config (multi-provider layer for CrewAI)

CrewAI is the agent framework. LiteLLM is the provider layer.
"""
# Auto-configure LiteLLM environment on first import
from app.agent.llm_client import configure_litellm as _configure
_configure()
