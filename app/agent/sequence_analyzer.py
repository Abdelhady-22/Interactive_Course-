"""Sequence Analyzer — pre-processes paragraphs to detect cross-paragraph patterns.

This module runs BEFORE the agent processes individual paragraphs. It scans
all paragraphs and their relevant assets to identify sequences where the
instructor should be "pinned" in a consistent position.

Key concept: If 2+ consecutive paragraphs have assets, we group them into a
"sequence" and suggest that the instructor stay in one position (e.g. PiP
bottom-right) throughout, instead of transitioning on every paragraph.
"""
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Asset types that typically need the full board/screen
FULLSCREEN_ASSET_TYPES = {"diagram", "infographic", "image"}
# Asset types that can be shown as overlays
OVERLAY_ASSET_TYPES = {"formula"}
# Asset types that need data comparison space
DATA_ASSET_TYPES = {"chart", "graph"}
# Keywords signaling narrative (no assets needed)
NARRATION_KEYWORDS = {"welcome", "introduction", "hello", "greeting", "summary",
                       "recap", "conclusion", "review", "takeaways", "story"}


@dataclass
class SequenceGroup:
    """A group of consecutive paragraphs that share a layout pattern."""
    paragraph_indices: list[int]
    sequence_type: str          # "asset_heavy", "narration", "mixed", "single_asset"
    pin_instructor: bool        # Should instructor stay in one position?
    suggested_pin_position: str # e.g. "bottom_right", "right"
    suggested_pin_size: str     # e.g. "small", "medium"
    suggested_pin_style: str    # e.g. "pip", "normal"
    reason: str                 # Human-readable explanation


@dataclass
class ContinuityHint:
    """Per-paragraph hint generated from sequence analysis."""
    paragraph_index: int
    is_sequence_start: bool     # First paragraph in a pinned sequence
    is_sequence_middle: bool    # Middle of a pinned sequence (don't transition)
    is_sequence_end: bool       # Last paragraph in a pinned sequence
    pin_instructor: bool
    pin_position: str
    pin_size: str
    pin_style: str
    sequence_id: int            # Which sequence this belongs to (-1 if none)
    note: str


def _find_relevant_assets_for_paragraph(paragraph: dict, assets: list[dict]) -> list[dict]:
    """Find assets relevant to a specific paragraph (simplified version of rules._find_relevant_assets)."""
    if not assets:
        return []

    kw_set = {kw.lower().strip() for kw in paragraph.get("keywords", [])}
    text_lower = paragraph.get("text", "").lower()
    relevant = []

    for asset in assets:
        name_lower = asset.get("name", "").lower()
        desc_lower = asset.get("description", "").lower()
        asset_type = asset.get("type", "").lower()

        keyword_match = any(kw in name_lower or kw in desc_lower for kw in kw_set)
        type_match = asset_type in kw_set
        name_in_text = name_lower and any(
            word in text_lower for word in name_lower.split() if len(word) > 3
        )

        if keyword_match or type_match or name_in_text:
            relevant.append(asset)

    return relevant


def _classify_paragraph(paragraph: dict, relevant_assets: list[dict]) -> str:
    """Classify what kind of content a paragraph represents."""
    kw_set = {kw.lower().strip() for kw in paragraph.get("keywords", [])}

    if kw_set & NARRATION_KEYWORDS and not relevant_assets:
        return "narration"

    if not relevant_assets:
        return "narration"

    asset_types = {a.get("type", "").lower() for a in relevant_assets}

    if asset_types & FULLSCREEN_ASSET_TYPES and len(relevant_assets) >= 2:
        return "multi_asset"

    if asset_types & FULLSCREEN_ASSET_TYPES:
        return "single_asset"

    if asset_types & DATA_ASSET_TYPES:
        return "data"

    if asset_types & OVERLAY_ASSET_TYPES:
        return "formula"

    return "mixed"


def _determine_pin_position(asset_types: set[str]) -> tuple[str, str, str]:
    """Determine the best instructor pin position based on asset types in a sequence.

    Returns: (position, size, style)
    """
    # If any assets need full screen, hide instructor or make very small
    if "diagram" in asset_types or "infographic" in asset_types:
        return "bottom_right", "small", "pip"

    # Formulas and images → instructor as medium PiP
    if "formula" in asset_types or "image" in asset_types:
        return "bottom_right", "small", "pip"

    # Charts/graphs → instructor on the side (more visible)
    if "chart" in asset_types or "graph" in asset_types:
        return "right", "medium", "normal"

    # Default
    return "bottom_right", "small", "pip"


def analyze_sequences(
    paragraphs: list[dict],
    assets: list[dict],
) -> list[SequenceGroup]:
    """Analyze all paragraphs to find sequences where instructor should be pinned.

    Args:
        paragraphs: List of paragraph dicts with id, text, keywords, start_ms, end_ms
        assets: List of all course asset dicts

    Returns:
        List of SequenceGroup objects describing detected sequences
    """
    # Step 1: Find relevant assets and classify each paragraph
    classifications = []
    relevant_assets_per_para = []
    for p in paragraphs:
        relevant = _find_relevant_assets_for_paragraph(p, assets)
        relevant_assets_per_para.append(relevant)
        classifications.append(_classify_paragraph(p, relevant))

    # Step 2: Find consecutive runs of asset-bearing paragraphs
    sequences: list[SequenceGroup] = []
    i = 0
    while i < len(paragraphs):
        if classifications[i] in ("single_asset", "multi_asset", "data", "formula", "mixed"):
            # Start of a potential sequence
            seq_start = i
            seq_indices = [i]
            all_asset_types: set[str] = set()
            for a in relevant_assets_per_para[i]:
                all_asset_types.add(a.get("type", "").lower())

            # Extend the sequence
            j = i + 1
            while j < len(paragraphs) and classifications[j] in ("single_asset", "multi_asset", "data", "formula", "mixed"):
                seq_indices.append(j)
                for a in relevant_assets_per_para[j]:
                    all_asset_types.add(a.get("type", "").lower())
                j += 1

            # Only create a pinned sequence if 2+ consecutive paragraphs have assets
            if len(seq_indices) >= 2:
                position, size, style = _determine_pin_position(all_asset_types)
                sequences.append(SequenceGroup(
                    paragraph_indices=seq_indices,
                    sequence_type="asset_heavy",
                    pin_instructor=True,
                    suggested_pin_position=position,
                    suggested_pin_size=size,
                    suggested_pin_style=style,
                    reason=(
                        f"Paragraphs {seq_indices[0]+1}-{seq_indices[-1]+1} all have visual assets "
                        f"({', '.join(sorted(all_asset_types))}). Pinning instructor at {position} "
                        f"for visual stability across {len(seq_indices)} paragraphs."
                    ),
                ))
                logger.info(
                    f"Sequence detected: paragraphs {seq_indices}, "
                    f"pin instructor at {position}/{size}/{style}"
                )
            else:
                # Single asset paragraph — no pinning needed
                sequences.append(SequenceGroup(
                    paragraph_indices=seq_indices,
                    sequence_type="single_asset",
                    pin_instructor=False,
                    suggested_pin_position="bottom_right",
                    suggested_pin_size="small",
                    suggested_pin_style="pip",
                    reason=f"Single asset paragraph {seq_indices[0]+1}. No pinning needed.",
                ))

            i = j
        else:
            # Narration paragraph — no sequence
            i += 1

    logger.info(
        f"Sequence analysis: {len(sequences)} sequences found across {len(paragraphs)} paragraphs. "
        f"{sum(1 for s in sequences if s.pin_instructor)} pinned sequences."
    )
    return sequences


def get_continuity_hints(
    paragraphs: list[dict],
    sequences: list[SequenceGroup],
) -> list[ContinuityHint]:
    """Generate per-paragraph continuity hints from sequence analysis.

    Returns a list with one ContinuityHint per paragraph (same order as paragraphs).
    """
    hints = []
    # Build a lookup: paragraph_index → (sequence_id, position_in_sequence)
    index_to_seq: dict[int, tuple[int, int]] = {}  # para_idx → (seq_id, pos_in_seq)
    for seq_id, seq in enumerate(sequences):
        for pos, para_idx in enumerate(seq.paragraph_indices):
            index_to_seq[para_idx] = (seq_id, pos)

    for i in range(len(paragraphs)):
        if i in index_to_seq:
            seq_id, pos = index_to_seq[i]
            seq = sequences[seq_id]
            seq_len = len(seq.paragraph_indices)

            hints.append(ContinuityHint(
                paragraph_index=i,
                is_sequence_start=(pos == 0),
                is_sequence_middle=(0 < pos < seq_len - 1),
                is_sequence_end=(pos == seq_len - 1),
                pin_instructor=seq.pin_instructor,
                pin_position=seq.suggested_pin_position,
                pin_size=seq.suggested_pin_size,
                pin_style=seq.suggested_pin_style,
                sequence_id=seq_id,
                note=seq.reason if pos == 0 else f"Continuing pinned sequence (paragraph {pos+1}/{seq_len}).",
            ))
        else:
            hints.append(ContinuityHint(
                paragraph_index=i,
                is_sequence_start=False,
                is_sequence_middle=False,
                is_sequence_end=False,
                pin_instructor=False,
                pin_position="center",
                pin_size="full",
                pin_style="normal",
                sequence_id=-1,
                note="Standalone paragraph, no sequence context.",
            ))

    return hints
