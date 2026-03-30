import re
from datetime import date, datetime

from app.domain.schemas.extraction import (
    ActionItem,
    Confidence,
    ExtractionResult,
    InsightItem,
)

STATUS_MAX_WORDS = 24
PRIORITY_MAX_WORDS = 18
SUMMARY_MAX_WORDS = 95
SUMMARY_BULLET_TARGET_WORDS = 32


def create_draft_canvas(
    extraction: ExtractionResult,
    source_label: str = "huddle_notes",
    title_override: str | None = None,
    compact_header: bool = False,
) -> str:
    title = title_override or (
        extraction.meeting_title or f"Meeting - {datetime.now().strftime('%Y-%m-%d')}"
    )
    sections = [
        build_meta_section(extraction, source_label, title, compact_header),
        build_summary_section(extraction),
        build_decisions_section(extraction.decisions),
        build_action_items_section(extraction.action_items),
        build_risks_section(extraction.risks),
        build_questions_section(extraction.open_questions),
        build_footer(source_label),
    ]
    return (
        f"\n\n{divider()}\n\n".join(section for section in sections if section.strip())
        + "\n"
    )


def create_dynamic_canvas(
    extraction: dict[str, object],
    selected_options: list[str] | None = None,
    custom_focus_prompt: str | None = None,
    source_label: str = "zoom_recording",
) -> str:
    normalized_extraction = _coerce_dynamic_extraction_result(extraction)
    normalized_options = set(_normalize_dynamic_selected_options(selected_options))
    render_all_optional_sections = not normalized_options

    sections = [
        build_meta_section(
            normalized_extraction,
            source_label,
            normalized_extraction.meeting_title
            or f"Meeting - {datetime.now().strftime('%Y-%m-%d')}",
        ),
        build_summary_section(normalized_extraction),
    ]

    discussion_overview = _coerce_text(extraction.get("discussion_overview"))
    if discussion_overview:
        sections.append(
            _build_dynamic_text_section("Detailed Context", discussion_overview)
        )

    if render_all_optional_sections or "key_decisions" in normalized_options:
        sections.append(build_decisions_section(normalized_extraction.decisions))

    if render_all_optional_sections or "action_items" in normalized_options:
        sections.append(build_action_items_section(normalized_extraction.action_items))

    if render_all_optional_sections or "risks" in normalized_options:
        sections.append(build_risks_section(normalized_extraction.risks))

    if render_all_optional_sections or "open_questions" in normalized_options:
        sections.append(build_questions_section(normalized_extraction.open_questions))

    custom_focus_analysis = _coerce_text(extraction.get("custom_focus_analysis"))
    if custom_focus_analysis:
        sections.append(
            _build_custom_focus_section(custom_focus_prompt, custom_focus_analysis)
        )

    if not any(section.strip() for section in sections[1:]):
        sections.append(
            _build_dynamic_text_section(
                "Executive Summary",
                "No structured meeting insights were extracted from the recording.",
            )
        )

    sections.append(build_footer(source_label))
    return (
        f"\n\n{divider()}\n\n".join(section for section in sections if section.strip())
        + "\n"
    )


def divider() -> str:
    return "---"


def bold(text: str) -> str:
    return f"*{text}*"


def italic(text: str) -> str:
    return f"_{text}_"


def header(text: str, level: int = 1) -> str:
    return f"{'#' * level} {text}"


def fmt_due(due_date: date | None) -> str:
    if due_date is None:
        return italic("TBD")
    return due_date.strftime("%d %b")


def build_meta_section(
    extraction: ExtractionResult,
    source_label: str,
    title: str,
    compact_header: bool = False,
) -> str:
    owners = ", ".join(extraction.owners)
    status_text = _compact_status_text(extraction.status_summary or "Needs review")
    next_review = (
        extraction.next_review_date.strftime("%d %b %Y")
        if extraction.next_review_date
        else italic("Not scheduled")
    )
    lines = [
        header(title),
        f":calendar: {bold('Date:')} {datetime.now().strftime('%d %b %Y')}",
        (
            f":traffic_light: {bold('Status:')} {status_text}   "
            f":spiral_calendar_pad: {bold('Next review:')} {next_review}"
        ),
    ]

    if extraction.priority_focus:
        lines.extend(
            [
                "",
                f":dart: {bold('Priority focus:')}",
                "",
                *_priority_focus_lines(extraction.priority_focus),
            ]
        )

    if owners:
        lines.extend(
            [
                "",
                f":busts_in_silhouette: {bold('Owners:')} {owners}",
            ]
        )
    return "\n".join(lines)


def build_summary_section(extraction: ExtractionResult) -> str:
    summary_text = _truncate_summary_text(_compose_summary_text(extraction))
    if not summary_text:
        return ""

    lines = [
        header("Meeting Summary", 2),
        "",
    ]
    lines.extend(f"- {item}" for item in _summary_bullets(summary_text))
    return "\n".join(lines)


def build_decisions_section(decisions: list[InsightItem]) -> str:
    if not decisions:
        return ""

    lines = [header("Key Decisions", 2), ""]
    for index, item in enumerate(decisions, start=1):
        lines.append(f"{index}. {item.content}")
    return "\n".join(lines)


def build_action_items_section(items: list[ActionItem]) -> str:
    if not items:
        return ""

    lines = [
        header("Action Items", 2),
        "",
        "| S.No | Task | Owner | Due | Status | Priority |",
        "| --- | --- | --- | --- | --- | --- |",
    ]

    for index, item in enumerate(items, start=1):
        row = [
            str(index),
            _escape_cell(item.content),
            _escape_cell(_owner_label(item)),
            _escape_cell(fmt_due(item.due_date)),
            _escape_cell(_status_label(item)),
            _escape_cell(_priority_label(item)),
        ]
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def build_risks_section(risks: list[InsightItem]) -> str:
    if not risks:
        return ""

    lines = [header("Open Risks", 2), ""]
    for index, risk in enumerate(risks, start=1):
        lines.append(f"{index}. {risk.content}")
    return "\n".join(lines)


def build_questions_section(open_questions: list[InsightItem]) -> str:
    if not open_questions:
        return ""

    lines = [header("Open Questions", 2), ""]
    for index, question in enumerate(open_questions, start=1):
        lines.append(f"{index}. {question.content}")
    return "\n".join(lines)


def build_footer(source_label: str) -> str:
    generated_at = datetime.now().strftime("%d %b %Y, %H:%M")
    return (
        f"{bold('Generated:')} {generated_at}   "
        f"{bold('Source:')} {source_label.replace('_', ' ').title()}"
    )


def _build_dynamic_text_section(title: str, text: str) -> str:
    lines = [header(title, 2), ""]
    lines.extend(f"- {item}" for item in _summary_bullets(text))
    return "\n".join(lines)


def _build_custom_focus_section(prompt: str | None, analysis: str) -> str:
    lines = [header("Custom Focus", 2), ""]
    if prompt:
        lines.append(f"{italic('Prompt:')} {prompt}")
        lines.append("")
    lines.extend(f"- {item}" for item in _summary_bullets(analysis))
    return "\n".join(lines)


def _escape_cell(value: str) -> str:
    return value.replace("\n", "<br>").replace("|", "\\|")


def _coerce_text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _coerce_insight_items(value: object) -> list[InsightItem]:
    if not isinstance(value, list):
        return []

    items: list[InsightItem] = []
    for entry in value:
        if isinstance(entry, InsightItem):
            items.append(entry)
            continue
        if isinstance(entry, dict):
            try:
                items.append(InsightItem.model_validate(entry))
            except Exception:
                continue
    return items


def _coerce_action_items(value: object) -> list[ActionItem]:
    if not isinstance(value, list):
        return []

    items: list[ActionItem] = []
    for entry in value:
        if isinstance(entry, ActionItem):
            items.append(entry)
            continue
        if isinstance(entry, dict):
            try:
                items.append(ActionItem.model_validate(entry))
            except Exception:
                continue
    return items


def _coerce_dynamic_extraction_result(
    extraction: dict[str, object]
) -> ExtractionResult:
    action_items = _coerce_action_items(extraction.get("action_items"))
    decisions = _coerce_insight_items(extraction.get("key_decisions"))
    risks = _coerce_insight_items(extraction.get("risks"))
    open_questions = _coerce_insight_items(extraction.get("open_questions"))
    owners = _coerce_owner_list(extraction.get("owners"))
    if not owners:
        owners = _unique_preserving_order(
            item.owner for item in action_items if item.owner
        )

    due_dates = _unique_preserving_order(
        item.due_date for item in action_items if item.due_date
    )
    next_review_date = _coerce_date_value(extraction.get("next_review_date"))
    if next_review_date is None and due_dates:
        next_review_date = due_dates[0]

    discussion_overview = _coerce_text(extraction.get("discussion_overview"))
    summary = _coerce_text(extraction.get("executive_summary")) or discussion_overview
    status_summary = _coerce_text(
        extraction.get("status_summary")
    ) or _derive_dynamic_status_summary(
        action_items,
        open_questions,
        risks,
    )
    priority_focus = _coerce_text(
        extraction.get("priority_focus")
    ) or _derive_dynamic_priority_focus(
        action_items,
        risks,
        open_questions,
        decisions,
    )
    confidence = (
        Confidence.high
        if any(
            [
                summary,
                discussion_overview,
                decisions,
                action_items,
                risks,
                open_questions,
            ]
        )
        else Confidence.needs_review
    )

    return ExtractionResult(
        meeting_title=_coerce_text(extraction.get("meeting_title"))
        or f"Meeting - {datetime.now().strftime('%Y-%m-%d')}",
        summary=summary,
        what_happened="",
        status_summary=status_summary,
        priority_focus=priority_focus,
        next_review_date=next_review_date,
        decisions=decisions,
        action_items=action_items,
        owners=owners,
        due_dates=due_dates,
        open_questions=open_questions,
        risks=risks,
        confidence_overall=confidence,
    )


def _coerce_date_value(value: object) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None
        try:
            return date.fromisoformat(cleaned)
        except ValueError:
            return None
    return None


def _coerce_owner_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    owners: list[str] = []
    for entry in value:
        cleaned = _coerce_text(entry)
        if cleaned and cleaned not in owners:
            owners.append(cleaned)
    return owners


def _normalize_dynamic_selected_options(
    selected_options: list[str] | None,
) -> list[str]:
    allowed = {
        "executive_summary",
        "action_items",
        "key_decisions",
        "risks",
        "open_questions",
    }
    normalized: list[str] = []
    for option in selected_options or []:
        cleaned = str(option).strip()
        if cleaned and cleaned in allowed and cleaned not in normalized:
            normalized.append(cleaned)
    return normalized


def _unique_preserving_order(values):
    unique_values = []
    for value in values:
        if value not in unique_values:
            unique_values.append(value)
    return unique_values


def _selected_option_label(option: str) -> str:
    return {
        "executive_summary": "Executive Summary",
        "action_items": "Action Items",
        "key_decisions": "Key Decisions",
        "risks": "Risks",
    }.get(option, option.replace("_", " ").title())


def _selected_output_label_text(
    selected_options: list[str] | None,
    custom_focus_prompt: str | None,
) -> str:
    labels = [
        _selected_option_label(option)
        for option in (selected_options or [])
        if str(option).strip()
    ]
    if custom_focus_prompt:
        labels.append("Custom Focus")
    return ", ".join(labels) if labels else "Executive Summary"


def _owner_label(item: ActionItem) -> str:
    if item.owner:
        return item.owner
    return "Needs review"


def _derive_dynamic_status_summary(
    action_items: list[ActionItem],
    open_questions: list[InsightItem],
    risks: list[InsightItem],
) -> str:
    if risks:
        return "At risk"
    if open_questions:
        return "Needs follow-up"
    if action_items:
        return "Execution in progress"
    return "Needs review"


def _derive_dynamic_priority_focus(
    action_items: list[ActionItem],
    risks: list[InsightItem],
    open_questions: list[InsightItem],
    decisions: list[InsightItem],
) -> str:
    if risks:
        return risks[0].content
    if open_questions:
        return open_questions[0].content
    if action_items:
        return action_items[0].content
    if decisions:
        return decisions[0].content
    return "Confirm next steps and owners."


def _status_label(item: ActionItem) -> str:
    mapping = {
        "To Do": "To do",
        "In Progress": "In progress",
        "Needs Review": "Needs review",
        "Blocked": "Blocked",
    }
    return mapping[_status_plain(item)]


def _status_plain(item: ActionItem) -> str:
    if (
        item.owner is None
        or item.due_date is None
        or item.confidence.value == "needs_review"
    ):
        return "Needs Review"
    if item.due_date < date.today():
        return "Blocked"
    if item.due_date <= date.today():
        return "In Progress"
    return "To Do"


def _priority_label(item: ActionItem) -> str:
    mapping = {
        "High": "High",
        "Medium": "Medium",
        "Low": "Low",
    }
    return mapping[_priority_plain(item)]


def _priority_plain(item: ActionItem) -> str:
    if not item.due_date:
        return "Medium"
    days_until_due = (item.due_date - date.today()).days
    if days_until_due <= 3:
        return "High"
    if days_until_due <= 7:
        return "Medium"
    return "Low"


def _priority_focus_lines(text: str) -> list[str]:
    compact_text = _compact_priority_focus(text)
    if not compact_text:
        return ["1. Confirm next steps and owners."]

    normalized = re.sub(r"\s+", " ", compact_text).strip()
    numbered_chunks = re.split(r"\s*\d+\.\s*", normalized)
    if len(numbered_chunks) > 2:
        items = [chunk.strip() for chunk in numbered_chunks if chunk.strip()]
        return [f"{index}. {item}" for index, item in enumerate(items, start=1)]

    sentences = [
        segment.strip(" -")
        for segment in re.split(r"(?<=[.!?])\s+|\s*;\s*", normalized)
        if segment.strip(" -")
    ]
    if len(sentences) == 1 and ", and " in normalized:
        sentences = [part.strip() for part in normalized.split(", ") if part.strip()]

    return [
        f"{index}. {sentence.rstrip('.')}"
        for index, sentence in enumerate(sentences[:3], start=1)
    ] or ["1. Confirm next steps and owners."]


def _compose_summary_text(extraction: ExtractionResult) -> str:
    summary = _clean_summary_text(extraction.summary, extraction.meeting_title)
    details = _clean_summary_text(extraction.what_happened, extraction.meeting_title)

    if details and summary and details.startswith(summary):
        return details
    if summary and details and summary.startswith(details):
        return summary
    if details and details != summary:
        return " ".join(part for part in [summary, details] if part).strip()
    return summary or details


def _clean_summary_text(text: str, meeting_title: str) -> str:
    if not text:
        return ""

    cleaned = " ".join(text.split())
    patterns = [
        rf"^{re.escape(meeting_title)}\s*[-:|]?\s*summary\s*:\s*",
        rf"^{re.escape(meeting_title)}\s*[-:|]?\s*",
        r"^summary\s*:\s*",
        r"^what happened\s*:\s*",
    ]
    for pattern in patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"\bsummary\s*:\s*", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(
        r"\bwhat happened\s*:\s*", "", cleaned, flags=re.IGNORECASE
    ).strip()
    return cleaned


def _truncate_summary_text(text: str) -> str:
    return _truncate_words(text, SUMMARY_MAX_WORDS)


def _summary_bullets(text: str) -> list[str]:
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", text)
        if sentence.strip()
    ]
    if not sentences:
        return [text]

    bullets: list[str] = []
    current_parts: list[str] = []
    current_words = 0

    for sentence in sentences:
        sentence_words = len(sentence.split())
        if (
            current_parts
            and current_words + sentence_words > SUMMARY_BULLET_TARGET_WORDS
        ):
            bullets.append(" ".join(current_parts).strip())
            current_parts = [sentence]
            current_words = sentence_words
            continue

        current_parts.append(sentence)
        current_words += sentence_words

    if current_parts:
        bullets.append(" ".join(current_parts).strip())

    return bullets or [text]


def _compact_status_text(text: str) -> str:
    return _truncate_words(text, STATUS_MAX_WORDS)


def _compact_priority_focus(text: str) -> str:
    default = "Confirm next steps and owners."
    return _truncate_words(text or default, PRIORITY_MAX_WORDS)


def _truncate_words(text: str, max_words: int) -> str:
    cleaned = " ".join(text.split())
    if not cleaned:
        return ""

    words = cleaned.split()
    if len(words) <= max_words:
        return cleaned

    truncated_words = words[:max_words]
    while truncated_words and truncated_words[-1].lower().rstrip(",;:-") in {
        "and",
        "or",
        "with",
        "to",
        "for",
        "of",
    }:
        truncated_words.pop()

    truncated = " ".join(truncated_words).rstrip(",;:-")
    if truncated.endswith((".", "!", "?")):
        return truncated
    return f"{truncated}..."
