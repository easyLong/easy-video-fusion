from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .errors import VideoFusionError

DEFAULT_PADDING_SECONDS = 1.0
DEFAULT_FPS = 30
DEFAULT_WIDTH = 1920
DEFAULT_HEIGHT = 1080


@dataclass(slots=True)
class BuildOptions:
    images: list[str]
    audios: list[str]
    images_dir: str | None
    audios_dir: str | None
    out_path: str
    padding_seconds: float
    fps: int
    resolution: tuple[int, int]


@dataclass(slots=True)
class ParsedCli:
    command: str
    options: BuildOptions | None = None


def format_usage() -> str:
    return "\n".join(
        [
            "easy-video-fusion",
            "",
            "Usage:",
            "  easy-video-fusion build --images-dir <dir> --audios-dir <dir> --out <file.mp4>",
            "  easy-video-fusion build --image <path> --audio <path> [--image ... --audio ...] --out <file.mp4>",
            "                       [--padding-seconds 1] [--fps 30] [--resolution 1920x1080]",
            "",
            "Examples:",
            "  easy-video-fusion build --images-dir images --audios-dir audios --out out.mp4",
            "  easy-video-fusion build --image 01.png --audio 01.mp3 --image 02.png --audio 02.mp3 --out out.mp4",
        ]
    )


def _parse_number(value: str, flag_name: str, *, integer: bool = False) -> float | int:
    try:
        parsed = int(value, 10) if integer else float(value)
    except ValueError as error:
        raise VideoFusionError(f"Invalid value for {flag_name}: {value}") from error
    if parsed <= 0:
        raise VideoFusionError(f"{flag_name} must be greater than 0.")
    return parsed


def parse_resolution_text(value: str) -> tuple[int, int]:
    text = value.strip()
    if "x" not in text.lower():
        raise VideoFusionError(f"Invalid value for --resolution: {value}. Use the form 1920x1080.")
    width_text, height_text = text.lower().split("x", 1)
    try:
        width = int(width_text, 10)
        height = int(height_text, 10)
    except ValueError as error:
        raise VideoFusionError(f"Invalid value for --resolution: {value}. Use the form 1920x1080.") from error
    if width <= 0 or height <= 0:
        raise VideoFusionError("--resolution must contain positive width and height.")
    return width, height


def _normalize_path_input(value: str) -> str:
    trimmed = value.strip()
    if not trimmed:
        raise VideoFusionError("Path values cannot be empty.")
    return str(Path(trimmed).expanduser().resolve())


def parse_cli_args(argv: Sequence[str]) -> ParsedCli:
    tokens = list(argv)
    if not tokens:
        return ParsedCli(command="help")

    if any(token in {"--help", "-h", "help"} for token in tokens):
        return ParsedCli(command="help")

    if tokens[0] == "build":
        tokens = tokens[1:]
    elif not tokens[0].startswith("-"):
        raise VideoFusionError(f"Unknown command: {tokens[0]}")
    else:
        tokens.insert(0, "build")

    images: list[str] = []
    audios: list[str] = []
    images_dir: str | None = None
    audios_dir: str | None = None
    out_path: str | None = None
    padding_seconds = DEFAULT_PADDING_SECONDS
    fps = DEFAULT_FPS
    resolution = (DEFAULT_WIDTH, DEFAULT_HEIGHT)

    i = 0
    while i < len(tokens):
        token = tokens[i]
        eq_index = token.find("=")
        flag_name = token[:eq_index] if eq_index >= 0 else token
        inline_value = token[eq_index + 1 :] if eq_index >= 0 else None

        def read_flag_value(flag_label: str) -> tuple[str, int]:
            if inline_value is not None:
                return inline_value, i
            next_index = i + 1
            if next_index >= len(tokens) or tokens[next_index].startswith("-"):
                raise VideoFusionError(f"Missing value for {flag_label}.")
            return tokens[next_index], next_index

        if flag_name == "build":
            i += 1
            continue
        if flag_name == "--image":
            value, next_index = read_flag_value("--image")
            images.append(_normalize_path_input(value))
            i = next_index + 1
            continue
        if flag_name == "--audio":
            value, next_index = read_flag_value("--audio")
            audios.append(_normalize_path_input(value))
            i = next_index + 1
            continue
        if flag_name == "--images-dir":
            value, next_index = read_flag_value("--images-dir")
            images_dir = _normalize_path_input(value)
            i = next_index + 1
            continue
        if flag_name == "--audios-dir":
            value, next_index = read_flag_value("--audios-dir")
            audios_dir = _normalize_path_input(value)
            i = next_index + 1
            continue
        if flag_name == "--out":
            value, next_index = read_flag_value("--out")
            out_path = _normalize_path_input(value)
            i = next_index + 1
            continue
        if flag_name == "--padding-seconds":
            value, next_index = read_flag_value("--padding-seconds")
            padding_seconds = float(_parse_number(value, "--padding-seconds"))
            i = next_index + 1
            continue
        if flag_name == "--fps":
            value, next_index = read_flag_value("--fps")
            fps = int(_parse_number(value, "--fps", integer=True))
            i = next_index + 1
            continue
        if flag_name == "--resolution":
            value, next_index = read_flag_value("--resolution")
            resolution = parse_resolution_text(value)
            i = next_index + 1
            continue
        raise VideoFusionError(f"Unknown option: {token}")

    if out_path is None:
        raise VideoFusionError("Missing required --out <file.mp4>.")

    using_directories = images_dir is not None or audios_dir is not None
    using_explicit_pairs = bool(images or audios)

    if using_directories and using_explicit_pairs:
        raise VideoFusionError("Use either directory inputs or explicit --image/--audio inputs, not both.")

    if using_directories:
        if images_dir is None or audios_dir is None:
            raise VideoFusionError("Both --images-dir and --audios-dir are required for directory mode.")
    else:
        if not images:
            raise VideoFusionError("At least one --image is required.")
        if not audios:
            raise VideoFusionError("At least one --audio is required.")
        if len(images) != len(audios):
            raise VideoFusionError(
                f"Image and audio counts must match. Got {len(images)} image(s) and {len(audios)} audio file(s)."
            )

    return ParsedCli(
        command="build",
        options=BuildOptions(
            images=images,
            audios=audios,
            images_dir=images_dir,
            audios_dir=audios_dir,
            out_path=out_path,
            padding_seconds=padding_seconds,
            fps=fps,
            resolution=resolution,
        ),
    )
