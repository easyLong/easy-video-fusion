from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile

from .args import BuildOptions
from .errors import VideoFusionError
from .ffmpeg import probe_audio_duration_seconds, run_ffmpeg
from .timeline import PairInput, TimedPairInput, build_timeline, pair_inputs


@dataclass(slots=True)
class ScannedFile:
    base_name: str
    numeric_value: int
    full_path: str


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
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
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
    width, height = _normalize_resolution(options.resolution)
    out_path = Path(options.out_path)
    pairs = _resolve_inputs(options)

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
        for pair in pairs:
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

        segment_paths: list[str] = []

        # Add intro with first image (no audio)
        if timeline and options.intro_seconds > 0:
            intro_path = str(temp_dir / "segment-0000.mp4")
            segment_paths.append(intro_path)
            if progress_fn:
                progress_fn(f"生成{options.intro_seconds:.0f}秒开场...")
            first_slide = timeline[0]
            video_filter = ",".join(
                [
                    f"scale={width}:{height}:force_original_aspect_ratio=decrease",
                    f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black",
                    "setsar=1",
                    f"fps={options.fps}",
                    "format=yuv420p",
                ]
            )
            # ⭐ 添加静音音频轨道，避免 concat 后丢失声音
            run_ffmpeg_fn([
                "-y", "-loop", "1", "-i", first_slide.image_path,
                "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=mono",
                "-vf", video_filter,
                "-shortest",
                "-t", f"{options.intro_seconds:.1f}",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                "-c:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart",
                intro_path
            ])

        for i, slide in enumerate(timeline):
            if progress_fn:
                progress_fn(f"处理第 {i+1}/{len(timeline)} 张图片...")
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
            )

        if progress_fn:
            progress_fn("合并视频段落...")
        _concat_segments(
            run_ffmpeg_fn=run_ffmpeg_fn,
            segment_paths=segment_paths,
            output_path=str(out_path),
            temp_dir=temp_dir,
        )

        return {
            "output_path": str(out_path),
            "temp_dir": temp_dir_name,
            "slides": timeline,
            "segment_paths": segment_paths,
        }
