# m4s2mp4

**m4s2mp4 是一个 m4s 文件转换工具**，用于把 B 站（bilibili）下载器生成的 `.m4s` 音视频流转换为标准的 MP4 文件。

它解决了手动转换 m4s 时的两个常见痛点：

1. **掉帧**：B 站 m4s 文件头带有垃圾前缀，直接转换会导致时间戳错乱、播放掉帧。本工具会自动清理前缀并保留原始时间戳。
2. **水印**：可选去除左上角 UP 主水印。

此外还支持自动合并匹配的音频流、批量转换文件夹，并提供图形界面和命令行两种使用方式。

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)]()

---

## 功能特性

- 🎬 **防掉帧**：自动清理 m4s 头部垃圾前缀，保留原始时间戳，杜绝播放卡顿掉帧
- 🧹 **去水印**：可选去除左上角水印（`delogo` 滤镜，区域可调）
- 🔊 **音频合并**：自动配对同目录下名称匹配的视频流和音频流
- 🖥️ **图形界面 + 命令行**：两种使用方式，满足不同场景
- 🔒 **安全输出**：先写临时文件、成功后原子替换，转换失败不会留下半成品
- 📦 **零额外依赖**：核心逻辑仅用 Python 标准库，GUI 依赖 Tkinter（官方自带）

---

## 环境要求

| 依赖 | 说明 |
| --- | --- |
| Python 3.8+ | 图形界面需要包含 Tkinter（Python 官方安装版自带） |
| FFmpeg | 可选。未安装时，程序会在首次运行自动下载官方 Windows 版到程序目录 |

> 💡 **开箱即用**：如果系统未安装 FFmpeg，程序会在首次运行时自动从官方源
> （[gyan.dev](https://www.gyan.dev/ffmpeg/builds/)）下载精简版 `ffmpeg.exe`
> 到程序目录，之后离线可用，无需手动安装。

---

## 目录结构

```
m4s2mp4/
├── m4s2mp4.py            # 图形界面（GUI）
├── m4s2mp4_cli.py        # 命令行入口
├── m4s2mp4_core.py       # 核心转换逻辑（GUI、CLI 共用）
├── ffmpeg_bootstrap.py   # FFmpeg 自动下载引导（首次运行获取）
├── test_m4s2mp4_core.py  # 单元测试
├── 启动GUI.bat           # Windows 双击启动 GUI
├── LICENSE               # MIT 许可证
└── README.md
```

---

## 使用方法

### 方法一：图形界面（GUI）

**Windows** 用户直接双击 `启动GUI.bat` 即可打开。

**macOS / Linux** 用户在终端运行：

```bash
python m4s2mp4.py
```

打开后按以下步骤操作：

1. 点击「添加文件」或「添加文件夹」，选择要转换的 `.m4s` 文件；
2. 勾选「去除左上角水印」（默认开启）、「合并音频」等选项；
3. 设置输出目录（默认与源文件同目录）；
4. 点击「开始转换」，等待进度条完成。

### 方法二：命令行（CLI）

#### 1. 转换单个文件（默认去水印）

```bash
python m4s2mp4_cli.py "视频-1-30080.m4s"
```

输出文件会生成在源文件所在目录，文件名为去掉 `-1-30080` 后缀后的名称，例如 `视频.mp4`。

#### 2. 批量转换整个文件夹

```bash
python m4s2mp4_cli.py "D:\bilibili"
```

默认只扫描当前文件夹，如需递归处理所有子文件夹，加 `--recursive`：

```bash
python m4s2mp4_cli.py "D:\bilibili" --recursive
```

#### 3. 不去水印（保留原画面，速度快、无画质损失）

```bash
python m4s2mp4_cli.py "视频-1-30080.m4s" --no-delogo
```

#### 4. 合并音频（自动配对视频流 + 音频流）

```bash
python m4s2mp4_cli.py "D:\bilibili" --audio --recursive
```

启用 `--audio` 后，工具会自动查找同目录下名称匹配的音频流（`-1-30280.m4s`）并合并进 MP4。

#### 5. 指定输出目录和画质

```bash
python m4s2mp4_cli.py "视频-1-30080.m4s" -o "D:\output" --crf 20
```

#### 6. 指定水印区域、允许覆盖

```bash
python m4s2mp4_cli.py "视频-1-30080.m4s" --delogo-box 8:25:500:95 --overwrite
```

---

## 命令行参数说明

| 参数 | 说明 |
| --- | --- |
| `inputs` | 一个或多个 m4s 文件或文件夹（必填） |
| `-o, --output DIR` | 输出目录，默认使用第一个输入文件所在目录 |
| `--no-delogo` | 不去水印，改用视频流复制（速度快、无画质损失） |
| `--delogo-box X:Y:W:H` | 水印区域，默认 `8:25:500:95` |
| `--audio` | 合并同目录下名称匹配的音频流 |
| `--crf N` | 去水印重编码画质参数，范围 0–51，默认 18（越小越清晰） |
| `--recursive` | 递归扫描输入文件夹 |
| `--overwrite` | 覆盖已有同名 MP4，默认跳过 |

---

## 文件命名与流类型识别

B 站 DASH 流按 `名称-1-清晰度代码.m4s` 命名，工具会自动识别：

| 后缀 | 类型 |
| --- | --- |
| `-1-30080` / `-1-30064` / `-1-30032` | 视频流（1080P / 720P / 480P） |
| `-1-30280` / `-1-30216` / `-1-30232` | 音频流 |

---

## 工作原理

转换流程共四步：

1. **清理前缀**：定位 `ftyp` 并移除其前的垃圾字节（分块内存复制，不整读大文件）
2. **remux**：`ffmpeg -c:v copy` 保留原始时间戳，杜绝掉帧
3. **去水印**（可选）：`delogo` 滤镜 + `libx264` 重新编码
4. **原子落盘**：写临时文件 → 校验 → `os.replace` 原子替换

---

## 运行测试

```bash
python -m unittest -v
```

---

## 许可证

[MIT](LICENSE)

> ⚠️ 本项目仅供学习与个人备份使用，请尊重原作者版权，勿将去除水印后的视频用于商业用途或二次传播。
