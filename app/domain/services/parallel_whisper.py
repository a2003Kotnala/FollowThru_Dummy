from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Sequence

import aiofiles
from openai import AsyncOpenAI

from app.config import settings

HINGLISH_TRANSCRIPTION_PROMPT = (
    "The following is a meeting transcript that contains a mix of English and "
    "Hindi (Hinglish)."
)
WHISPER_MODEL = "large-v3"
TRANSCRIPTION_TIMEOUT_SECONDS = 600.0
BOUNDARY_WORD_COUNT = 50


async def transcribe_audio_chunks(chunk_paths: Sequence[str | Path]) -> str:
    if not settings.openai_api_key:
        raise RuntimeError("LLM_API_KEY or OPENAI_API_KEY is not configured.")

    resolved_paths = [str(Path(chunk_path)) for chunk_path in chunk_paths]
    if not resolved_paths:
        return ""

    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.resolved_llm_base_url,
        timeout=max(settings.openai_timeout_seconds, TRANSCRIPTION_TIMEOUT_SECONDS),
    )
    try:
        base_prompts = [_build_prompt() for _ in resolved_paths]
        initial_pass = await _transcribe_chunks_once(client, resolved_paths, base_prompts)

        refined_prompts = []
        for index, _chunk_path in enumerate(resolved_paths):
            previous_tail = ""
            if index > 0:
                previous_tail = _last_words(initial_pass[index - 1], BOUNDARY_WORD_COUNT)
            refined_prompts.append(_build_prompt(previous_tail))

        final_pass = await _transcribe_chunks_once(client, resolved_paths, refined_prompts)
        return "\n\n".join(text.strip() for text in final_pass if text and text.strip())
    finally:
        await client.close()


async def _transcribe_chunks_once(
    client: AsyncOpenAI,
    chunk_paths: Sequence[str],
    prompts: Sequence[str],
) -> list[str]:
    tasks = [
        _transcribe_single_chunk(client=client, chunk_path=chunk_path, prompt=prompt)
        for chunk_path, prompt in zip(chunk_paths, prompts, strict=True)
    ]
    return await asyncio.gather(*tasks)


async def _transcribe_single_chunk(
    client: AsyncOpenAI,
    chunk_path: str,
    prompt: str,
) -> str:
    path = Path(chunk_path)
    try:
        async with aiofiles.open(path, "rb") as file_handle:
            payload = await file_handle.read()
        response = await client.audio.transcriptions.create(
            model=WHISPER_MODEL,
            file=(path.name, payload, "audio/mpeg"),
            prompt=prompt,
            response_format="text",
            temperature=0,
        )
        return _coerce_transcription_text(response)
    except Exception as exc:
        raise RuntimeError(
            f"Whisper transcription failed for {path.name}: {exc}"
        ) from exc


def _build_prompt(previous_tail: str | None = None) -> str:
    prompt = HINGLISH_TRANSCRIPTION_PROMPT
    if previous_tail:
        prompt += (
            "\nContinue naturally from the previous chunk without repeating "
            "or hallucinating partial words. Previous chunk trailing words: "
            f"{previous_tail}"
        )
    return prompt


def _last_words(text: str, count: int) -> str:
    words = text.split()
    if len(words) <= count:
        return " ".join(words)
    return " ".join(words[-count:])


def _coerce_transcription_text(response) -> str:
    if isinstance(response, str):
        return response
    return getattr(response, "text", "") or ""
