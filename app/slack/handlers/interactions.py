from __future__ import annotations

import json

from app.integrations.slack_client import slack_client
from app.logger import logger
from app.workers.tasks import process_meeting_task


def register_interactions(bolt_app) -> None:
    @bolt_app.view("canvas_config_modal")
    def handle_canvas_config_submission(ack, body):
        ack()

        try:
            metadata = _parse_private_metadata(body)
            channel_id = metadata["channel_id"]
            url = metadata["text_input"]
            user_id = body["user"]["id"]
            selected_options = _extract_selected_options(body)
            custom_prompt = _extract_custom_focus(body)

            slack_client.client.chat_postMessage(
                channel=channel_id,
                text=(
                    ":hourglass_flowing_sand: Your meeting is being processed "
                    "in the background..."
                ),
            )
            process_meeting_task.delay(
                url,
                selected_options,
                custom_prompt,
                channel_id,
                user_id,
            )
        except Exception:
            logger.exception("Failed to handle canvas configuration modal submission")
            channel_id = _safe_channel_id(body)
            if channel_id:
                try:
                    slack_client.client.chat_postMessage(
                        channel=channel_id,
                        text=(
                            ":warning: FollowThru could not start the background "
                            "meeting pipeline. Please try again."
                        ),
                    )
                except Exception:
                    logger.exception(
                        "Failed to send modal submission failure message to Slack"
                    )


def _parse_private_metadata(body: dict) -> dict[str, str]:
    metadata = body.get("view", {}).get("private_metadata") or "{}"
    parsed = json.loads(metadata)
    if not isinstance(parsed, dict):
        raise ValueError("Modal private_metadata must be a JSON object.")
    payload = {
        "channel_id": str(parsed.get("channel_id") or "").strip(),
        "text_input": str(parsed.get("text_input") or "").strip(),
    }
    if not payload["channel_id"] or not payload["text_input"]:
        raise ValueError("Modal private_metadata is missing channel_id or text_input.")
    return payload


def _extract_selected_options(body: dict) -> list[str]:
    state_values = body.get("view", {}).get("state", {}).get("values", {})
    selected_options = (
        state_values.get("canvas_options", {})
        .get("selected_options", {})
        .get("selected_options", [])
    )
    values: list[str] = []
    for option in selected_options:
        value = (option or {}).get("value")
        if value:
            values.append(value)
    return values


def _extract_custom_focus(body: dict) -> str | None:
    state_values = body.get("view", {}).get("state", {}).get("values", {})
    value = (
        state_values.get("custom_focus_block", {})
        .get("custom_focus", {})
        .get("value")
    )
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _safe_channel_id(body: dict) -> str | None:
    try:
        channel_id = _parse_private_metadata(body).get("channel_id")
    except Exception:
        return None
    return channel_id or None
