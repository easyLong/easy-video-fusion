from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile

from .args import BuildOptions
from .errors import VideoFusionError
from .ffmpeg import list_available_video_encoders, probe_audio_duration_seconds, run_ffmpeg
from .timeline import PairInput, TimedPairInput, build_timeline, pair_inputs

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


@dataclass(slots=True)
class ScannedFile:
    base_name: str
    numeric_value: int
    full_path: str


def _emit_progress(progress_fn, message: str) -> None:
    if progress_fn:
        progress_fn(message)


def _normalize_resolution(resolution: tuple[int, int] | None) -> tuple[int, int]:
    if resolution is None:
        raise VideoFusionError("Resolution must contain positive integer width and height.")
    width, height = resolution
    if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
        raise VideoFusionError("Resolution must contain positive integer width and height.")
    return width, height


def _to_concat_entry(file_path: str) -> str:
    escaped = file_path.replace("\\", "/").replace("'", "\\'")
    return f"file '{escaped}'"


def _parse_numeric_stem(file_name: str, kind: str, container_path: Path) -> ScannedFile:
    base_name = Path(file_name).stem
    if not base_name.isdigit():
        raise VideoFusionError(
            f"All {kind} files in {container_path} must use numeric names like 001{Path(file_name).suffix}. Found {file_name}."
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


def _render_segment(
    *,
    run_ffmpeg_fn,
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
    run_ffmpeg_fn(
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
    run_ffmpeg_fn,
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
    run_ffmpeg_fn(
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


def _concat_segments(*, run_ffmpeg_fn, segment_paths: list[str], output_path: str, temp_dir: Path) -> None:
    list_path = temp_dir / "concat.txt"
    list_body = "\n".join(_to_concat_entry(segment_path) for segment_path in segment_paths) + "\n"
    list_path.write_text(list_body, encoding="utf-8")
    run_ffmpeg_fn(
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


def build_video_project(
    options: BuildOptions,
    *,
    probe_duration_fn=probe_audio_duration_seconds,
    run_ffmpeg_fn=run_ffmpeg,
    progress_fn=None,
) -> dict[str, object]:
    _emit_progress(progress_fn, "Resolving encoder and input files...")
    width, height = _normalize_resolution(options.resolution)
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
        probed_pairs: list[TimedPairInput] = []
        for i, pair in enumerate(pairs):
            _emit_progress(progress_fn, f"Probing audio duration {i + 1}/{len(pairs)}...")
            audio_duration_seconds = probe_duration_fn(pair.audio_path)
            if audio_duration_seconds <= 0:
                raise VideoFusionError(f"Unable to read duration from {pair.audio_path}.")
            probed_pairs.append(
                TimedPairInput(
                    index=pair.index,
                    image_path=pair.image_path,
                    audio_path=pair.audio_path,
                    audio_duration_seconds=audio_duration_seconds,
                )
            )

        timeline = build_timeline(probed_pairs, options.padding_seconds)
        _emit_progress(progress_fn, f"Timeline ready with {len(timeline)} slide segment(s).")

        segment_paths: list[str] = []

        if timeline and options.intro_seconds > 0:
            _emit_progress(progress_fn, f"Rendering intro segment ({options.intro_seconds:.1f}s)...")
            intro_path = str(temp_dir / "segment-0000.mp4")
            segment_paths.append(intro_path)
            _render_intro_segment(
                run_ffmpeg_fn=run_ffmpeg_fn,
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
                run_ffmpeg_fn=run_ffmpeg_fn,
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
        _concat_segments(
            run_ffmpeg_fn=run_ffmpeg_fn,
            segment_paths=segment_paths,
            output_path=str(out_path),
            temp_dir=temp_dir,
        )
        _emit_progress(progress_fn, "Done.")

        return {
            "output_path": str(out_path),
            "temp_dir": temp_dir_name,
            "slides": timeline,
            "segment_paths": segment_paths,
            "video_codec": video_codec,
            "fast_mode": options.fast_mode,
        }
