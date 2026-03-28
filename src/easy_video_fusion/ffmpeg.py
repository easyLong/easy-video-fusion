from __future__ import annotations

from functools import lru_cache
import subprocess

from imageio_ffmpeg import get_ffmpeg_exe
from tinytag import TinyTag

from .errors import VideoFusionError, wrap_command_error


@lru_cache(maxsize=1)
def resolve_ffmpeg_executable() -> str:
    ffmpeg_path = get_ffmpeg_exe()
    if not ffmpeg_path:
        raise VideoFusionError("imageio-ffmpeg did not return an ffmpeg executable path.")
    return ffmpeg_path


def probe_audio_duration_seconds(audio_path: str) -> float:
    tag = TinyTag.get(audio_path)
    if tag is None or tag.duration is None:
        raise VideoFusionError(f"Unable to read duration from {audio_path}.")
    duration = float(tag.duration)
    if duration <= 0:
        raise VideoFusionError(f"Unable to read duration from {audio_path}.")
    return duration


def run_ffmpeg(args: list[str]) -> None:
    ffmpeg_path = resolve_ffmpeg_executable()
    try:
        subprocess.run([ffmpeg_path, *args], check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as error:
        details = error.stderr.strip() if error.stderr else error.stdout.strip()
        raise wrap_command_error("ffmpeg", error, details or None) from error
