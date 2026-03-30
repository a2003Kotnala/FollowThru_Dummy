from __future__ import annotations

import json

DEFAULT_CANVAS_OPTIONS = [
    "executive_summary",
    "action_items",
    "key_decisions",
    "risks",
    "open_questions",
]


def build_canvas_configuration_modal(
    channel_id: str,
    trigger_id: str,
    text_input: str,
) -> dict:
    del trigger_id

    private_metadata = json.dumps(
        {
            "channel_id": channel_id,
            "text_input": text_input,
        }
    )

    return {
        "type": "modal",
        "callback_id": "canvas_config_modal",
        "private_metadata": private_metadata,
        "title": {
            "type": "plain_text",
            "text": "Configure Canvas",
        },
        "submit": {
            "type": "plain_text",
            "text": "Process",
        },
        "close": {
            "type": "plain_text",
            "text": "Cancel",
        },
        "blocks": [
            {
                "type": "section",
                "block_id": "canvas_options",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "Detailed canvas sections are preselected. "
                        "Uncheck anything you do not want, or add a custom focus."
                    ),
                },
                "accessory": {
                    "type": "checkboxes",
                    "action_id": "selected_options",
                    "options": [
                        {
                            "text": {
                                "type": "plain_text",
                                "text": "Executive Summary",
                            },
                            "value": "executive_summary",
                        },
                        {
                            "text": {
                                "type": "plain_text",
                                "text": "Action Items",
                            },
                            "value": "action_items",
                        },
                        {
                            "text": {
                                "type": "plain_text",
                                "text": "Key Decisions",
                            },
                            "value": "key_decisions",
                        },
                        {
                            "text": {
                                "type": "plain_text",
                                "text": "Risks",
                            },
                            "value": "risks",
                        },
                        {
                            "text": {
                                "type": "plain_text",
                                "text": "Open Questions",
                            },
                            "value": "open_questions",
                        },
                    ],
                    "initial_options": [
                        {
                            "text": {
                                "type": "plain_text",
                                "text": "Executive Summary",
                            },
                            "value": "executive_summary",
                        },
                        {
                            "text": {
                                "type": "plain_text",
                                "text": "Action Items",
                            },
                            "value": "action_items",
                        },
                        {
                            "text": {
                                "type": "plain_text",
                                "text": "Key Decisions",
                            },
                            "value": "key_decisions",
                        },
                        {
                            "text": {
                                "type": "plain_text",
                                "text": "Risks",
                            },
                            "value": "risks",
                        },
                        {
                            "text": {
                                "type": "plain_text",
                                "text": "Open Questions",
                            },
                            "value": "open_questions",
                        },
                    ],
                },
            },
            {
                "type": "input",
                "block_id": "custom_focus_block",
                "optional": True,
                "label": {
                    "type": "plain_text",
                    "text": "Custom Focus",
                },
                "element": {
                    "type": "plain_text_input",
                    "action_id": "custom_focus",
                    "multiline": True,
                    "placeholder": {
                        "type": "plain_text",
                        "text": (
                            "Optional: highlight blockers, client asks, "
                            "delivery gaps, or any custom angle."
                        ),
                    },
                },
            },
        ],
    }
