from datetime import date

from app.domain.schemas.extraction import (
    ActionItem,
    Confidence,
    ExtractionResult,
    InsightItem,
)
from app.domain.services.canvas_composer import (
    create_draft_canvas,
    create_dynamic_canvas,
)


def test_create_draft_canvas_renders_clean_professional_layout():
    extraction = ExtractionResult(
        meeting_title="Launch Readiness Review",
        summary="Reviewed launch readiness.",
        what_happened="The team confirmed scope and assigned follow-ups.",
        status_summary="Execution in progress",
        priority_focus="Prepare beta checklist",
        next_review_date=date(2026, 3, 20),
        decisions=[
            InsightItem(content="Launch internal beta", confidence=Confidence.high)
        ],
        action_items=[
            ActionItem(
                content="Prepare beta checklist",
                owner="maya",
                due_date=date(2026, 3, 20),
                confidence=Confidence.high,
            )
        ],
        owners=["maya"],
        due_dates=[date(2026, 3, 20)],
        open_questions=[
            InsightItem(
                content="Who signs off on release messaging?",
                confidence=Confidence.needs_review,
            )
        ],
        risks=[
            InsightItem(
                content="QA bandwidth is still limited.",
                confidence=Confidence.medium,
            )
        ],
        confidence_overall=Confidence.high,
    )

    canvas = create_draft_canvas(extraction, "manual-demo")

    assert "# Launch Readiness Review" in canvas
    assert ":calendar: *Date:*" in canvas
    assert ":traffic_light: *Status:* Execution in progress" in canvas
    assert ":spiral_calendar_pad: *Next review:* 20 Mar 2026" in canvas
    assert ":dart: *Priority focus:*" in canvas
    assert "1. Prepare beta checklist" in canvas
    assert ":busts_in_silhouette: *Owners:* maya" in canvas
    assert "## Meeting Summary" in canvas
    assert "## Key Decisions" in canvas
    assert "## Action Items" in canvas
    assert "| S.No | Task | Owner | Due | Status | Priority |" in canvas
    assert "Prepare beta checklist" in canvas
    assert "## Open Risks" in canvas
    assert "1. QA bandwidth is still limited." in canvas
    assert "## Open Questions" in canvas
    assert "1. Who signs off on release messaging?" in canvas
    assert "*Generated:*" in canvas
    assert "| Source | Confidence | Actions | Attention |" not in canvas
    assert "`----------` 0% (0/1 complete)" not in canvas
    assert "Action Canvas generated from" not in canvas
    assert "_Text |" not in canvas
    assert ":grey_question:" not in canvas
    assert ":red_circle:" not in canvas
    assert ":large_yellow_circle:" not in canvas


def test_create_draft_canvas_deduplicates_summary_content():
    extraction = ExtractionResult(
        meeting_title="Roadmap Sync - Product, Design, Engineering",
        summary="Roadmap Sync - Product, Design, Engineering Summary:",
        what_happened=(
            "Roadmap Sync - Product, Design, Engineering Summary: "
            "The team reviewed roadmap priorities and agreed to shift execution focus."
        ),
        confidence_overall=Confidence.high,
    )

    canvas = create_draft_canvas(extraction, "manual-demo")

    assert "## Meeting Summary" in canvas
    assert " Roadmap Sync - Product, Design, Engineering Summary:" not in canvas
    assert (
        "The team reviewed roadmap priorities and agreed to shift execution focus."
        in canvas
    )


def test_create_draft_canvas_truncates_long_status_and_summary():
    long_status = (
        "The backend is largely ready with transcript fallback and improved DM "
        "workflow implemented, but significant unknowns remain around live "
        "Slack transcript access, permissions, and publishing behavior."
    )
    long_summary = " ".join(
        f"Sentence {index} covers launch readiness, blockers, owners, and next steps."
        for index in range(1, 13)
    )
    extraction = ExtractionResult(
        meeting_title="FollowThru Launch Review",
        summary=long_summary,
        what_happened=long_summary,
        status_summary=long_status,
        priority_focus=(
            "Prove the live Slack flow works, clean up setup, and document the "
            "happy path for the team before rollout."
        ),
        confidence_overall=Confidence.high,
    )

    canvas = create_draft_canvas(extraction, "manual-demo")

    assert ":traffic_light: *Status:*" in canvas
    assert "publishing behavior." not in canvas
    assert "permissions..." in canvas
    assert "Sentence 12 covers launch readiness" not in canvas
    assert "1. Prove the live Slack flow works" in canvas
    assert (
        "- Sentence 1 covers launch readiness, blockers, owners, and next steps."
        in canvas
    )


def test_create_draft_canvas_supports_compact_dm_header():
    extraction = ExtractionResult(
        meeting_title="FollowThru Launch Readiness Review",
        summary="Reviewed launch readiness for the DM flow.",
        confidence_overall=Confidence.high,
    )

    canvas = create_draft_canvas(
        extraction,
        "text",
        title_override="Launch Readiness Review | 23 Mar 02:49 PM",
        compact_header=True,
    )

    assert "# Launch Readiness Review | 23 Mar 02:49 PM" in canvas
    assert "Action Canvas generated from" not in canvas
    assert "_Text | High confidence_" not in canvas


def test_create_draft_canvas_omits_empty_sections():
    extraction = ExtractionResult(
        meeting_title="Quiet Sync",
        summary="A short alignment call with no concrete follow-ups.",
        confidence_overall=Confidence.needs_review,
    )

    canvas = create_draft_canvas(extraction, "text")

    assert "## Meeting Summary" in canvas
    assert "## Key Decisions" not in canvas
    assert "## Action Items" not in canvas
    assert "## Open Risks" not in canvas
    assert "## Open Questions" not in canvas
    assert "None captured" not in canvas


def test_create_dynamic_canvas_renders_detailed_execution_sections():
    extraction = {
        "meeting_title": "Project Atlas Pilot Readiness Review",
        "executive_summary": (
            "The team confirmed BrightPath can still target a monitored pilot "
            "launch, while Nova Retail will be delayed until enablement and "
            "onboarding gaps are closed."
        ),
        "discussion_overview": (
            "Engineering reported an unresolved permissions sync bug and duplicate "
            "alert events. Customer Success flagged Nova's onboarding needs, and "
            "the group aligned on launch sequencing, support ownership, metrics, "
            "and a go or no-go checkpoint."
        ),
        "status_summary": "At risk pending engineering fixes and QA retest.",
        "priority_focus": (
            "Land permissions sync and duplicate alert fixes before the mid-week "
            "QA retest window."
        ),
        "next_review_date": "2026-04-02",
        "action_items": [
            {
                "content": "Fix duplicate alert dedupe logic and run replay validation",
                "owner": "Arjun",
                "due_date": "2026-04-01",
                "confidence": "high",
            }
        ],
        "key_decisions": [
            {
                "content": (
                    "Proceed with the BrightPath pilot launch on 2026-04-06 if the "
                    "defects are fixed by 2026-04-03."
                ),
                "confidence": "high",
            }
        ],
        "risks": [
            {
                "content": (
                    "Missing the Wednesday and Thursday QA retest window would put "
                    "the BrightPath pilot at risk."
                ),
                "confidence": "medium",
            }
        ],
        "open_questions": [
            {
                "content": (
                    "Should low-confidence alerts stay disabled during the first "
                    "pilot week?"
                ),
                "confidence": "needs_review",
            }
        ],
        "custom_focus_analysis": (
            "Leadership should watch the engineering and QA dependency closely "
            "because the launch decision hinges on staging verification."
        ),
    }

    canvas = create_dynamic_canvas(
        extraction=extraction,
        selected_options=[
            "executive_summary",
            "action_items",
            "key_decisions",
            "risks",
            "open_questions",
        ],
        custom_focus_prompt="Highlight launch blockers for leadership.",
    )

    assert "# Project Atlas Pilot Readiness Review" in canvas
    assert (
        ":traffic_light: *Status:* At risk pending engineering fixes and QA retest."
        in canvas
    )
    assert ":spiral_calendar_pad: *Next review:* 02 Apr 2026" in canvas
    assert "## Meeting Summary" in canvas
    assert "## Detailed Context" in canvas
    assert "## Key Decisions" in canvas
    assert "## Action Items" in canvas
    assert "## Open Risks" in canvas
    assert "## Open Questions" in canvas
    assert "## Custom Focus" in canvas
    assert "Proceed with the BrightPath pilot launch" in canvas
    assert "Fix duplicate alert dedupe logic and run replay validation" in canvas
    assert "Should low-confidence alerts stay disabled" in canvas
    assert "Requested outputs" not in canvas
