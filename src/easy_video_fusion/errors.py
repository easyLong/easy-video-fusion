from __future__ import annotations


class VideoFusionError(Exception):
    def __init__(self, message: str, *, code: str = "VIDEO_FUSION_ERROR", cause: Exception | None = None):
        super().__init__(message)
        self.code = code
        self.cause = cause


def to_error_message(error: object) -> str:
    if isinstance(error, Exception):
        return str(error) or error.__class__.__name__
    if isinstance(error, str):
        return error
    return repr(error)


def is_command_not_found_error(error: object) -> bool:
    return isinstance(error, FileNotFoundError)


def wrap_command_error(command_name: str, error: Exception, details: str | None = None) -> VideoFusionError:
    if isinstance(error, VideoFusionError):
        return error
    if is_command_not_found_error(error):
        return VideoFusionError(
            f"{command_name} was not found.",
            code="COMMAND_NOT_FOUND",
            cause=error,
        )
    suffix = f": {details}" if details else ""
    return VideoFusionError(f"{command_name} failed{suffix}", code="COMMAND_FAILED", cause=error)
