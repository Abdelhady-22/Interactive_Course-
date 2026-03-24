"""Agent engine — orchestrates the hybrid decision pipeline.

Flow:
1. Try rule engine first (fast, deterministic, free)
2. If no rule matches → send to LLM via LiteLLM
3. Validate the output against the DecisionOutput schema
4. Return the decision

CrewAI is used to structure the LLM agent with a clear role,
goal, and task — making decisions more consistent and the
system extensible for future multi-agent workflows.
"""
import json
import logging
from crewai import Agent, Crew, Task

from app.agent import rules
from app.agent.prompts import SYSTEM_PROMPT, build_paragraph_prompt
from app.agent import llm_client
from app.config import settings
from app.schemas.decision import DecisionOutput

logger = logging.getLogger(__name__)


def _create_layout_director_agent() -> Agent:
    """Create the CrewAI Layout Director agent."""
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
        llm=settings.llm_model,
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
        expected_output="A valid JSON object with layout, assets, transition, script_display, director_note, confidence, and decided_by fields.",
        agent=agent,
    )


def _llm_decide_with_crewai(
    paragraph_id: str,
    paragraph: dict,
    assets: list[dict],
    video_context: dict,
) -> dict:
    """Use CrewAI agent to make a layout decision.

    Falls back to direct LiteLLM call if CrewAI fails.
    """
    try:
        agent = _create_layout_director_agent()
        task = _create_layout_task(agent, paragraph_id, paragraph, assets, video_context)

        crew = Crew(
            agents=[agent],
            tasks=[task],
            verbose=False,
        )

        result = crew.kickoff()
        raw = str(result)

        # Parse the CrewAI output
        if raw.startswith("```json"):
            raw = raw[7:]
        if raw.startswith("```"):
            raw = raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

        return json.loads(raw)

    except Exception as e:
        logger.warning(f"CrewAI failed ({e}), falling back to direct LiteLLM call")
        return _llm_decide_direct(paragraph_id, paragraph, assets, video_context)


def _llm_decide_direct(
    paragraph_id: str,
    paragraph: dict,
    assets: list[dict],
    video_context: dict,
) -> dict:
    """Direct LiteLLM call as fallback when CrewAI is unavailable."""
    user_prompt = build_paragraph_prompt(paragraph_id, paragraph, assets, video_context)
    return llm_client.complete(SYSTEM_PROMPT, user_prompt)


def process_paragraph(
    paragraph_id: str,
    paragraph: dict,
    assets: list[dict],
    video_context: dict,
    use_crewai: bool = True,
) -> DecisionOutput:
    """Process a single paragraph through the hybrid decision pipeline.

    Args:
        paragraph_id: UUID string of the paragraph
        paragraph: Dict with text, keywords, start_ms, end_ms
        assets: List of available asset dicts (filtered for relevance if needed)
        video_context: Dict with video description
        use_crewai: Whether to use CrewAI (True) or direct LiteLLM (False)

    Returns:
        DecisionOutput — validated decision ready to store

    Flow:
        1. Try rules engine
        2. If no rule matches → LLM (via CrewAI or direct)
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

    # --- Step 2: LLM decision ---
    logger.info(f"Paragraph {paragraph_id}: No rule matched → calling LLM")

    if use_crewai:
        raw_decision = _llm_decide_with_crewai(
            paragraph_id, paragraph, assets, video_context
        )
    else:
        raw_decision = _llm_decide_direct(
            paragraph_id, paragraph, assets, video_context
        )

    # --- Step 3: Validate against schema ---
    try:
        decision = DecisionOutput(**raw_decision)
        logger.info(
            f"Paragraph {paragraph_id}: LLM decided → "
            f"layout={decision.layout.mode}, confidence={decision.confidence}"
        )
        return decision
    except Exception as e:
        logger.error(f"Paragraph {paragraph_id}: LLM output validation failed: {e}")
        # Return a safe fallback
        return _fallback_decision(paragraph_id, paragraph)


def _fallback_decision(paragraph_id: str, paragraph: dict) -> DecisionOutput:
    """Safe fallback when both rules and LLM fail."""
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
        director_note="FALLBACK: Both rule engine and LLM failed to produce a valid decision. Using safe split layout. Please review manually.",
        confidence=0.3,
        decided_by=DecisionSource.LLM,
    )


def process_course(
    paragraphs: list[dict],
    assets: list[dict],
    video_context: dict,
    use_crewai: bool = True,
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
            use_crewai=use_crewai,
        )
        decisions.append(decision)

    from app.models.decision import DecisionSource
    logger.info(
        f"Processed {len(decisions)} paragraphs: "
        f"{sum(1 for d in decisions if d.decided_by == DecisionSource.RULE)} by rules, "
        f"{sum(1 for d in decisions if d.decided_by == DecisionSource.LLM)} by LLM"
    )
    return decisions
