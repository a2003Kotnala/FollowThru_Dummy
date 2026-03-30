from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.db.base import engine
from app.domain.services.canvas_composer import create_dynamic_canvas
from app.domain.services.dynamic_extraction import extract_dynamic_intelligence
from app.domain.services.parallel_whisper import transcribe_audio_chunks
from app.integrations.slack_client import slack_client
from app.logger import logger
from app.workers.media_processor import extract_audio_chunks

DOWNLOAD_TIMEOUT_SECONDS = 300.0

celery_app = None
if settings.followthru_job_execution_mode != "threaded":
    try:
        from app.workers.celery_app import celery_app as configured_celery_app

        celery_app = configured_celery_app
    except Exception as exc:  # pragma: no cover - depends on local worker setup
        logger.warning(
            "Celery is unavailable; FollowThru meeting jobs will run in a thread: %s",
            exc,
        )


def process_meeting_task(
    url: str,
    selected_options: list[str],
    custom_prompt: str | None,
    channel_id: str,
    user_id: str,
) -> dict[str, str]:
    with TemporaryDirectory(prefix="followthru-meeting-") as temp_dir:
        try:
            video_path = _download_recording(url, Path(temp_dir))
            chunk_paths = extract_audio_chunks(
                input_source=video_path,
                output_dir=Path(temp_dir) / "chunks",
            )
            transcript = asyncio.run(transcribe_audio_chunks(chunk_paths))
            extraction = extract_dynamic_intelligence(
                transcript=transcript,
                selected_options=selected_options,
                custom_prompt=custom_prompt,
            )
            canvas_markdown = create_dynamic_canvas(
                extraction=extraction,
                selected_options=selected_options,
                custom_focus_prompt=custom_prompt,
            )
            canvas_title = _build_canvas_title(extraction)
            canvas = slack_client.upload_canvas(
                channel_id=channel_id,
                content=canvas_markdown,
                title=canvas_title,
                slack_user_id=user_id,
            )
            slack_client.client.chat_postMessage(
                channel=channel_id,
                text=(
                    ":white_check_mark: Your meeting Canvas is ready. "
                    f"Slack canvas ID: {canvas['id']}."
                ),
            )
            return {
                "canvas_id": str(canvas["id"]),
                "canvas_title": str(canvas["title"]),
            }
        except Exception as exc:
            logger.exception("Background meeting processing failed for url=%s", url)
            _notify_processing_failure(channel_id, exc)
            raise
        finally:
            try:
                engine.dispose()
            except Exception as db_exc:  # pragma: no cover - defensive cleanup
                logger.warning(
                    "Failed to dispose SQLAlchemy engine after meeting task: %s",
                    db_exc,
                )


def _delay_process_meeting_task(
    url: str,
    selected_options: list[str],
    custom_prompt: str | None,
    channel_id: str,
    user_id: str,
) -> None:
    worker = threading.Thread(
        target=process_meeting_task,
        args=(url, selected_options, custom_prompt, channel_id, user_id),
        daemon=True,
        name="followthru-process-meeting",
    )
    worker.start()


if celery_app is not None:
    process_meeting_task = celery_app.task(name="process_meeting_task")(
        process_meeting_task
    )
else:
    process_meeting_task.delay = _delay_process_meeting_task


def _download_recording(url: str, temp_dir: Path) -> Path:
    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix or ".mp4"
    destination = temp_dir / f"meeting_recording{suffix}"

    headers = {"User-Agent": "FollowThru/1.0"}
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=DOWNLOAD_TIMEOUT_SECONDS,
            headers=headers,
        ) as client:
            with client.stream("GET", url) as response:
                response.raise_for_status()
                content_type = (response.headers.get("content-type") or "").lower()
                if "text/html" in content_type:
                    raise RuntimeError(
                        "The recording URL returned HTML instead of a media file. "
                        "Please use a direct downloadable Zoom recording link."
                    )

                with destination.open("wb") as file_handle:
                    for chunk in response.iter_bytes():
                        if chunk:
                            file_handle.write(chunk)
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Failed to download recording from URL: {exc}") from exc

    if not destination.exists() or destination.stat().st_size == 0:
        raise RuntimeError("Downloaded recording file is empty.")
    return destination


def _build_canvas_title(extraction: dict[str, object]) -> str:
    meeting_title = str(extraction.get("meeting_title") or "").strip()
    if not meeting_title:
        return "Action Canvas - Meeting Recording"
    return f"Action Canvas - {meeting_title[:80]}"


def _notify_processing_failure(channel_id: str, exc: Exception) -> None:
    try:
        slack_client.client.chat_postMessage(
            channel=channel_id,
            text=(
                ":warning: FollowThru could not finish processing the meeting "
                f"recording. {exc}"
            ),
        )
    except Exception:
        logger.exception("Failed to send Slack failure message for meeting task")
