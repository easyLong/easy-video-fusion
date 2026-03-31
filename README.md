# easy-video-fusion

`easy-video-fusion` 是一个本地 Python 工具，用来把按顺序编号的图片和音频合成为 MP4 视频。

它适合这类场景：

- 每张图片对应一段 TTS 或配音音频
- 需要按顺序把多页内容合成为一个视频
- 希望自动按音频时长控制每页停留时间
- 希望在视频开头额外停留几秒，再进入第一段内容

项目同时提供两种使用方式：

- 主项目 CLI / GUI：适合直接在当前仓库里安装和使用
- 独立 skill 脚本：位于 `skills/easy-video-fusion/`，适合单独复制出去使用

## 功能概览

- 支持目录批量模式：按数字文件名自动配对图片和音频
- 支持显式配对模式：通过重复传入 `--image` / `--audio` 构建序列
- 支持每页额外缓冲秒数 `--padding-seconds`
- 支持视频开场停留秒数 `--intro-seconds`
- 支持自定义帧率和分辨率
- 支持桌面 GUI
- Windows 下支持用 `easy-video-fusion-gui.vbs` 静默启动 GUI

## 环境要求

- Python 3.10 或更高版本
- `pyproject.toml` 中声明的依赖

主项目安装后会使用这些 Python 依赖：

- `imageio-ffmpeg`
- `tinytag`

## 安装

在仓库根目录执行：

```bash
python -m pip install -e .
```

安装后会提供两个命令：

- `easy-video-fusion`
- `easy-video-fusion-gui`

## 命令行使用

查看帮助：

```bash
python -m easy_video_fusion --help
```

或：

```bash
easy-video-fusion --help
```

### 目录批量模式

```bash
python -m easy_video_fusion build ^
  --images-dir ./images ^
  --audios-dir ./audios ^
  --out ./out/video.mp4
```

### 显式配对模式

```bash
python -m easy_video_fusion build ^
  --image ./slides/01.png --audio ./tts/01.mp3 ^
  --image ./slides/02.png --audio ./tts/02.mp3 ^
  --out ./out/video.mp4
```

### 自定义开场时间

```bash
python -m easy_video_fusion build ^
  --images-dir ./images ^
  --audios-dir ./audios ^
  --out ./out/video.mp4 ^
  --intro-seconds 3
```

### 禁用开场

```bash
python -m easy_video_fusion build ^
  --images-dir ./images ^
  --audios-dir ./audios ^
  --out ./out/video.mp4 ^
  --intro-seconds 0
```

## 参数说明

| 参数 | 说明 | 默认值 |
| --- | --- | --- |
| `--images-dir <dir>` | 图片输入目录 | - |
| `--audios-dir <dir>` | 音频输入目录 | - |
| `--image <path>` | 单张图片输入，可重复传入 | - |
| `--audio <path>` | 单段音频输入，可重复传入 | - |
| `--out <file.mp4>` | 输出视频文件 | 必填 |
| `--padding-seconds <n>` | 每页音频结束后额外停留的秒数 | `1` |
| `--fps <n>` | 输出帧率 | `30` |
| `--resolution <WxH>` | 输出分辨率，例如 `1920x1080` | `1920x1080` |
| `--intro-seconds <n>` | 视频开场停留秒数，使用第一张图片静默显示 | `5` |

## 图片与音频目录规则

目录模式下，图片和音频要分别放在两个目录里，并且文件名必须使用数字编号。

支持示例：

- `1.png` + `1.mp3`
- `001.png` + `001.wav`
- `10.jpg` + `10.mp3`

规则如下：

- 只读取目录最外层文件，不递归子目录
- 按数字顺序排序，不按字符串字典序排序
- 图片和音频的编号必须完全一致
- 同一个目录内不能出现重复编号
- 如果有一边缺文件，程序会直接报错

## 输出行为

最终视频由两部分组成：

- 开场部分：第一张图片静默显示 `intro_seconds` 秒
- 内容部分：每一页的时长为 `音频时长 + padding_seconds`

程序会先生成临时分段，再使用 FFmpeg 合并为最终 MP4。临时文件在完成后会自动清理。

## 桌面 GUI

启动 GUI：

```bash
easy-video-fusion-gui
```

开发环境下也可以直接运行：

```bash
python -m easy_video_fusion.gui
```

Windows 下还可以双击仓库根目录的：

```text
easy-video-fusion-gui.vbs
```

它会直接拉起 GUI，并尽量避免弹出黑色控制台窗口。

## 独立 Skill 版本

仓库中还包含一个可单独复制的独立版本：

[`skills/easy-video-fusion`](./skills/easy-video-fusion)

它的定位和主项目不同：

- 主项目版本：依赖当前仓库源码与 `pyproject.toml` 依赖
- skill 版本：只依赖 skill 目录本身的 Python 脚本

skill 版入口：

```bash
python skills/easy-video-fusion/scripts/easy_video_fusion.py --help
```

skill 版说明：

- 适合单独复制目录后使用
- 只保留 Python 运行方式
- 不依赖当前仓库的 `src/easy_video_fusion/`
- 需要自己提供 `ffmpeg` / `ffprobe` 可执行环境

## 开发与测试

运行全部单元测试：

```bash
python -m unittest discover -s test
```

如果只想检查某个模块，可以按文件分别运行，例如：

```bash
python -m unittest discover -s test -p "test_args.py"
python -m unittest discover -s test -p "test_video_fusion.py"
```

## 常见错误

以下情况会直接报错并退出：

- Python 或依赖没有安装
- 图片和音频数量不一致
- 输入文件或目录不存在
- 目录中的文件名不是纯数字编号
- 同一个目录中存在重复编号
- 分辨率格式错误
- `--intro-seconds` 为负数

## 项目结构

```text
src/easy_video_fusion/        主项目源码
test/                         单元测试
easy-video-fusion-gui.vbs     Windows GUI 启动器
skills/easy-video-fusion/     可独立复制的 skill 版本
```

## 更新日志

### v0.1.2

- 重写 README，补充主项目 CLI、GUI、独立 skill 版本、目录规则和测试说明
- 新增 `skills/easy-video-fusion` 独立可复制版本，内置纯 Python CLI 脚本

### v0.1.1

- 新增 `--intro-seconds` 参数，支持自定义开场时间，默认 5 秒
- GUI 中新增开场秒数输入能力
- 修复开场视频缺少音频轨道后 concat 可能导致整段视频无声的问题
- 完善参数与使用文档

### v0.1.0

- 初始版本
- 提供 CLI 模式批量合成能力
- 提供 GUI 桌面应用
- 支持图片目录配对和显式参数配对
