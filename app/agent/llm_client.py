"""LiteLLM client — thin wrapper for multi-provider LLM access.

Supports Ollama (local), Groq, Cohere, OpenAI, Anthropic, and any
provider supported by LiteLLM — configured via .env.
"""
import json
import logging

import litellm

from app.config import settings

logger = logging.getLogger(__name__)

# Suppress litellm's verbose logging
litellm.suppress_debug_info = True


def complete(system_prompt: str, user_prompt: str) -> dict:
    """Send a prompt to the configured LLM and return parsed JSON.

    Args:
        system_prompt: The system prompt defining the agent's role
        user_prompt: The user prompt with paragraph data

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
        "temperature": 0.3,  # Low temp for consistent, deterministic decisions
        "max_tokens": 2000,
        "num_retries": 2,
    }

    # Set API base for local providers (Ollama)
    if settings.llm_api_base:
        kwargs["api_base"] = settings.llm_api_base

    # Set API key for cloud providers
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
        logger.info(f"LLM response parsed successfully. Confidence: {parsed.get('confidence', 'N/A')}")
        return parsed

    except json.JSONDecodeError as e:
        logger.error(f"LLM returned invalid JSON: {e}\nRaw: {raw_content[:500]}")
        raise ValueError(f"LLM returned invalid JSON: {e}")
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        raise
