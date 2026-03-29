from __future__ import annotations

import os
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except Exception as error:  # pragma: no cover - imported only in GUI environments
    tk = None  # type: ignore[assignment]
    filedialog = messagebox = ttk = None  # type: ignore[assignment]
    _tkinter_import_error = error
else:
    _tkinter_import_error = None

from .args import DEFAULT_FPS, DEFAULT_HEIGHT, DEFAULT_PADDING_SECONDS, DEFAULT_WIDTH, DEFAULT_INTRO_SECONDS, BuildOptions, parse_resolution_text
from .errors import VideoFusionError, to_error_message
from .video_fusion import build_video_project

FPS_OPTIONS = ("24", "30", "60")
RESOLUTION_OPTIONS = ("1280x720", "1920x1080", "2560x1440")


@dataclass(slots=True)
class FormValues:
    images_dir: str
    audios_dir: str
    out_path: str
    padding_seconds: str
    fps: str
    resolution: str
    intro_seconds: str


def build_options_from_values(values: FormValues) -> BuildOptions:
    images_dir = values.images_dir.strip()
    audios_dir = values.audios_dir.strip()
    out_path = values.out_path.strip()
    if not images_dir:
        raise VideoFusionError("请选择图片目录。")
    if not audios_dir:
        raise VideoFusionError("请选择音频目录。")
    if not out_path:
        raise VideoFusionError("请选择输出文件路径。")

    try:
        padding_seconds = float(values.padding_seconds.strip() or DEFAULT_PADDING_SECONDS)
    except ValueError as error:
        raise VideoFusionError("缓冲秒数格式不正确。") from error
    if padding_seconds <= 0:
        raise VideoFusionError("缓冲秒数必须大于 0。")

    try:
        fps = int(values.fps.strip() or DEFAULT_FPS)
    except ValueError as error:
        raise VideoFusionError("帧率格式不正确。") from error
    if fps <= 0:
        raise VideoFusionError("帧率必须大于 0。")

    resolution_text = values.resolution.strip() or f"{DEFAULT_WIDTH}x{DEFAULT_HEIGHT}"
    width, height = parse_resolution_text(resolution_text)

    try:
        intro_seconds = float(values.intro_seconds.strip() or DEFAULT_INTRO_SECONDS)
    except ValueError as error:
        raise VideoFusionError("开场秒数格式不正确。") from error
    if intro_seconds < 0:
        raise VideoFusionError("开场秒数不能为负数。")

    return BuildOptions(
        images=[],
        audios=[],
        images_dir=str(Path(images_dir).expanduser().resolve()),
        audios_dir=str(Path(audios_dir).expanduser().resolve()),
        out_path=str(Path(out_path).expanduser().resolve()),
        padding_seconds=padding_seconds,
        fps=fps,
        resolution=(width, height),
        intro_seconds=intro_seconds,
    )


def reveal_output_folder(folder: Path) -> None:
    if sys.platform.startswith("win"):
        os.startfile(str(folder))
        return
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(folder)])
        return
    subprocess.Popen(["xdg-open", str(folder)])


class VideoFusionDesktopApp:
    def __init__(self) -> None:
        if tk is None or ttk is None:
            raise RuntimeError("Tkinter is not available.") from _tkinter_import_error

        self.root = tk.Tk()
        self.root.title("easy-video-fusion")
        self.root.geometry("720x480")
        self.root.minsize(680, 440)

        self.images_dir = tk.StringVar()
        self.audios_dir = tk.StringVar()
        self.out_path = tk.StringVar()
        self.padding_seconds = tk.StringVar(value=str(int(DEFAULT_PADDING_SECONDS)))
        self.fps = tk.StringVar(value=str(DEFAULT_FPS))
        self.resolution = tk.StringVar(value=f"{DEFAULT_WIDTH}x{DEFAULT_HEIGHT}")
        self.intro_seconds = tk.StringVar(value=str(int(DEFAULT_INTRO_SECONDS)))
        self.output_dir: Path | None = None
        self.is_busy = False

        self._build_ui()

    def _build_ui(self) -> None:
        assert ttk is not None

        root = self.root
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        main = ttk.Frame(root, padding=14)
        main.grid(row=0, column=0, sticky="nsew")
        main.columnconfigure(1, weight=1)

        ttk.Label(main, text="easy-video-fusion", font=("Segoe UI", 16, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(main, text="图片 + TTS 音频 -> MP4", font=("Segoe UI", 10)).grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 10))

        self._path_row(main, 2, "图片目录", self.images_dir, lambda: self._choose_directory(self.images_dir))
        self._path_row(main, 3, "音频目录", self.audios_dir, lambda: self._choose_directory(self.audios_dir))
        self._path_row(main, 4, "输出文件", self.out_path, self._choose_output)

        ttk.Separator(main).grid(row=5, column=0, columnspan=3, sticky="ew", pady=10)

        ttk.Label(main, text="参数", font=("Segoe UI", 11, "bold")).grid(row=6, column=0, columnspan=3, sticky="w", pady=(0, 8))
        self._field_row(main, 7, "缓冲秒数", self.padding_seconds, "默认 1 秒")
        self._field_row(main, 8, "开场秒数", self.intro_seconds, "默认 5 秒")
        self._combo_row(main, 9, "帧率", self.fps, FPS_OPTIONS)
        self._combo_row(main, 10, "分辨率", self.resolution, RESOLUTION_OPTIONS)

        button_row = ttk.Frame(main)
        button_row.grid(row=11, column=0, columnspan=3, sticky="ew", pady=(14, 0))
        button_row.columnconfigure(2, weight=1)

        self.generate_button = ttk.Button(button_row, text="生成视频", command=self._on_generate)
        self.generate_button.grid(row=0, column=0, sticky="w")

        self.open_folder_button = ttk.Button(button_row, text="打开输出目录", command=self._open_output_folder, state="disabled")
        self.open_folder_button.grid(row=0, column=1, sticky="w", padx=(10, 0))

    def _path_row(self, parent: ttk.Frame, row: int, label: str, variable: tk.StringVar, chooser) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=5)
        entry = ttk.Entry(parent, textvariable=variable)
        entry.grid(row=row, column=1, sticky="ew", padx=(8, 8), pady=5)
        ttk.Button(parent, text="浏览", command=chooser).grid(row=row, column=2, sticky="e", pady=5)

    def _field_row(self, parent: ttk.Frame, row: int, label: str, variable: tk.StringVar, hint: str) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=5)
        entry = ttk.Entry(parent, textvariable=variable, width=18)
        entry.grid(row=row, column=1, sticky="w", padx=(8, 12), pady=5)
        ttk.Label(parent, text=hint).grid(row=row, column=2, sticky="w", pady=5)

    def _combo_row(self, parent: ttk.Frame, row: int, label: str, variable: tk.StringVar, options: tuple[str, ...]) -> None:
        assert ttk is not None
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=5)
        combo = ttk.Combobox(parent, textvariable=variable, values=options, state="readonly", width=16)
        combo.grid(row=row, column=1, sticky="w", padx=(8, 12), pady=5)
        if not variable.get():
            variable.set(options[0])
        ttk.Label(parent, text="请选择一个预设值").grid(row=row, column=2, sticky="w", pady=5)

    def _choose_directory(self, variable: tk.StringVar) -> None:
        assert filedialog is not None
        path = filedialog.askdirectory(parent=self.root, title="选择目录")
        if path:
            variable.set(path)

    def _choose_output(self) -> None:
        assert filedialog is not None
        path = filedialog.asksaveasfilename(
            parent=self.root,
            title="选择输出文件",
            defaultextension=".mp4",
            filetypes=[("MP4 视频", "*.mp4"), ("所有文件", "*.*")],
        )
        if path:
            self.out_path.set(path)

    def _set_busy(self, busy: bool) -> None:
        self.is_busy = busy
        self.generate_button.configure(state="disabled" if busy else "normal")
        self.open_folder_button.configure(state="disabled" if busy or self.output_dir is None else "normal")

    def _on_generate(self) -> None:
        if self.is_busy:
            return

        try:
            options = build_options_from_values(
                FormValues(
                    images_dir=self.images_dir.get(),
                    audios_dir=self.audios_dir.get(),
                    out_path=self.out_path.get(),
                    padding_seconds=self.padding_seconds.get(),
                    fps=self.fps.get(),
                    resolution=self.resolution.get(),
                    intro_seconds=self.intro_seconds.get(),
                )
            )
        except VideoFusionError as error:
            assert messagebox is not None
            messagebox.showerror("参数错误", str(error))
            return

        self.output_dir = Path(options.out_path).parent
        self._set_busy(True)
        thread = threading.Thread(target=self._run_generation, args=(options,), daemon=True)
        thread.start()

    def _run_generation(self, options: BuildOptions) -> None:
        try:
            result = build_video_project(options)
        except Exception as error:  # pragma: no cover - exercised through GUI actions
            self.root.after(0, lambda: self._on_generation_failed(error))
            return

        self.root.after(0, lambda: self._on_generation_succeeded(result["output_path"]))

    def _on_generation_failed(self, error: Exception) -> None:
        assert messagebox is not None
        self._set_busy(False)
        message = str(error) if isinstance(error, VideoFusionError) else to_error_message(error)
        messagebox.showerror("生成失败", message)

    def _on_generation_succeeded(self, output_path: str) -> None:
        assert messagebox is not None
        self._set_busy(False)
        self.open_folder_button.configure(state="normal")
        messagebox.showinfo("生成完成", f"视频已生成:\n{output_path}")

    def _open_output_folder(self) -> None:
        if self.output_dir and self.output_dir.exists():
            reveal_output_folder(self.output_dir)

    def run(self) -> None:
        self.root.mainloop()


def main(argv: list[str] | None = None) -> int:
    try:
        app = VideoFusionDesktopApp()
        app.run()
        return 0
    except RuntimeError as error:
        sys.stderr.write(f"easy-video-fusion-gui: {error}\n")
        return 1


if __name__ == "__main__":  # pragma: no cover - manual launch only
    raise SystemExit(main())
