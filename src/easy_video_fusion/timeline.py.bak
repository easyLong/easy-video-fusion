from __future__ import annotations

from dataclasses import dataclass

from .errors import VideoFusionError


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


def format_seconds(value: float) -> str:
    return f"{value:.3f}"


def validate_inputs(images: list[str], audios: list[str]) -> None:
    if not isinstance(images, list) or not images:
        raise VideoFusionError("At least one image is required.")
    if not isinstance(audios, list) or not audios:
        raise VideoFusionError("At least one audio file is required.")
    if len(images) != len(audios):
        raise VideoFusionError(
            f"Image and audio counts must match. Got {len(images)} image(s) and {len(audios)} audio file(s)."
        )


def pair_inputs(images: list[str], audios: list[str]) -> list[PairInput]:
    validate_inputs(images, audios)
    return [PairInput(index=i, image_path=images[i], audio_path=audios[i]) for i in range(len(images))]


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
