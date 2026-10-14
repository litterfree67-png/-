# m4s2mp4

将 B 站下载器生成的 `.m4s` 视频流转换为标准 MP4 文件，可选合并匹配的音频流或去除左上角水印。

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)]()

## 特性

- 🎬 **防掉帧**：自动清理 B 站 m4s 头部的垃圾前缀，remux 保留原始时间戳，避免时间戳错乱导致的掉帧
- 🧹 **去水印**：可选去除左上角 UP 主水印（`delogo`，区域可调）
- 🔊 **音频合并**：自动配对同目录下名称匹配的 `30280` 音频流
- 🖥️ **图形界面** + ⌨️ **命令行** 双入口，均复用同一套核心逻辑
- 🔒 **原子输出**：先写临时文件，成功后原子替换；失败不留半成品、不破坏已有文件
- 📦 **零额外依赖**：核心逻辑仅用标准库，GUI 依赖 Tkinter（Python 官方自带）

## 目录结构

```
m4s2mp4/
├── m4s2mp4.py            # Tkinter 图形界面
├── m4s2mp4_cli.py        # 命令行 / 批量转换
├── m4s2mp4_core.py       # 核心转换逻辑（GUI、CLI 共用）
├── test_m4s2mp4_core.py  # 单元测试
├── 启动GUI.bat           # Windows 双击启动 GUI
├── LICENSE               # MIT 许可证
└── README.md
```

## 环境要求

- **Python 3.8+**（GUI 需要包含 Tkinter，官方安装版自带）
- **FFmpeg**：加入系统 `PATH`，或将 `ffmpeg.exe` 放在程序目录

## 快速开始

### 图形界面

Windows 下双击 `启动GUI.bat`；其他平台运行：

```bash
python m4s2mp4.py
```

添加 m4s 文件或文件夹 → 设置选项 → 开始转换。

### 命令行

```bash
# 单文件转换（默认去水印）
python m4s2mp4_cli.py "视频-1-30080.m4s"

# 批量转换文件夹，递归扫描并合并匹配音频
python m4s2mp4_cli.py "D:\bilibili" --recursive --audio

# 保留原画面（不去水印、流复制、无画质损失）
python m4s2mp4_cli.py "视频-1-30080.m4s" --no-delogo -o "D:\output"

# 指定水印区域、画质，并允许覆盖
python m4s2mp4_cli.py "视频-1-30080.m4s" --delogo-box 8:25:500:95 --crf 20 --overwrite
```

## 命令行选项

| 选项 | 说明 |
| --- | --- |
| `--no-delogo` | 不去水印，改用视频流复制（速度快、无画质损失） |
| `--delogo-box X:Y:W:H` | 水印区域，默认 `8:25:500:95` |
| `--audio` | 合并同目录下名称匹配的音频流 |
| `--crf N` | 去水印重编码画质参数，范围 0–51，默认 18（越小越清晰） |
| `--recursive` | 递归扫描输入文件夹 |
| `-o, --output DIR` | 输出目录，默认使用第一个输入文件所在目录 |
| `--overwrite` | 覆盖已有同名 MP4，默认跳过 |

## 工作原理

B 站 DASH 流按 `名称-1-清晰度代码.m4s` 命名：

| 后缀 | 类型 |
| --- | --- |
| `-1-30080` / `-1-30064` / `-1-30032` | 视频流（1080P / 720P / 480P） |
| `-1-30280` / `-1-30216` / `-1-30232` | 音频流 |

转换流程：

1. **清理前缀**：定位 `ftyp` 并移除其前的垃圾字节（边界内存复制，不整读大文件）
2. **remux**：`ffmpeg -c:v copy` 保留原始时间戳，杜绝掉帧
3. **去水印**（可选）：`delogo` 滤镜 + `libx264` 重新编码
4. **原子落盘**：写临时文件 → 校验 → `os.replace` 原子替换

## 运行测试

```bash
python -m unittest -v
```

## 许可证

[MIT](LICENSE)

> ⚠️ 本项目仅供学习与个人备份使用，请尊重原作者版权，勿将去除水印后的视频用于商业用途或二次传播。
