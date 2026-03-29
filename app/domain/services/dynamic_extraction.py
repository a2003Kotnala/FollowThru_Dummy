from __future__ import annotations

from typing import Sequence

from openai import OpenAI
from pydantic import BaseModel, Field, create_model

from app.config import settings
from app.domain.schemas.extraction import ActionItem, InsightItem

OPTION_LABELS = {
    "executive_summary": "Executive Summary",
    "action_items": "Action Items",
    "key_decisions": "Key Decisions",
    "risks": "Risks",
}
EXTRACTION_MODEL = "gpt-4o"
EXTRACTION_TIMEOUT_SECONDS = 180.0
TRANSCRIPT_MAX_CHARS = 120_000


def build_dynamic_extraction_model(
    selected_options: Sequence[str],
    custom_prompt: str | None = None,
) -> type[BaseModel]:
    normalized_options = _normalize_options(selected_options)
    if not normalized_options and not custom_prompt:
        normalized_options = ["executive_summary"]

    fields: dict[str, tuple[object, object]] = {
        "meeting_title": (
            str,
            Field(
                description="A concise title for the meeting or recording.",
            ),
        )
    }

    if "executive_summary" in normalized_options:
        fields["executive_summary"] = (
            str,
            Field(
                description=(
                    "A concise executive summary of the meeting, grounded in the "
                    "transcript."
                ),
            ),
        )

    if "action_items" in normalized_options:
        fields["action_items"] = (
            list[ActionItem],
            Field(
                default_factory=list,
                description=(
                    "Action items with owners and due dates when explicitly stated."
                ),
            ),
        )

    if "key_decisions" in normalized_options:
        fields["key_decisions"] = (
            list[InsightItem],
            Field(
                default_factory=list,
                description="Decisions that were clearly made during the meeting.",
            ),
        )

    if "risks" in normalized_options:
        fields["risks"] = (
            list[InsightItem],
            Field(
                default_factory=list,
                description="Risks, blockers, or concerns grounded in the transcript.",
            ),
        )

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
    if not settings.openai_api_key:
        raise RuntimeError("LLM_API_KEY or OPENAI_API_KEY is not configured.")

    response_model = build_dynamic_extraction_model(selected_options, custom_prompt)
    client = OpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.resolved_llm_base_url,
        timeout=max(settings.openai_timeout_seconds, EXTRACTION_TIMEOUT_SECONDS),
    )

    prepared_transcript = _prepare_transcript_for_extraction(transcript)
    requested_outputs = _requested_outputs_text(selected_options, custom_prompt)
    user_prompt = (
        "Analyze the meeting transcript and return only well-grounded structured "
        "data.\n"
        "The transcript contains a mix of English and Hindi (Hinglish).\n"
        f"Requested outputs: {requested_outputs}\n"
        "Do not invent owners, due dates, decisions, or risks.\n"
        "If a requested list is not present in the transcript, return an empty "
        "list for that field.\n\n"
        f"Transcript:\n{prepared_transcript}"
    )

    try:
        completion = client.beta.chat.completions.parse(
            model=EXTRACTION_MODEL,
            temperature=0.1,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You extract structured intelligence from meeting "
                        "transcripts for Slack canvases."
                    ),
                },
                {"role": "user", "content": user_prompt},
            ],
            response_format=response_model,
        )
        parsed = completion.choices[0].message.parsed
        if parsed is None:
            raise RuntimeError("OpenAI returned no parsed structured response.")
        return parsed.model_dump(exclude_none=True)
    except Exception as exc:
        raise RuntimeError(f"GPT-4o extraction failed: {exc}") from exc
    finally:
        client.close()


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
    normalized_options = _normalize_options(selected_options)
    labels = [OPTION_LABELS[option] for option in normalized_options]
    if custom_prompt:
        labels.append(f"Custom Focus ({custom_prompt})")
    return ", ".join(labels) if labels else "Executive Summary"


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
