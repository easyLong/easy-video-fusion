from __future__ import annotations

import unittest

from easy_video_fusion.args import DEFAULT_FPS, DEFAULT_HEIGHT, DEFAULT_INTRO_SECONDS, DEFAULT_PADDING_SECONDS, DEFAULT_WIDTH
from easy_video_fusion.gui import FPS_OPTIONS, RESOLUTION_OPTIONS, FormValues, build_options_from_values


class GuiConfigTest(unittest.TestCase):
    def test_build_options_from_values_uses_defaults(self) -> None:
        options = build_options_from_values(
            FormValues(
                images_dir="C:/Demo/picture",
                audios_dir="C:/Demo/mp3",
                out_path="C:/Demo/out/video.mp4",
                padding_seconds="",
                fps="",
                resolution="",
                intro_seconds="",
            )
        )

        self.assertEqual(options.padding_seconds, DEFAULT_PADDING_SECONDS)
        self.assertEqual(options.fps, DEFAULT_FPS)
        self.assertEqual(options.resolution, (DEFAULT_WIDTH, DEFAULT_HEIGHT))
        self.assertEqual(options.intro_seconds, DEFAULT_INTRO_SECONDS)

    def test_build_options_from_values_parses_custom_inputs(self) -> None:
        options = build_options_from_values(
            FormValues(
                images_dir="C:/Demo/picture",
                audios_dir="C:/Demo/mp3",
                out_path="C:/Demo/out/video.mp4",
                padding_seconds="2",
                fps="24",
                resolution="1280x720",
                intro_seconds="3",
            )
        )

        self.assertEqual(options.padding_seconds, 2.0)
        self.assertEqual(options.fps, 24)
        self.assertEqual(options.resolution, (1280, 720))
        self.assertEqual(options.intro_seconds, 3.0)

    def test_gui_preset_options_include_common_choices(self) -> None:
        self.assertIn("30", FPS_OPTIONS)
        self.assertIn("1920x1080", RESOLUTION_OPTIONS)


if __name__ == "__main__":
    unittest.main()
