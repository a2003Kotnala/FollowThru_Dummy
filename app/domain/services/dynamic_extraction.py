from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import date

import httpx
from pydantic import BaseModel, Field, create_model

from app.config import settings
from app.domain.schemas.extraction import ActionItem, ExtractionResult, InsightItem
from app.domain.services.extraction_service import (
    extract_structured_meeting_data_with_rules,
)

OPTION_LABELS = {
    "executive_summary": "Executive Summary",
    "action_items": "Action Items",
    "key_decisions": "Key Decisions",
    "risks": "Risks",
    "open_questions": "Open Questions",
}
DEFAULT_DETAIL_OPTIONS = [
    "executive_summary",
    "action_items",
    "key_decisions",
    "risks",
    "open_questions",
]
EXTRACTION_TIMEOUT_SECONDS = 180.0
TRANSCRIPT_MAX_CHARS = 120_000
MIN_SUBSTANTIVE_TEXT_WORDS = 8


def build_dynamic_extraction_model(
    selected_options: Sequence[str],
    custom_prompt: str | None = None,
) -> type[BaseModel]:
    fields: dict[str, tuple[object, object]] = {
        "meeting_title": (
            str,
            Field(
                description="A concise title for the meeting or recording.",
            ),
        ),
        "executive_summary": (
            str,
            Field(
                description=(
                    "A dense factual summary of the meeting that captures the main "
                    "goal, outcome, and key dependencies from the transcript."
                ),
            ),
        ),
        "discussion_overview": (
            str,
            Field(
                description=(
                    "A detailed recap of what happened in the meeting. Preserve "
                    "specific commitments, launch criteria, customer asks, "
                    "dependencies, and sequencing without generic filler."
                ),
            ),
        ),
        "status_summary": (
            str,
            Field(
                description=(
                    "A short concrete status line describing the current execution "
                    "or readiness state."
                ),
            ),
        ),
        "priority_focus": (
            str,
            Field(
                description=(
                    "The highest-priority next focus area or dependency the team "
                    "needs to handle."
                ),
            ),
        ),
        "next_review_date": (
            date | None,
            Field(
                default=None,
                description=(
                    "The earliest explicit checkpoint, review date, or deadline "
                    "that should anchor the team's next review. Use null if none."
                ),
            ),
        ),
        "action_items": (
            list[ActionItem],
            Field(
                default_factory=list,
                description=(
                    "All explicit follow-up actions with owners and due dates when "
                    "the transcript states them."
                ),
            ),
        ),
        "key_decisions": (
            list[InsightItem],
            Field(
                default_factory=list,
                description="Decisions that were clearly made during the meeting.",
            ),
        ),
        "risks": (
            list[InsightItem],
            Field(
                default_factory=list,
                description="Risks, blockers, or concerns grounded in the transcript.",
            ),
        ),
        "open_questions": (
            list[InsightItem],
            Field(
                default_factory=list,
                description=(
                    "Unresolved questions, tradeoffs, or decision points explicitly "
                    "raised in the transcript."
                ),
            ),
        ),
    }

    if custom_prompt:
        fields["custom_focus_analysis"] = (
            str,
            Field(
                description=(
                    "A focused response to the user's custom analysis request: "
                    f"{custom_prompt}"
                ),
            ),
        )

    return create_model("DynamicMeetingExtraction", **fields)


def extract_dynamic_intelligence(
    transcript: str,
    selected_options: Sequence[str],
    custom_prompt: str | None = None,
) -> dict[str, object]:
    if not settings.resolved_llm_api_key:
        raise RuntimeError(
            "No LLM API key is configured. Set OPENAI_API_KEY, "
            "GEMINI_API_KEY, or LLM_API_KEY."
        )

    response_model = build_dynamic_extraction_model(selected_options, custom_prompt)
    prepared_transcript = _prepare_transcript_for_extraction(transcript)
    requested_outputs = _requested_outputs_text(selected_options, custom_prompt)
    response_schema = json.dumps(
        response_model.model_json_schema(),
        ensure_ascii=True,
    )
    user_prompt = (
        "Analyze the meeting transcript and return only well-grounded structured "
        "data.\n"
        "Always produce a detailed operating canvas, not a short generic summary.\n"
        "The transcript contains a mix of English and Hindi (Hinglish).\n"
        f"Give extra attention to these areas: {requested_outputs}\n"
        "Preserve concrete names, teams, customers, dates, launch criteria, "
        "dependencies, metrics, and sequencing when they are stated.\n"
        "Prefer dense factual output over polished filler or leadership-speak.\n"
        "Do not invent owners, due dates, decisions, risks, or open questions.\n"
        "If a requested list is not present in the transcript, return an empty "
        "list for that field. Use null for next_review_date when no explicit date "
        "is available.\n\n"
        f"Transcript:\n{prepared_transcript}"
    )

    try:
        payload = {
            "model": settings.resolved_llm_model,
            "temperature": 0.1,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You extract detailed delivery execution intelligence "
                        "from meeting transcripts for Slack canvases. Return a "
                        "single JSON object that matches this schema exactly: "
                        f"{response_schema}"
                    ),
                },
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
        }
        with httpx.Client(
            timeout=max(settings.llm_timeout_seconds, EXTRACTION_TIMEOUT_SECONDS)
        ) as client:
            response = client.post(
                f"{settings.resolved_llm_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.resolved_llm_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            completion = response.json()

        content = _coerce_message_content(
            completion["choices"][0]["message"]["content"]
        )
        if not content:
            raise RuntimeError(
                "The configured LLM returned an empty structured response."
            )
        parsed = response_model.model_validate(json.loads(content))
        fallback = extract_structured_meeting_data_with_rules(prepared_transcript)
        return _merge_with_rule_based_fallback(
            parsed.model_dump(exclude_none=True),
            fallback,
        )
    except Exception as exc:
        raise RuntimeError(f"Structured extraction failed: {exc}") from exc


def _normalize_options(selected_options: Sequence[str]) -> list[str]:
    normalized: list[str] = []
    for option in selected_options:
        cleaned = str(option).strip()
        if cleaned and cleaned in OPTION_LABELS and cleaned not in normalized:
            normalized.append(cleaned)
    return normalized


def _requested_outputs_text(
    selected_options: Sequence[str],
    custom_prompt: str | None,
) -> str:
    normalized_options = _normalize_options(selected_options) or DEFAULT_DETAIL_OPTIONS
    labels = [OPTION_LABELS[option] for option in normalized_options]
    if custom_prompt:
        labels.append(f"Custom Focus ({custom_prompt})")
    return ", ".join(labels)


def _prepare_transcript_for_extraction(transcript: str) -> str:
    cleaned = transcript.strip()
    if len(cleaned) <= TRANSCRIPT_MAX_CHARS:
        return cleaned

    head = cleaned[:40_000].strip()
    middle_start = max((len(cleaned) // 2) - 20_000, 0)
    middle = cleaned[middle_start : middle_start + 40_000].strip()
    tail = cleaned[-40_000:].strip()
    return (
        f"{head}\n\n[Transcript truncated for length]\n\n"
        f"{middle}\n\n[Transcript tail]\n\n{tail}"
    )


def _coerce_message_content(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "") for block in content if isinstance(block, dict)
        )
    return ""


def _merge_with_rule_based_fallback(
    extraction: dict[str, object],
    fallback: ExtractionResult,
) -> dict[str, object]:
    merged: dict[str, object] = {
        "meeting_title": _prefer_text(
            extraction.get("meeting_title"),
            fallback.meeting_title,
        )
        or "Execution Review",
        "executive_summary": _prefer_descriptive_text(
            extraction.get("executive_summary"),
            fallback.summary,
        ),
        "discussion_overview": _prefer_descriptive_text(
            extraction.get("discussion_overview"),
            fallback.what_happened or fallback.summary,
        ),
        "status_summary": _prefer_text(
            extraction.get("status_summary"),
            fallback.status_summary,
        ),
        "priority_focus": _prefer_text(
            extraction.get("priority_focus"),
            fallback.priority_focus,
        ),
        "action_items": _merge_action_items(
            extraction.get("action_items"),
            fallback.action_items,
        ),
        "key_decisions": _merge_insight_items(
            extraction.get("key_decisions"),
            fallback.decisions,
        ),
        "risks": _merge_insight_items(
            extraction.get("risks"),
            fallback.risks,
        ),
        "open_questions": _merge_insight_items(
            extraction.get("open_questions"),
            fallback.open_questions,
        ),
    }

    next_review_date = extraction.get("next_review_date")
    if next_review_date is None and fallback.next_review_date is not None:
        next_review_date = fallback.next_review_date.isoformat()
    if next_review_date is not None:
        merged["next_review_date"] = next_review_date

    custom_focus_analysis = _clean_text(extraction.get("custom_focus_analysis"))
    if custom_focus_analysis:
        merged["custom_focus_analysis"] = custom_focus_analysis

    return merged


def _prefer_descriptive_text(primary: object, fallback: str) -> str:
    cleaned_primary = _clean_text(primary)
    if _is_substantive_text(cleaned_primary):
        return cleaned_primary

    cleaned_fallback = _clean_text(fallback)
    if cleaned_primary and cleaned_primary == cleaned_fallback:
        return cleaned_primary
    return cleaned_fallback or cleaned_primary


def _prefer_text(primary: object, fallback: str) -> str:
    return _clean_text(primary) or _clean_text(fallback)


def _clean_text(value: object) -> str:
    if isinstance(value, str):
        return " ".join(value.split()).strip()
    return ""


def _is_substantive_text(value: str) -> bool:
    return len(value.split()) >= MIN_SUBSTANTIVE_TEXT_WORDS


def _merge_action_items(
    extracted: object,
    fallback_items: Sequence[ActionItem],
) -> list[dict[str, object]]:
    items: list[ActionItem] = []
    seen: set[tuple[str, str | None, str | None]] = set()

    for entry in list(extracted) if isinstance(extracted, list) else []:
        item = _coerce_action_item(entry)
        if item is None:
            continue
        key = _action_item_key(item)
        if key in seen:
            continue
        items.append(item)
        seen.add(key)

    for item in fallback_items:
        key = _action_item_key(item)
        if key in seen:
            continue
        items.append(item)
        seen.add(key)

    return [item.model_dump(exclude_none=True) for item in items]


def _merge_insight_items(
    extracted: object,
    fallback_items: Sequence[InsightItem],
) -> list[dict[str, object]]:
    items: list[InsightItem] = []
    seen: set[str] = set()

    for entry in list(extracted) if isinstance(extracted, list) else []:
        item = _coerce_insight_item(entry)
        if item is None:
            continue
        key = _insight_item_key(item)
        if key in seen:
            continue
        items.append(item)
        seen.add(key)

    for item in fallback_items:
        key = _insight_item_key(item)
        if key in seen:
            continue
        items.append(item)
        seen.add(key)

    return [item.model_dump(exclude_none=True) for item in items]


def _coerce_action_item(entry: object) -> ActionItem | None:
    if isinstance(entry, ActionItem):
        return entry
    if isinstance(entry, dict):
        try:
            return ActionItem.model_validate(entry)
        except Exception:
            return None
    return None


def _coerce_insight_item(entry: object) -> InsightItem | None:
    if isinstance(entry, InsightItem):
        return entry
    if isinstance(entry, dict):
        try:
            return InsightItem.model_validate(entry)
        except Exception:
            return None
    return None


def _action_item_key(item: ActionItem) -> tuple[str, str | None, str | None]:
    due_date = item.due_date.isoformat() if item.due_date else None
    return (_normalized_key(item.content), item.owner, due_date)


def _insight_item_key(item: InsightItem) -> str:
    return _normalized_key(item.content)


def _normalized_key(value: str) -> str:
    return " ".join(value.lower().split())
