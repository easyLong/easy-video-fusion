---
name: easy-video-fusion
description: Standalone skill for building MP4 videos from numbered image and audio pairs. Use when Codex needs to generate a slideshow-style video from local images plus TTS or narration audio, especially when the user wants a portable, copyable skill directory with bundled executable scripts instead of relying on project source code.
---

# Easy Video Fusion

Use the bundled standalone scripts in this skill directory. Do not depend on any repository source files outside `skills/easy-video-fusion/`.

## What This Skill Provides

- A standalone CLI implementation under `scripts/`
- Directory mode using numbered files like `001.png` plus `001.mp3`
- Explicit pair mode using repeated `--image` and `--audio`
- Optional intro hold using the first image before audio begins
- Encoder selection with auto hardware preference (`nvenc` / `qsv` / `amf` / `cpu`)
- Fast mode that uses speed-oriented encoder parameters
- Real-time progress logs for probing, segment rendering, and concat stages
- FFmpeg concat-based rendering with a silent audio track for the intro segment

## Requirements

- Python 3.10 or newer
- `ffmpeg` available on `PATH` (or at `bin/ffmpeg(.exe)` inside the copied skill folder)

## Run It

Use the Python entry point from inside the copied skill folder:

```powershell
python scripts/easy_video_fusion.py --help
python scripts/easy_video_fusion.py build --images-dir ./images --audios-dir ./audios --out ./out/video.mp4
python scripts/easy_video_fusion.py build --images-dir ./images --audios-dir ./audios --out ./out/video.mp4 --encoder nvenc --fast
```

Explicit pair mode:

```powershell
python scripts/easy_video_fusion.py build --image ./slides/01.png --audio ./tts/01.mp3 --image ./slides/02.png --audio ./tts/02.mp3 --out ./out/video.mp4
```

Supported flags:

- `--images-dir <dir>`
- `--audios-dir <dir>`
- `--image <path>` repeated
- `--audio <path>` repeated
- `--out <file.mp4>`
- `--padding-seconds <n>` default `1`
- `--fps <n>` default `30`
- `--resolution <WxH>` default `1920x1080`
- `--intro-seconds <n>` default `5`
- `--encoder <name>` default `auto`, choices: `auto`, `cpu`, `nvenc`, `qsv`, `amf`
- `--fast` optional speed mode switch

## Behavior Notes

- Numbered directory mode only reads the top level of each directory.
- Image and audio stems must be numeric and must match exactly.
- Slide duration is `audio duration + padding`.
- Intro duration is a separate silent segment that shows the first image before the first audio starts.
- Audio duration probing uses `ffmpeg -i` duration parsing to avoid incorrect WAV header estimates.
- The script first looks for `bin/ffmpeg(.exe)` next to the skill, then falls back to `PATH`.
- If the user asks to change intro or timing behavior, edit the standalone script in this skill instead of external project code.
