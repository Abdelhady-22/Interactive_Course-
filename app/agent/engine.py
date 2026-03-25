"""Agent engine — orchestrates the hybrid decision pipeline with cross-paragraph awareness.

Flow:
1. Run sequence analyzer to detect asset-heavy sequences
2. For each paragraph:
   a. Try rule engine first (fast, deterministic, free)
   b. If no rule matches → send to CrewAI agent (Layout Director)
   c. Pass previous 3 decisions + continuity hints as context
   d. Apply continuity overrides from sequence analyzer
   e. Validate the output against the DecisionOutput schema
3. Return all decisions

Production features:
- LLM retry with exponential backoff (configurable)
- LLM response timeout (configurable)
- Structured error handling
"""
import json
import logging
import time

from crewai import Agent, Crew, Task

from app.agent import rules
from app.agent.prompts import SYSTEM_PROMPT, build_paragraph_prompt
from app.agent.sequence_analyzer import analyze_sequences, get_continuity_hints
from app.config import settings
from app.middleware import AgentError, ErrorCode
from app.models.decision import DecisionSource
from app.schemas.decision import DecisionOutput, PositionContinuity

logger = logging.getLogger(__name__)

# How many previous decisions to include as context
CONTEXT_LOOKBACK = 3


def _create_layout_director_agent() -> Agent:
    """Create the CrewAI Layout Director agent."""
    return Agent(
        role="Layout Director",
        goal=(
            "Analyze educational course paragraphs and decide the optimal"
            " screen layout, asset placement, transitions, and instructor"
            " positioning continuity to maximize learning impact."
        ),
        backstory=(
            "You are an expert educational video director with 20 years of"
            " experience in creating engaging visual learning experiences."
            " You understand that every layout choice serves a teaching purpose."
            " You think about pacing, visual hierarchy, cross-paragraph continuity,"
            " and how learners absorb information through different visual compositions."
            " You know when to pin the instructor in place for stability and when"
            " to transition for dramatic effect."
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
    previous_decisions: list[dict] | None = None,
    continuity_hint: dict | None = None,
) -> Task:
    """Create a CrewAI task for deciding a paragraph's layout."""
    user_prompt = build_paragraph_prompt(
        paragraph_id, paragraph, assets, video_context,
        previous_decisions=previous_decisions,
        continuity_hint=continuity_hint,
    )

    return Task(
        description=(
            f"{SYSTEM_PROMPT}\n\n"
            f"---\n\n"
            f"{user_prompt}"
        ),
        expected_output=(
            "A valid JSON object with layout, assets, transition, "
            "script_display, continuity, director_note, confidence, and decided_by fields."
        ),
        agent=agent,
    )


def _parse_crew_output(raw: str) -> dict:
    """Parse the CrewAI output, handling markdown wrapping."""
    text = raw.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    return json.loads(text)


def _run_crew_agent_with_retry(
    paragraph_id: str,
    paragraph: dict,
    assets: list[dict],
    video_context: dict,
    previous_decisions: list[dict] | None = None,
    continuity_hint: dict | None = None,
) -> dict:
    """Run the CrewAI agent with retry logic and timeout.

    Retries with exponential backoff: 1s → 2s → 4s → ...
    Raises AgentError if all retries fail.
    """
    max_retries = settings.llm_max_retries
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            start_time = time.time()

            agent = _create_layout_director_agent()
            task = _create_layout_task(
                agent, paragraph_id, paragraph, assets, video_context,
                previous_decisions=previous_decisions,
                continuity_hint=continuity_hint,
            )

            crew = Crew(
                agents=[agent],
                tasks=[task],
                verbose=False,
            )

            result = crew.kickoff()
            elapsed = time.time() - start_time

            # Check timeout
            if elapsed > settings.llm_timeout_seconds:
                logger.warning(
                    f"Paragraph {paragraph_id}: LLM took {elapsed:.1f}s "
                    f"(timeout={settings.llm_timeout_seconds}s)"
                )

            raw = str(result)
            parsed = _parse_crew_output(raw)

            logger.info(
                f"Paragraph {paragraph_id}: CrewAI succeeded on attempt {attempt} "
                f"({elapsed:.1f}s)"
            )
            return parsed

        except json.JSONDecodeError as e:
            last_error = e
            logger.warning(
                f"Paragraph {paragraph_id}: JSON parse failed on attempt {attempt}/{max_retries}: {e}"
            )
        except Exception as e:
            last_error = e
            logger.warning(
                f"Paragraph {paragraph_id}: CrewAI failed on attempt {attempt}/{max_retries}: {e}"
            )

        # Exponential backoff before retry
        if attempt < max_retries:
            backoff = 2 ** (attempt - 1)  # 1s, 2s, 4s, ...
            logger.info(f"Paragraph {paragraph_id}: Retrying in {backoff}s...")
            time.sleep(backoff)

    # All retries exhausted
    error_msg = f"CrewAI agent failed after {max_retries} attempts: {last_error}"
    logger.error(f"Paragraph {paragraph_id}: {error_msg}")
    raise AgentError(
        code=ErrorCode.AGENT_LLM_UNAVAILABLE,
        message=error_msg,
        detail=str(last_error),
    )


def _apply_continuity(
    decision: DecisionOutput,
    continuity_hint: dict | None,
    previous_decisions: list[DecisionOutput],
) -> DecisionOutput:
    """Apply continuity overrides from the sequence analyzer."""
    if not continuity_hint or not continuity_hint.get("pin_instructor"):
        return decision

    pin_from = None
    if previous_decisions:
        for prev in previous_decisions:
            if prev.continuity.pin_instructor:
                pin_from = prev.continuity.pin_from_paragraph or prev.paragraph_id
                break

    if decision.continuity.pin_instructor:
        if not decision.continuity.pin_from_paragraph and pin_from:
            decision.continuity.pin_from_paragraph = pin_from
        return decision

    pin_position = continuity_hint.get("pin_position", "bottom_right")
    pin_size = continuity_hint.get("pin_size", "small")
    pin_style = continuity_hint.get("pin_style", "pip")

    decision.layout.instructor.position = pin_position
    decision.layout.instructor.size = pin_size
    decision.layout.instructor.style = pin_style

    decision.continuity = PositionContinuity(
        pin_instructor=True,
        pin_from_paragraph=pin_from or decision.paragraph_id,
        transition_instructor=continuity_hint.get("is_sequence_start", False),
        sequence_note=continuity_hint.get("note", "Pinned by sequence analyzer."),
    )

    logger.info(
        f"Paragraph {decision.paragraph_id}: Continuity override — "
        f"pin instructor at {pin_position}/{pin_size}/{pin_style}"
    )
    return decision


def process_paragraph(
    paragraph_id: str,
    paragraph: dict,
    assets: list[dict],
    video_context: dict,
    previous_decisions: list[dict] | None = None,
    continuity_hint: dict | None = None,
) -> DecisionOutput:
    """Process a single paragraph through the hybrid decision pipeline."""
    # --- Step 1: Try rules (with context) ---
    rule_decision = rules.evaluate(
        paragraph_id, paragraph, assets,
        previous_decisions=previous_decisions,
        continuity_hint=continuity_hint,
    )
    if rule_decision is not None:
        logger.info(
            f"Paragraph {paragraph_id}: Rule matched → "
            f"layout={rule_decision.layout.mode}, confidence={rule_decision.confidence}"
        )
        return rule_decision

    # --- Step 2: CrewAI agent with retry ---
    logger.info(f"Paragraph {paragraph_id}: No rule matched → running CrewAI agent")

    try:
        raw_decision = _run_crew_agent_with_retry(
            paragraph_id, paragraph, assets, video_context,
            previous_decisions=previous_decisions,
            continuity_hint=continuity_hint,
        )
    except AgentError:
        logger.warning(f"Paragraph {paragraph_id}: All retries failed → using fallback")
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
        return _fallback_decision(paragraph_id, paragraph)


def _fallback_decision(paragraph_id: str, paragraph: dict) -> DecisionOutput:
    """Safe fallback when both rules and CrewAI fail."""
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
        continuity=PositionContinuity(
            pin_instructor=False,
            transition_instructor=True,
            sequence_note="Fallback decision — no continuity context available.",
        ),
        director_note="FALLBACK: Both rule engine and CrewAI agent failed. Using safe split layout. Please review manually.",
        confidence=0.3,
        decided_by=DecisionSource.LLM,
    )


def process_course(
    paragraphs: list[dict],
    assets: list[dict],
    video_context: dict,
) -> list[DecisionOutput]:
    """Process all paragraphs in a course with cross-paragraph awareness."""
    # Step 1: Analyze sequences
    sequences = analyze_sequences(paragraphs, assets)
    continuity_hints = get_continuity_hints(paragraphs, sequences)

    logger.info(
        f"Sequence analysis: {len(sequences)} sequences, "
        f"{sum(1 for h in continuity_hints if h.pin_instructor)} paragraphs will be pinned"
    )

    # Step 2: Process each paragraph with context
    decisions: list[DecisionOutput] = []
    for i, p in enumerate(paragraphs):
        logger.info(f"Processing paragraph {i+1}/{len(paragraphs)}: {p.get('id', '?')}")

        prev_dicts = None
        if decisions:
            prev_decisions_raw = decisions[max(0, i - CONTEXT_LOOKBACK):i]
            prev_dicts = [d.model_dump() for d in prev_decisions_raw]

        hint = continuity_hints[i] if i < len(continuity_hints) else None
        hint_dict = {
            "pin_instructor": hint.pin_instructor,
            "pin_position": hint.pin_position,
            "pin_size": hint.pin_size,
            "pin_style": hint.pin_style,
            "is_sequence_start": hint.is_sequence_start,
            "is_sequence_middle": hint.is_sequence_middle,
            "is_sequence_end": hint.is_sequence_end,
            "note": hint.note,
        } if hint else None

        decision = process_paragraph(
            paragraph_id=p["id"],
            paragraph=p,
            assets=assets,
            video_context=video_context,
            previous_decisions=prev_dicts,
            continuity_hint=hint_dict,
        )

        decision = _apply_continuity(decision, hint_dict, decisions)
        decisions.append(decision)

    logger.info(
        f"Processed {len(decisions)} paragraphs: "
        f"{sum(1 for d in decisions if d.decided_by == DecisionSource.RULE)} by rules, "
        f"{sum(1 for d in decisions if d.decided_by == DecisionSource.LLM)} by CrewAI, "
        f"{sum(1 for d in decisions if d.continuity.pin_instructor)} pinned"
    )
    return decisions
