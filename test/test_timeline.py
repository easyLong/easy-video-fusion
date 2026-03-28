from __future__ import annotations

import unittest

from easy_video_fusion.timeline import TimedPairInput, build_timeline, format_seconds, pair_inputs


class TimelineTest(unittest.TestCase):
    def test_pair_inputs_keeps_input_order(self) -> None:
        pairs = pair_inputs(["a.png", "b.png"], ["a.mp3", "b.mp3"])
        self.assertEqual(pairs[0].index, 0)
        self.assertEqual(pairs[0].image_path, "a.png")
        self.assertEqual(pairs[0].audio_path, "a.mp3")
        self.assertEqual(pairs[1].index, 1)
        self.assertEqual(pairs[1].image_path, "b.png")
        self.assertEqual(pairs[1].audio_path, "b.mp3")

    def test_build_timeline_adds_padding_to_each_slide(self) -> None:
        timeline = build_timeline(
            [
                TimedPairInput(index=0, image_path="a.png", audio_path="a.mp3", audio_duration_seconds=1.5),
                TimedPairInput(index=1, image_path="b.png", audio_path="b.mp3", audio_duration_seconds=2.0),
            ],
            3,
        )

        self.assertEqual(timeline[0].start_seconds, 0)
        self.assertEqual(timeline[0].duration_seconds, 4.5)
        self.assertEqual(timeline[0].end_seconds, 4.5)
        self.assertEqual(timeline[1].start_seconds, 4.5)
        self.assertEqual(timeline[1].duration_seconds, 5.0)
        self.assertEqual(timeline[1].end_seconds, 9.5)

    def test_format_seconds_normalizes_ffmpeg_durations(self) -> None:
        self.assertEqual(format_seconds(4.5), "4.500")


if __name__ == "__main__":
    unittest.main()
