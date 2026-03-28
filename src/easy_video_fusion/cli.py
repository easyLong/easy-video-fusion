from __future__ import annotations

import sys

from .args import format_usage, parse_cli_args
from .errors import VideoFusionError, to_error_message
from .video_fusion import build_video_project


def run_cli(argv: list[str] | None = None) -> dict[str, object]:
    parsed = parse_cli_args(sys.argv[1:] if argv is None else argv)
    if parsed.command == "help":
        return {"exit_code": 0, "stdout": f"{format_usage()}\n"}

    result = build_video_project(parsed.options)
    return {"exit_code": 0, "stdout": f"Wrote {result['output_path']}\n"}


def main(argv: list[str] | None = None) -> int:
    try:
        result = run_cli(argv)
        stdout = result.get("stdout")
        if stdout:
            sys.stdout.write(str(stdout))
        return int(result.get("exit_code", 0))
    except VideoFusionError as error:
        sys.stderr.write(f"easy-video-fusion: {error}\n")
        return 1
    except Exception as error:
        sys.stderr.write(f"easy-video-fusion: Unexpected error: {to_error_message(error)}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
