# easy-video-fusion

一个本地 Python CLI 工具，用于把图片和 TTS 音频合成为 MP4 视频。

工具会按顺序读取每一页素材，根据音频长度决定该页停留时间，默认再额外加 1 秒缓冲，最后调用 FFmpeg 生成成品视频。当前项目已完全切换为 Python 版本。

除了命令行模式，还提供一个更适合直接点选操作的桌面应用，适合不想手动敲命令时使用。

## 环境要求

- Python 3.10 或更高版本
- `pyproject.toml` 中声明的 Python 依赖

## 安装

使用可编辑模式安装项目：

```bash
python -m pip install -e .
```

安装完成后，会自动提供 `easy-video-fusion` 命令。

如果你想直接打开桌面应用，也会提供 `easy-video-fusion-gui` 命令。

## 运行

查看帮助：

```bash
python -m easy_video_fusion --help
```

使用目录批量合成：

```bash
python -m easy_video_fusion build ^
  --images-dir ./images ^
  --audios-dir ./audios ^
  --out ./out/video.mp4
```

使用显式成对参数合成：

```bash
python -m easy_video_fusion build ^
  --image ./slides/01.png --audio ./tts/01.mp3 ^
  --image ./slides/02.png --audio ./tts/02.mp3 ^
  --out ./out/video.mp4
```

如果你已经安装了包，也可以直接使用命令：

```bash
easy-video-fusion --help
```

打开桌面应用：

```bash
easy-video-fusion-gui
```

桌面应用会让你选择图片目录、音频目录和输出路径，然后一键生成视频。
其中帧率和分辨率使用下拉选择，图片/音频还是按数字编号自动配对。

## 批量目录规则

图片和音频分别放在两个目录中，文件名必须是数字编号，并且两边完全一致。

支持的命名示例：

- `1.png` + `1.mp3`
- `001.png` + `001.wav`
- `10.png` + `10.mp3`

规则说明：

- 只读取目录最外层文件，不会递归子目录。
- 按数字顺序排序，所以 `2.png` 会排在 `10.png` 前面。
- 同一个目录里，编号不能重复。
- 图片目录和音频目录必须包含完全相同的编号。

## 参数说明

- `--images-dir <dir>`: 图片输入目录
- `--audios-dir <dir>`: 音频输入目录
- `--image <path>`: 单张图片输入，可重复传入
- `--audio <path>`: 单段音频输入，可重复传入
- `--out <file.mp4>`: 输出视频文件
- `--padding-seconds <n>`: 每页在音频结束后额外停留的秒数，默认 `1`
- `--fps <n>`: 输出视频帧率，默认 `30`
- `--resolution <WxH>`: 输出分辨率，默认 `1920x1080`

桌面应用同样沿用这些默认值，界面里可以直接改。

## 桌面应用

启动桌面版：

```bash
easy-video-fusion-gui
```

开发环境下，也可以直接运行：

```bash
python -m easy_video_fusion.gui
```

Windows 下还提供了仓库根目录的启动器：

```text
easy-video-fusion-gui.vbs
```

双击这个文件就能直接打开桌面应用，它本质上封装了 `python -m easy_video_fusion.gui`，并且不会弹出黑色控制台窗口。

## Windows UI 操作

1. 双击 `easy-video-fusion-gui.vbs` 打开桌面应用。
2. 在“图片目录”里选择图片文件夹，在“音频目录”里选择音频文件夹。
3. 在“输出文件”里指定生成的 `MP4` 文件路径。
4. 根据需要选择帧率和分辨率，默认值分别是 `30` 和 `1920x1080`。
5. 点击“生成视频”开始合成。
6. 生成完成后，点击“打开输出目录”查看结果文件。

操作时请确保图片和音频文件名都是数字编号，并且两边一一对应，例如 `01.jpg` 对应 `01.mp3`。

## 输出结果

命令会在你指定的 `--out` 路径写出一个 MP4 文件。

渲染过程中生成的临时分段文件会在完成后自动清理。

## 常见错误

以下情况会直接报错并退出：

- Python 或所需的 Python 依赖未安装
- 图片和音频数量不一致
- 目录中的文件名不是数字编号
- 同一个目录中出现重复编号
- 输入文件或目录不存在
