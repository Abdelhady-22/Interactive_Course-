"""Agent engine — orchestrates the hybrid decision pipeline.

Flow:
1. Try rule engine first (fast, deterministic, free)
2. If no rule matches → send to CrewAI agent (Layout Director)
3. CrewAI uses LiteLLM under the hood for multi-provider LLM access
4. Validate the output against the DecisionOutput schema
5. Return the decision

Architecture:
- CrewAI = the agent framework (role, goal, task structure)
- LiteLLM = the provider layer inside CrewAI (Ollama, GPT, Claude, Groq, etc.)
- No direct LiteLLM calls — all LLM interaction goes through CrewAI
"""
import json
import logging

from crewai import Agent, Crew, Task

from app.agent import rules
from app.agent.prompts import SYSTEM_PROMPT, build_paragraph_prompt
from app.config import settings
from app.schemas.decision import DecisionOutput

logger = logging.getLogger(__name__)


def _create_layout_director_agent() -> Agent:
    """Create the CrewAI Layout Director agent.

    The `llm` parameter accepts a LiteLLM model string, which gives us
    multi-provider support automatically:
    - "ollama/llama3" → local Ollama
    - "gpt-4o" → OpenAI
    - "claude-3-sonnet-20240229" → Anthropic
    - "groq/llama-3.1-70b-versatile" → Groq
    """
    return Agent(
        role="Layout Director",
        goal=(
            "Analyze educational course paragraphs and decide the optimal"
            " screen layout, asset placement, and transitions to maximize"
            " learning impact."
        ),
        backstory=(
            "You are an expert educational video director with 20 years of"
            " experience in creating engaging visual learning experiences."
            " You understand that every layout choice serves a teaching purpose."
            " You think about pacing, visual hierarchy, and how learners"
            " absorb information through different visual compositions."
        ),
        verbose=False,
        allow_delegation=False,
        llm=settings.llm_model,  # LiteLLM model string for multi-provider support
    )


def _create_layout_task(
    agent: Agent,
    paragraph_id: str,
    paragraph: dict,
    assets: list[dict],
    video_context: dict,
) -> Task:
    """Create a CrewAI task for deciding a paragraph's layout."""
    user_prompt = build_paragraph_prompt(paragraph_id, paragraph, assets, video_context)

    return Task(
        description=(
            f"{SYSTEM_PROMPT}\n\n"
            f"---\n\n"
            f"{user_prompt}"
        ),
        expected_output=(
            "A valid JSON object with layout, assets, transition, "
            "script_display, director_note, confidence, and decided_by fields."
        ),
        agent=agent,
    )


def _parse_crew_output(raw: str) -> dict:
    """Parse the CrewAI output, handling markdown wrapping."""
    # CrewAI sometimes wraps JSON in markdown code blocks
    text = raw.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    return json.loads(text)


def _run_crew_agent(
    paragraph_id: str,
    paragraph: dict,
    assets: list[dict],
    video_context: dict,
) -> dict:
    """Run the CrewAI Layout Director agent on a single paragraph.

    CrewAI handles:
    - Agent persona (role, goal, backstory)
    - Task structuring and execution
    - LLM provider routing via LiteLLM (configured in settings.llm_model)
    """
    agent = _create_layout_director_agent()
    task = _create_layout_task(agent, paragraph_id, paragraph, assets, video_context)

    crew = Crew(
        agents=[agent],
        tasks=[task],
        verbose=False,
    )

    result = crew.kickoff()
    raw = str(result)

    return _parse_crew_output(raw)


def process_paragraph(
    paragraph_id: str,
    paragraph: dict,
    assets: list[dict],
    video_context: dict,
) -> DecisionOutput:
    """Process a single paragraph through the hybrid decision pipeline.

    Args:
        paragraph_id: UUID string of the paragraph
        paragraph: Dict with text, keywords, start_ms, end_ms
        assets: List of available asset dicts
        video_context: Dict with video description

    Returns:
        DecisionOutput — validated decision ready to store

    Flow:
        1. Try rules engine (fast, free, deterministic)
        2. If no rule matches → CrewAI agent (uses LiteLLM for provider routing)
        3. Validate output schema
    """
    # --- Step 1: Try rules ---
    rule_decision = rules.evaluate(paragraph_id, paragraph, assets)
    if rule_decision is not None:
        logger.info(
            f"Paragraph {paragraph_id}: Rule matched → "
            f"layout={rule_decision.layout.mode}, confidence={rule_decision.confidence}"
        )
        return rule_decision

    # --- Step 2: CrewAI agent ---
    logger.info(f"Paragraph {paragraph_id}: No rule matched → running CrewAI agent")

    try:
        raw_decision = _run_crew_agent(
            paragraph_id, paragraph, assets, video_context
        )
    except Exception as e:
        logger.error(f"Paragraph {paragraph_id}: CrewAI agent failed: {e}")
        return _fallback_decision(paragraph_id, paragraph)

    # --- Step 3: Validate against schema ---
    try:
        decision = DecisionOutput(**raw_decision)
        logger.info(
            f"Paragraph {paragraph_id}: CrewAI decided → "
            f"layout={decision.layout.mode}, confidence={decision.confidence}"
        )
        return decision
    except Exception as e:
        logger.error(f"Paragraph {paragraph_id}: Agent output validation failed: {e}")
        # Return a safe fallback
        return _fallback_decision(paragraph_id, paragraph)


def _fallback_decision(paragraph_id: str, paragraph: dict) -> DecisionOutput:
    """Safe fallback when both rules and CrewAI fail."""
    from app.models.decision import DecisionSource
    from app.schemas.decision import (
        BoardLayout, InstructorLayout, LayoutDecision,
        ScriptDisplayDecision, TransitionDecision,
    )

    return DecisionOutput(
        paragraph_id=paragraph_id,
        layout=LayoutDecision(
            mode="split_50_50",
            description="Fallback: equal split between instructor and board.",
            instructor=InstructorLayout(
                visible=True, position="right", size="medium", style="normal"
            ),
            board=BoardLayout(visible=True, position="left", size="medium"),
        ),
        assets=[],
        transition=TransitionDecision(
            type="fade", duration_ms=400,
            instruction="Default fade transition."
        ),
        script_display=ScriptDisplayDecision(
            instruction="Show paragraph text at the bottom.",
            keywords_to_highlight=paragraph.get("keywords", []),
        ),
        director_note="FALLBACK: Both rule engine and CrewAI agent failed to produce a valid decision. Using safe split layout. Please review manually.",
        confidence=0.3,
        decided_by=DecisionSource.LLM,
    )


def process_course(
    paragraphs: list[dict],
    assets: list[dict],
    video_context: dict,
) -> list[DecisionOutput]:
    """Process all paragraphs in a course.

    Args:
        paragraphs: List of paragraph dicts, each with id, text, keywords, start_ms, end_ms
        assets: List of all asset dicts for the course
        video_context: Dict with video description

    Returns:
        List of DecisionOutput objects, one per paragraph
    """
    decisions = []
    for p in paragraphs:
        decision = process_paragraph(
            paragraph_id=p["id"],
            paragraph=p,
            assets=assets,
            video_context=video_context,
        )
        decisions.append(decision)

    from app.models.decision import DecisionSource
    logger.info(
        f"Processed {len(decisions)} paragraphs: "
        f"{sum(1 for d in decisions if d.decided_by == DecisionSource.RULE)} by rules, "
        f"{sum(1 for d in decisions if d.decided_by == DecisionSource.LLM)} by CrewAI"
    )
    return decisions
