from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from easy_video_fusion.args import BuildOptions
from easy_video_fusion.video_fusion import build_video_project


class VideoFusionTest(unittest.TestCase):
    def _make_options(self, **overrides) -> BuildOptions:
        base = {
            "images": [],
            "audios": [],
            "images_dir": None,
            "audios_dir": None,
            "out_path": "out.mp4",
            "padding_seconds": 3.0,
            "fps": 30,
            "resolution": (1920, 1080),
        }
        base.update(overrides)
        return BuildOptions(**base)

    def test_renders_one_segment_per_pair_and_concatenates_them(self) -> None:
        with tempfile.TemporaryDirectory(prefix="easy-video-fusion-test-") as temp_root:
            root = Path(temp_root)
            images_dir = root / "images"
            images_dir.mkdir()
            audios_dir = root / "audios"
            audios_dir.mkdir()

            image1 = root / "01.png"
            image2 = root / "02.png"
            audio1 = root / "01.mp3"
            audio2 = root / "02.mp3"
            for file_path, body in [
                (image1, b"img1"),
                (image2, b"img2"),
                (audio1, b"aud1"),
                (audio2, b"aud2"),
            ]:
                file_path.write_bytes(body)

            out_path = root / "out" / "video.mp4"
            probe_calls: list[str] = []
            ffmpeg_calls: list[list[str]] = []

            def probe(audio_path: str) -> float:
                probe_calls.append(audio_path)
                return {str(audio1): 1.5, str(audio2): 2.0}[audio_path]

            def run_ffmpeg(args: list[str]) -> None:
                ffmpeg_calls.append(args)

            result = build_video_project(
                self._make_options(
                    images=[str(image1), str(image2)],
                    audios=[str(audio1), str(audio2)],
                    out_path=str(out_path),
                ),
                probe_duration_fn=probe,
                run_ffmpeg_fn=run_ffmpeg,
            )

            self.assertEqual(result["output_path"], str(out_path))
            self.assertEqual(probe_calls, [str(audio1), str(audio2)])
            self.assertEqual(len(ffmpeg_calls), 3)
            self.assertIn("4.500", ffmpeg_calls[0])
            self.assertIn("5.000", ffmpeg_calls[1])
            self.assertTrue(any("concat.txt" in arg for arg in ffmpeg_calls[2]))

    def test_directory_mode_with_numeric_filename_ordering(self) -> None:
        with tempfile.TemporaryDirectory(prefix="easy-video-fusion-dirs-") as temp_root:
            root = Path(temp_root)
            images_dir = root / "images"
            audios_dir = root / "audios"
            images_dir.mkdir()
            audios_dir.mkdir()

            for file_name, body in [
                ("10.png", "img10"),
                ("2.png", "img2"),
                ("1.png", "img1"),
                ("10.mp3", "aud10"),
                ("2.mp3", "aud2"),
                ("1.mp3", "aud1"),
            ]:
                target_dir = images_dir if file_name.endswith(".png") else audios_dir
                (target_dir / file_name).write_text(body, encoding="utf-8")

            out_path = root / "out" / "video.mp4"
            probe_calls: list[str] = []

            def probe(audio_path: str) -> float:
                probe_calls.append(audio_path)
                return {str(audios_dir / "1.mp3"): 1.0, str(audios_dir / "2.mp3"): 2.0, str(audios_dir / "10.mp3"): 10.0}[audio_path]

            result = build_video_project(
                self._make_options(
                    images_dir=str(images_dir),
                    audios_dir=str(audios_dir),
                    out_path=str(out_path),
                ),
                probe_duration_fn=probe,
                run_ffmpeg_fn=lambda args: None,
            )

            self.assertEqual(
                [Path(slide.image_path).name for slide in result["slides"]],
                ["1.png", "2.png", "10.png"],
            )
            self.assertEqual(
                [Path(slide.audio_path).name for slide in result["slides"]],
                ["1.mp3", "2.mp3", "10.mp3"],
            )
            self.assertEqual(probe_calls, [str(audios_dir / "1.mp3"), str(audios_dir / "2.mp3"), str(audios_dir / "10.mp3")])


if __name__ == "__main__":
    unittest.main()
