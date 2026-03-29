import json

from app.slack.handlers.interactions import register_interactions


class FakeBoltApp:
    def __init__(self) -> None:
        self.view_handlers = {}

    def view(self, name: str):
        def decorator(func):
            self.view_handlers[name] = func
            return func

        return decorator


def test_canvas_modal_submission_acknowledges_posts_status_and_enqueues(monkeypatch):
    app = FakeBoltApp()
    register_interactions(app)

    acked: list[bool] = []
    posted_messages: list[tuple[str, str]] = []
    queued_jobs: list[tuple[str, list[str], str | None, str, str]] = []

    monkeypatch.setattr(
        "app.slack.handlers.interactions.slack_client.client.chat_postMessage",
        lambda channel, text: posted_messages.append((channel, text)),
    )
    monkeypatch.setattr(
        "app.slack.handlers.interactions.process_meeting_task.delay",
        lambda url, selected_options, custom_prompt, channel_id, user_id: queued_jobs.append(
            (url, selected_options, custom_prompt, channel_id, user_id)
        ),
    )

    app.view_handlers["canvas_config_modal"](
        ack=lambda: acked.append(True),
        body={
            "user": {"id": "U123"},
            "view": {
                "private_metadata": json.dumps(
                    {
                        "channel_id": "C123",
                        "text_input": "https://zoom.example.com/recording.mp4",
                    }
                ),
                "state": {
                    "values": {
                        "canvas_options": {
                            "selected_options": {
                                "selected_options": [
                                    {"value": "executive_summary"},
                                    {"value": "action_items"},
                                ]
                            }
                        },
                        "custom_focus_block": {
                            "custom_focus": {
                                "value": "Flag delivery blockers for leadership."
                            }
                        },
                    }
                },
            },
        },
    )

    assert acked == [True]
    assert posted_messages == [
        (
            "C123",
            ":hourglass_flowing_sand: Your meeting is being processed in the background...",
        )
    ]
    assert queued_jobs == [
        (
            "https://zoom.example.com/recording.mp4",
            ["executive_summary", "action_items"],
            "Flag delivery blockers for leadership.",
            "C123",
            "U123",
        )
    ]
