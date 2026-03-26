"""LiteLLM configuration — multi-provider LLM access layer.

This module exists as a utility for providers that need direct
LLM calls outside of CrewAI (e.g., future features like
auto-summarization, keyword extraction, etc.).

For the agent pipeline, LLM calls go through CrewAI, which uses
LiteLLM internally via the `llm` parameter on the Agent.

Supported providers (configured in .env via LLM_MODEL):
- ollama/llama3         → local Ollama
- gpt-4o               → OpenAI
- claude-3-sonnet-...   → Anthropic
- groq/llama-3.1-...   → Groq
- cohere/command-r      → Cohere
"""
import json
import logging
import os

import litellm

from app.config import settings

logger = logging.getLogger(__name__)

# Suppress litellm's verbose logging
litellm.suppress_debug_info = True


def configure_litellm():
    """Set up LiteLLM environment for CrewAI to use.

    CrewAI/LiteLLM looks up API keys by provider-specific env vars:
    - groq/* → GROQ_API_KEY
    - gpt-* / openai/* → OPENAI_API_KEY
    - anthropic/* → ANTHROPIC_API_KEY
    - cohere/* → COHERE_API_KEY

    This function maps our single LLM_API_KEY setting to the correct env var.
    """
    if settings.llm_api_base:
        os.environ.setdefault("LITELLM_API_BASE", settings.llm_api_base)

    if settings.llm_api_key:
        # Set generic key
        os.environ.setdefault("LITELLM_API_KEY", settings.llm_api_key)

        # Set provider-specific key based on model prefix
        model = settings.llm_model.lower()
        provider_env_map = {
            "groq/": "GROQ_API_KEY",
            "gpt-": "OPENAI_API_KEY",
            "openai/": "OPENAI_API_KEY",
            "anthropic/": "ANTHROPIC_API_KEY",
            "claude-": "ANTHROPIC_API_KEY",
            "cohere/": "COHERE_API_KEY",
        }

        for prefix, env_var in provider_env_map.items():
            if model.startswith(prefix):
                os.environ.setdefault(env_var, settings.llm_api_key)
                logger.info(f"Set {env_var} for provider '{prefix.rstrip('/')}'")
                break

    logger.info(f"LiteLLM configured: model={settings.llm_model}")


def complete(system_prompt: str, user_prompt: str) -> dict:
    """Send a prompt to the configured LLM and return parsed JSON.

    NOTE: This is NOT used by the agent pipeline (which uses CrewAI).
    It's available for utility tasks like summarization, keyword
    extraction, or other future features.

    Args:
        system_prompt: The system prompt defining the role
        user_prompt: The user prompt with data

    Returns:
        Parsed JSON dict from the LLM response

    Raises:
        ValueError: If LLM response is not valid JSON
        Exception: If LLM call fails after retries
    """
    kwargs = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 2000,
        "num_retries": settings.llm_max_retries,
        "timeout": settings.llm_timeout_seconds,
    }

    if settings.llm_api_base:
        kwargs["api_base"] = settings.llm_api_base

    if settings.llm_api_key:
        kwargs["api_key"] = settings.llm_api_key

    logger.info(f"Calling LLM: model={settings.llm_model}")

    try:
        response = litellm.completion(**kwargs)
        raw_content = response.choices[0].message.content.strip()

        # Clean response — sometimes LLMs wrap JSON in markdown code blocks
        if raw_content.startswith("```json"):
            raw_content = raw_content[7:]
        if raw_content.startswith("```"):
            raw_content = raw_content[3:]
        if raw_content.endswith("```"):
            raw_content = raw_content[:-3]
        raw_content = raw_content.strip()

        parsed = json.loads(raw_content)
        logger.info(f"LLM response parsed successfully.")
        return parsed

    except json.JSONDecodeError as e:
        logger.error(f"LLM returned invalid JSON: {e}\nRaw: {raw_content[:500]}")
        raise ValueError(f"LLM returned invalid JSON: {e}")
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        raise


# Auto-configure on import
configure_litellm()
