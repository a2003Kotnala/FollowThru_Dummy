from __future__ import annotations

import subprocess
from pathlib import Path


def extract_audio_chunks(
    input_source: str | Path,
    output_dir: str | Path,
) -> list[str]:
    input_path = Path(input_source).expanduser().resolve()
    chunk_dir = Path(output_dir).expanduser().resolve()
    chunk_dir.mkdir(parents=True, exist_ok=True)
    output_pattern = chunk_dir / "chunk_%03d.mp3"

    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-vn",
        "-ar",
        "16000",
        "-ac",
        "1",
        "-b:a",
        "64k",
        "-f",
        "segment",
        "-segment_time",
        "600",
        "-reset_timestamps",
        "1",
        str(output_pattern),
    ]

    try:
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "FFmpeg is not installed or is not available on PATH."
        ) from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise RuntimeError(
            f"FFmpeg failed while extracting audio chunks: {stderr or exc}"
        ) from exc

    chunk_paths = sorted(str(path) for path in chunk_dir.glob("chunk_*.mp3"))
    if not chunk_paths:
        raise RuntimeError("FFmpeg did not produce any audio chunks.")
    return chunk_paths
