from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time


DEFAULT_PADDING_SECONDS = 1.0
DEFAULT_FPS = 30
DEFAULT_WIDTH = 1920
DEFAULT_HEIGHT = 1080
DEFAULT_INTRO_SECONDS = 5.0
DEFAULT_ENCODER = "auto"
ENCODER_CHOICES = ("auto", "cpu", "nvenc", "qsv", "amf")
AUDIO_SAMPLE_RATE = 24000
AUDIO_CHANNEL_LAYOUT = "stereo"
AUDIO_CHANNEL_COUNT = 2
AUTO_ENCODER_PRIORITY = ("h264_nvenc", "h264_qsv", "h264_amf")
ENCODER_TO_CODEC = {
    "cpu": "libx264",
    "nvenc": "h264_nvenc",
    "qsv": "h264_qsv",
    "amf": "h264_amf",
}
_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")


class VideoFusionError(Exception):
    pass


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
    intro_seconds: float = DEFAULT_INTRO_SECONDS
    encoder: str = DEFAULT_ENCODER
    fast_mode: bool = False


@dataclass(slots=True)
class PairInput:
    index: int
    image_path: str
    audio_path: str


@dataclass(slots=True)
class TimedPairInput(PairInput):
    audio_duration_seconds: float


@dataclass(slots=True)
class TimelineSlide:
    index: int
    image_path: str
    audio_path: str
    audio_duration_seconds: float
    duration_seconds: float
    start_seconds: float
    end_seconds: float


@dataclass(slots=True)
class ScannedFile:
    base_name: str
    numeric_value: int
    full_path: str


def format_usage() -> str:
    return "\n".join(
        [
            "easy-video-fusion",
            "",
            "Usage:",
            "  easy-video-fusion build --images-dir <dir> --audios-dir <dir> --out <file.mp4>",
            "  easy-video-fusion build --image <path> --audio <path> [--image ... --audio ...] --out <file.mp4>",
            "                       [--padding-seconds 1] [--fps 30] [--resolution 1920x1080] [--intro-seconds 5]",
            "                       [--encoder auto|cpu|nvenc|qsv|amf] [--fast]",
            "",
            "Examples:",
            "  easy-video-fusion build --images-dir images --audios-dir audios --out out.mp4",
            "  easy-video-fusion build --image 01.png --audio 01.mp3 --image 02.png --audio 02.mp3 --out out.mp4",
            "  easy-video-fusion build --images-dir images --audios-dir audios --out out.mp4 --intro-seconds 3",
            "  easy-video-fusion build --images-dir images --audios-dir audios --out out.mp4 --encoder nvenc --fast",
        ]
    )


def _emit_progress(progress_fn, message: str) -> None:
    if progress_fn:
        progress_fn(message)


def _normalize_path_input(value: str) -> str:
    trimmed = value.strip()
    if not trimmed:
        raise VideoFusionError("Path values cannot be empty.")
    return str(Path(trimmed).expanduser().resolve())


def _parse_number(value: str, flag_name: str, *, integer: bool = False) -> float | int:
    try:
        parsed = int(value, 10) if integer else float(value)
    except ValueError as error:
        raise VideoFusionError(f"Invalid value for {flag_name}: {value}") from error
    if parsed <= 0:
        raise VideoFusionError(f"{flag_name} must be greater than 0.")
    return parsed


def parse_resolution_text(value: str) -> tuple[int, int]:
    text = value.strip().lower()
    if "x" not in text:
        raise VideoFusionError(f"Invalid value for --resolution: {value}. Use the form 1920x1080.")
    width_text, height_text = text.split("x", 1)
    try:
        width = int(width_text, 10)
        height = int(height_text, 10)
    except ValueError as error:
        raise VideoFusionError(f"Invalid value for --resolution: {value}. Use the form 1920x1080.") from error
    if width <= 0 or height <= 0:
        raise VideoFusionError("--resolution must contain positive width and height.")
    return width, height


def parse_cli_args(argv: list[str]) -> BuildOptions | None:
    tokens = list(argv)
    if not tokens or any(token in {"--help", "-h", "help"} for token in tokens):
        return None

    if tokens[0] == "build":
        tokens = tokens[1:]
    elif not tokens[0].startswith("-"):
        raise VideoFusionError(f"Unknown command: {tokens[0]}")

    images: list[str] = []
    audios: list[str] = []
    images_dir: str | None = None
    audios_dir: str | None = None
    out_path: str | None = None
    padding_seconds = DEFAULT_PADDING_SECONDS
    fps = DEFAULT_FPS
    resolution = (DEFAULT_WIDTH, DEFAULT_HEIGHT)
    intro_seconds = DEFAULT_INTRO_SECONDS
    encoder = DEFAULT_ENCODER
    fast_mode = False

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
        if flag_name == "--intro-seconds":
            value, next_index = read_flag_value("--intro-seconds")
            try:
                intro_seconds = float(value)
            except ValueError as error:
                raise VideoFusionError(f"Invalid value for --intro-seconds: {value}") from error
            if intro_seconds < 0:
                raise VideoFusionError("--intro-seconds must be >= 0.")
            i = next_index + 1
            continue
        if flag_name == "--encoder":
            value, next_index = read_flag_value("--encoder")
            normalized = value.strip().lower()
            if normalized not in ENCODER_CHOICES:
                choices = ", ".join(ENCODER_CHOICES)
                raise VideoFusionError(f"Invalid value for --encoder: {value}. Choose one of: {choices}.")
            encoder = normalized
            i = next_index + 1
            continue
        if flag_name == "--fast":
            if inline_value is not None:
                raise VideoFusionError("--fast does not take a value.")
            fast_mode = True
            i += 1
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

    return BuildOptions(
        images=images,
        audios=audios,
        images_dir=images_dir,
        audios_dir=audios_dir,
        out_path=out_path,
        padding_seconds=padding_seconds,
        fps=fps,
        resolution=resolution,
        intro_seconds=intro_seconds,
        encoder=encoder,
        fast_mode=fast_mode,
    )


def _candidate_binary_paths(binary_name: str) -> list[str]:
    script_dir = Path(__file__).resolve().parent
    skill_root = script_dir.parent
    names = [binary_name]
    if sys.platform == "win32":
        names.insert(0, f"{binary_name}.exe")
    candidates: list[str] = []
    for name in names:
        candidates.append(str(skill_root / "bin" / name))
        candidates.append(name)
    return candidates


def resolve_binary(binary_name: str) -> str:
    for candidate in _candidate_binary_paths(binary_name):
        path = Path(candidate)
        if path.exists():
            return str(path)
        if path.name == candidate:
            return candidate
    return binary_name


def _run_command(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    kwargs: dict[str, object] = {"check": check, "capture_output": True, "text": True}
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        kwargs["startupinfo"] = startupinfo
    try:
        return subprocess.run(command, **kwargs)
    except FileNotFoundError as error:
        raise VideoFusionError(f"Command not found: {command[0]}") from error
    except subprocess.CalledProcessError as error:
        details = (error.stderr or error.stdout or "").strip()
        suffix = f": {details}" if details else ""
        raise VideoFusionError(f"{command[0]} failed{suffix}") from error


def probe_audio_duration_seconds(audio_path: str) -> float:
    ffmpeg = resolve_binary("ffmpeg")
    result = _run_command([ffmpeg, "-hide_banner", "-i", audio_path], check=False)
    match = _DURATION_RE.search(result.stderr or "")
    if not match:
        raise VideoFusionError(f"Unable to read duration from {audio_path}.")
    hours = int(match.group(1))
    minutes = int(match.group(2))
    seconds = float(match.group(3))
    duration = hours * 3600 + minutes * 60 + seconds
    if duration <= 0:
        raise VideoFusionError(f"Unable to read duration from {audio_path}.")
    return duration


def run_ffmpeg(args: list[str]) -> None:
    _run_command([resolve_binary("ffmpeg"), *args], check=True)


def list_available_video_encoders() -> set[str]:
    result = _run_command([resolve_binary("ffmpeg"), "-hide_banner", "-encoders"], check=True)
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


def _resolve_video_codec(encoder: str) -> str:
    normalized = (encoder or "auto").strip().lower()
    if normalized == "auto":
        available = list_available_video_encoders()
        for codec in AUTO_ENCODER_PRIORITY:
            if codec in available:
                return codec
        return "libx264"

    if normalized not in ENCODER_TO_CODEC:
        raise VideoFusionError(f"Unsupported encoder value: {encoder}")

    codec = ENCODER_TO_CODEC[normalized]
    if codec == "libx264":
        return codec

    available = list_available_video_encoders()
    if codec not in available:
        available_hw = [name for name in AUTO_ENCODER_PRIORITY if name in available]
        hint = f" Available hardware encoders: {', '.join(available_hw)}." if available_hw else " No hardware encoder is available."
        raise VideoFusionError(f"Requested encoder '{normalized}' is not available in current ffmpeg build.{hint}")
    return codec


def _build_video_codec_args(codec: str, *, fast_mode: bool) -> list[str]:
    if codec == "libx264":
        preset = "ultrafast" if fast_mode else "veryfast"
        crf = "23" if fast_mode else "18"
        return ["-c:v", codec, "-preset", preset, "-crf", crf]
    if codec == "h264_nvenc":
        preset = "p3" if fast_mode else "p5"
        cq = "24" if fast_mode else "20"
        return ["-c:v", codec, "-preset", preset, "-rc", "vbr", "-cq", cq, "-b:v", "0"]
    if codec == "h264_qsv":
        quality = "28" if fast_mode else "22"
        return ["-c:v", codec, "-global_quality", quality]
    if codec == "h264_amf":
        quality = "speed" if fast_mode else "quality"
        return ["-c:v", codec, "-quality", quality]
    return ["-c:v", codec]


def _to_concat_entry(file_path: str) -> str:
    escaped = file_path.replace("\\", "/").replace("'", "\\'")
    return f"file '{escaped}'"


def _parse_numeric_stem(file_name: str, kind: str, container_path: Path) -> ScannedFile:
    base_name = Path(file_name).stem
    if not base_name.isdigit():
        suffix = Path(file_name).suffix
        raise VideoFusionError(
            f"All {kind} files in {container_path} must use numeric names like 001{suffix}. Found {file_name}."
        )
    return ScannedFile(base_name=base_name, numeric_value=int(base_name, 10), full_path=str(container_path / file_name))


def _scan_directory_inputs(container_path: Path, kind: str) -> list[ScannedFile]:
    if not container_path.exists():
        raise VideoFusionError(f"Directory not found: {container_path}")
    if not container_path.is_dir():
        raise VideoFusionError(f"Expected a directory but found a different path: {container_path}")

    files: list[ScannedFile] = []
    seen_names: set[str] = set()
    seen_numeric_values: set[int] = set()
    for entry in container_path.iterdir():
        if not entry.is_file():
            continue
        parsed = _parse_numeric_stem(entry.name, kind, container_path)
        if parsed.base_name in seen_names:
            raise VideoFusionError(
                f"Duplicate {kind} name {parsed.base_name} in {container_path}. Each numeric name must be unique."
            )
        if parsed.numeric_value in seen_numeric_values:
            raise VideoFusionError(
                f"Duplicate {kind} order {parsed.base_name} in {container_path}. Use one unique numeric filename per slide."
            )
        seen_names.add(parsed.base_name)
        seen_numeric_values.add(parsed.numeric_value)
        files.append(parsed)

    if not files:
        raise VideoFusionError(f"No {kind} files found in {container_path}.")

    files.sort(key=lambda item: (item.numeric_value, item.base_name))
    return files


def pair_inputs(images: list[str], audios: list[str]) -> list[PairInput]:
    return [PairInput(index=i, image_path=images[i], audio_path=audios[i]) for i in range(len(images))]


def _resolve_inputs(options: BuildOptions) -> list[PairInput]:
    if options.images_dir or options.audios_dir:
        if not options.images_dir or not options.audios_dir:
            raise VideoFusionError("Both --images-dir and --audios-dir are required for directory mode.")

        image_files = _scan_directory_inputs(Path(options.images_dir), "image")
        audio_files = _scan_directory_inputs(Path(options.audios_dir), "audio")

        if len(image_files) != len(audio_files):
            raise VideoFusionError(
                f"Image and audio counts must match. Got {len(image_files)} image file(s) and {len(audio_files)} audio file(s)."
            )

        audio_by_name = {file.base_name: file.full_path for file in audio_files}
        pairs: list[PairInput] = []
        for image_file in image_files:
            audio_path = audio_by_name.get(image_file.base_name)
            if audio_path is None:
                raise VideoFusionError(
                    f"Missing audio file for numeric name {image_file.base_name}. Directory names must match exactly."
                )
            pairs.append(PairInput(index=len(pairs), image_path=image_file.full_path, audio_path=audio_path))

        image_names = {file.base_name for file in image_files}
        for audio_file in audio_files:
            if audio_file.base_name not in image_names:
                raise VideoFusionError(
                    f"Missing image file for numeric name {audio_file.base_name}. Directory names must match exactly."
                )

        return pairs

    return pair_inputs(options.images, options.audios)


def _ensure_path_exists(target_path: Path, *, expected_kind: str = "file") -> None:
    if not target_path.exists():
        raise VideoFusionError(f"{expected_kind.capitalize()} not found: {target_path}")
    if expected_kind == "file" and not target_path.is_file():
        raise VideoFusionError(f"Expected a file but found a different path: {target_path}")
    if expected_kind == "directory" and not target_path.is_dir():
        raise VideoFusionError(f"Expected a directory but found a different path: {target_path}")


def build_timeline(pairs: list[TimedPairInput], padding_seconds: float) -> list[TimelineSlide]:
    current_start = 0.0
    timeline: list[TimelineSlide] = []
    for pair in pairs:
        duration_seconds = pair.audio_duration_seconds + padding_seconds
        start_seconds = current_start
        end_seconds = start_seconds + duration_seconds
        current_start = end_seconds
        timeline.append(
            TimelineSlide(
                index=pair.index,
                image_path=pair.image_path,
                audio_path=pair.audio_path,
                audio_duration_seconds=pair.audio_duration_seconds,
                duration_seconds=duration_seconds,
                start_seconds=start_seconds,
                end_seconds=end_seconds,
            )
        )
    return timeline


def _render_segment(
    *,
    image_path: str,
    audio_path: str,
    output_path: str,
    duration_seconds: float,
    padding_seconds: float,
    fps: int,
    width: int,
    height: int,
    video_codec_args: list[str],
) -> None:
    video_filter = ",".join(
        [
            f"scale={width}:{height}:force_original_aspect_ratio=decrease",
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black",
            "setsar=1",
            f"fps={fps}",
            "format=yuv420p",
        ]
    )
    run_ffmpeg(
        [
            "-y",
            "-loop",
            "1",
            "-i",
            image_path,
            "-i",
            audio_path,
            "-vf",
            video_filter,
            "-filter_complex",
            f"[1:a]apad=pad_dur={padding_seconds:.3f}[aout]",
            "-map",
            "0:v:0",
            "-map",
            "[aout]",
            "-t",
            f"{duration_seconds:.3f}",
            *video_codec_args,
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            str(AUDIO_SAMPLE_RATE),
            "-ac",
            str(AUDIO_CHANNEL_COUNT),
            "-movflags",
            "+faststart",
            output_path,
        ]
    )


def _render_intro_segment(
    *,
    image_path: str,
    output_path: str,
    intro_seconds: float,
    fps: int,
    width: int,
    height: int,
    video_codec_args: list[str],
) -> None:
    video_filter = ",".join(
        [
            f"scale={width}:{height}:force_original_aspect_ratio=decrease",
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black",
            "setsar=1",
            f"fps={fps}",
            "format=yuv420p",
        ]
    )
    run_ffmpeg(
        [
            "-y",
            "-loop",
            "1",
            "-i",
            image_path,
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=r={AUDIO_SAMPLE_RATE}:cl={AUDIO_CHANNEL_LAYOUT}",
            "-vf",
            video_filter,
            "-shortest",
            "-t",
            f"{intro_seconds:.3f}",
            *video_codec_args,
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            str(AUDIO_SAMPLE_RATE),
            "-ac",
            str(AUDIO_CHANNEL_COUNT),
            "-movflags",
            "+faststart",
            output_path,
        ]
    )


def _concat_segments(*, segment_paths: list[str], output_path: str, temp_dir: Path) -> None:
    list_path = temp_dir / "concat.txt"
    list_path.write_text("\n".join(_to_concat_entry(path) for path in segment_paths) + "\n", encoding="utf-8")
    run_ffmpeg(
        [
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            output_path,
        ]
    )


def build_video_project(options: BuildOptions, *, progress_fn=None) -> dict[str, object]:
    _emit_progress(progress_fn, "Resolving encoder and input files...")
    width, height = options.resolution
    if width <= 0 or height <= 0:
        raise VideoFusionError("Resolution must contain positive integer width and height.")

    video_codec = _resolve_video_codec(options.encoder)
    video_codec_args = _build_video_codec_args(video_codec, fast_mode=options.fast_mode)
    _emit_progress(progress_fn, f"Using video codec: {video_codec} (fast mode: {'on' if options.fast_mode else 'off'})")

    out_path = Path(options.out_path)
    pairs = _resolve_inputs(options)
    _emit_progress(progress_fn, f"Resolved {len(pairs)} image/audio pair(s).")

    if not options.images_dir:
        for file_path in [*options.images, *options.audios]:
            _ensure_path_exists(Path(file_path), expected_kind="file")
    else:
        _ensure_path_exists(Path(options.images_dir), expected_kind="directory")
        _ensure_path_exists(Path(options.audios_dir or ""), expected_kind="directory")

    out_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="easy-video-fusion-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        timed_pairs: list[TimedPairInput] = []
        for i, pair in enumerate(pairs):
            _emit_progress(progress_fn, f"Probing audio duration {i + 1}/{len(pairs)}...")
            duration = probe_audio_duration_seconds(pair.audio_path)
            timed_pairs.append(
                TimedPairInput(
                    index=pair.index,
                    image_path=pair.image_path,
                    audio_path=pair.audio_path,
                    audio_duration_seconds=duration,
                )
            )

        timeline = build_timeline(timed_pairs, options.padding_seconds)
        _emit_progress(progress_fn, f"Timeline ready with {len(timeline)} slide segment(s).")
        segment_paths: list[str] = []

        if timeline and options.intro_seconds > 0:
            _emit_progress(progress_fn, f"Rendering intro segment ({options.intro_seconds:.1f}s)...")
            intro_path = str(temp_dir / "segment-0000.mp4")
            segment_paths.append(intro_path)
            _render_intro_segment(
                image_path=timeline[0].image_path,
                output_path=intro_path,
                intro_seconds=options.intro_seconds,
                fps=options.fps,
                width=width,
                height=height,
                video_codec_args=video_codec_args,
            )

        for i, slide in enumerate(timeline):
            _emit_progress(progress_fn, f"Rendering slide segment {i + 1}/{len(timeline)}...")
            segment_path = str(temp_dir / f"segment-{slide.index + 1:04d}.mp4")
            segment_paths.append(segment_path)
            _render_segment(
                image_path=slide.image_path,
                audio_path=slide.audio_path,
                output_path=segment_path,
                duration_seconds=slide.duration_seconds,
                padding_seconds=options.padding_seconds,
                fps=options.fps,
                width=width,
                height=height,
                video_codec_args=video_codec_args,
            )

        _emit_progress(progress_fn, "Concatenating all segments...")
        _concat_segments(segment_paths=segment_paths, output_path=str(out_path), temp_dir=temp_dir)
        _emit_progress(progress_fn, "Done.")

        return {
            "output_path": str(out_path),
            "temp_dir": temp_dir_name,
            "slides": timeline,
            "segment_paths": segment_paths,
            "video_codec": video_codec,
            "fast_mode": options.fast_mode,
        }


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    try:
        parsed = parse_cli_args(args)
        if parsed is None:
            sys.stdout.write(f"{format_usage()}\n")
            return 0

        started_at = time.monotonic()

        def progress(message: str) -> None:
            elapsed = time.monotonic() - started_at
            sys.stderr.write(f"[easy-video-fusion +{elapsed:7.2f}s] {message}\n")
            sys.stderr.flush()

        result = build_video_project(parsed, progress_fn=progress)
        codec = result.get("video_codec", "unknown")
        sys.stdout.write(f"Wrote {result['output_path']} (video codec: {codec})\n")
        return 0
    except VideoFusionError as error:
        sys.stderr.write(f"easy-video-fusion: {error}\n")
        return 1
    except Exception as error:
        sys.stderr.write(f"easy-video-fusion: Unexpected error: {error}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
