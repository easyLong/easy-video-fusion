from __future__ import annotations

from functools import lru_cache
import re
import subprocess
import sys

from imageio_ffmpeg import get_ffmpeg_exe
from tinytag import TinyTag

from .errors import VideoFusionError, wrap_command_error


@lru_cache(maxsize=1)
def resolve_ffmpeg_executable() -> str:
    ffmpeg_path = get_ffmpeg_exe()
    if not ffmpeg_path:
        raise VideoFusionError("imageio-ffmpeg did not return an ffmpeg executable path.")
    return ffmpeg_path


def _ffmpeg_subprocess_kwargs() -> dict[str, object]:
    kwargs: dict[str, object] = {"check": True, "capture_output": True, "text": True}
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        kwargs["startupinfo"] = startupinfo
    return kwargs


_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")


def _probe_duration_with_ffmpeg(audio_path: str) -> float:
    ffmpeg_path = resolve_ffmpeg_executable()
    try:
        kwargs = _ffmpeg_subprocess_kwargs()
        kwargs["check"] = False
        result = subprocess.run([ffmpeg_path, "-hide_banner", "-i", audio_path], **kwargs)
    except FileNotFoundError as error:
        raise VideoFusionError("ffmpeg was not found.") from error

    stderr = result.stderr or ""
    match = _DURATION_RE.search(stderr)
    if not match:
        raise VideoFusionError(f"Unable to read duration from {audio_path}.")
    hours = int(match.group(1))
    minutes = int(match.group(2))
    seconds = float(match.group(3))
    duration = hours * 3600 + minutes * 60 + seconds
    if duration <= 0:
        raise VideoFusionError(f"Unable to read duration from {audio_path}.")
    return duration


def probe_audio_duration_seconds(audio_path: str) -> float:
    # Prefer ffmpeg parsing because some WAV headers can make TinyTag report wildly inflated durations.
    try:
        return _probe_duration_with_ffmpeg(audio_path)
    except VideoFusionError:
        tag = TinyTag.get(audio_path)
        if tag is None or tag.duration is None:
            raise VideoFusionError(f"Unable to read duration from {audio_path}.")
        duration = float(tag.duration)
        if duration <= 0:
            raise VideoFusionError(f"Unable to read duration from {audio_path}.")
        return duration


@lru_cache(maxsize=1)
def list_available_video_encoders() -> set[str]:
    ffmpeg_path = resolve_ffmpeg_executable()
    try:
        result = subprocess.run([ffmpeg_path, "-hide_banner", "-encoders"], **_ffmpeg_subprocess_kwargs())
    except subprocess.CalledProcessError as error:
        details = error.stderr.strip() if error.stderr else error.stdout.strip()
        raise wrap_command_error("ffmpeg", error, details or None) from error

    encoders: set[str] = set()
    for line in result.stdout.splitlines():
        row = line.strip()
        if not row or row.startswith("Encoders:") or row.startswith("--"):
            continue
        parts = row.split()
        if len(parts) < 2:
            continue
        flags, name = parts[0], parts[1]
        if flags.startswith("V"):
            encoders.add(name)
    return encoders


def run_ffmpeg(args: list[str]) -> None:
    ffmpeg_path = resolve_ffmpeg_executable()
    try:
        subprocess.run([ffmpeg_path, *args], **_ffmpeg_subprocess_kwargs())
    except subprocess.CalledProcessError as error:
        details = error.stderr.strip() if error.stderr else error.stdout.strip()
        raise wrap_command_error("ffmpeg", error, details or None) from error
