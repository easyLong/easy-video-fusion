from __future__ import annotations

from pathlib import Path
import unittest

from easy_video_fusion.args import parse_cli_args


class ParseArgsTest(unittest.TestCase):
    def test_pairs_repeated_image_and_audio_flags(self) -> None:
        parsed = parse_cli_args(
            [
                "build",
                "--image",
                "01.png",
                "--audio",
                "01.mp3",
                "--image",
                "02.png",
                "--audio",
                "02.mp3",
                "--out",
                "out.mp4",
            ]
        )

        self.assertEqual(parsed.command, "build")
        self.assertEqual(parsed.options.images, [str(Path("01.png").resolve()), str(Path("02.png").resolve())])
        self.assertEqual(parsed.options.audios, [str(Path("01.mp3").resolve()), str(Path("02.mp3").resolve())])
        self.assertEqual(parsed.options.out_path, str(Path("out.mp4").resolve()))

    def test_reads_defaults_and_numeric_options(self) -> None:
        parsed = parse_cli_args(
            [
                "--image",
                "a.png",
                "--audio",
                "a.mp3",
                "--out",
                "out.mp4",
                "--padding-seconds",
                "4",
                "--fps",
                "24",
                "--resolution",
                "1280x720",
            ]
        )

        self.assertEqual(parsed.command, "build")
        self.assertEqual(parsed.options.padding_seconds, 4.0)
        self.assertEqual(parsed.options.fps, 24)
        self.assertEqual(parsed.options.resolution, (1280, 720))
        self.assertEqual(parsed.options.encoder, "auto")
        self.assertEqual(parsed.options.fast_mode, False)

    def test_accepts_directory_mode(self) -> None:
        parsed = parse_cli_args(
            [
                "build",
                "--images-dir",
                "images",
                "--audios-dir",
                "audios",
                "--out",
                "out.mp4",
            ]
        )

        self.assertEqual(parsed.command, "build")
        self.assertEqual(parsed.options.images_dir, str(Path("images").resolve()))
        self.assertEqual(parsed.options.audios_dir, str(Path("audios").resolve()))
        self.assertEqual(parsed.options.images, [])
        self.assertEqual(parsed.options.audios, [])

    def test_rejects_mismatched_media_counts(self) -> None:
        with self.assertRaisesRegex(Exception, "counts must match"):
            parse_cli_args(["--image", "a.png", "--audio", "a.mp3", "--audio", "b.mp3", "--out", "x"])

    def test_accepts_encoder_and_fast_mode(self) -> None:
        parsed = parse_cli_args(
            [
                "--image",
                "a.png",
                "--audio",
                "a.mp3",
                "--out",
                "out.mp4",
                "--encoder",
                "nvenc",
                "--fast",
            ]
        )

        self.assertEqual(parsed.options.encoder, "nvenc")
        self.assertEqual(parsed.options.fast_mode, True)

    def test_rejects_invalid_encoder(self) -> None:
        with self.assertRaisesRegex(Exception, "Invalid value for --encoder"):
            parse_cli_args(["--image", "a.png", "--audio", "a.mp3", "--out", "out.mp4", "--encoder", "bad"])


if __name__ == "__main__":
    unittest.main()
