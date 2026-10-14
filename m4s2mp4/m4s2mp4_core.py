#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared conversion and file-discovery logic for the GUI and CLI."""

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Tuple


VIDEO_SUFFIXES = ("-30080", "-30064", "-30032")
AUDIO_SUFFIXES = ("-30280", "-30216", "-30232")
DEFAULT_DELOGO_BOX = (8, 25, 500, 95)
FFMPEG_TIMEOUT_SECONDS = 1800
LOG_CALLBACK = Callable[[str], None]


class ConversionError(RuntimeError):
    """An input could not be converted."""


@dataclass(frozen=True)
class ConversionOptions:
    delogo: bool = True
    delogo_box: Tuple[int, int, int, int] = DEFAULT_DELOGO_BOX
    crf: int = 18
    overwrite: bool = False


def find_ffmpeg() -> Optional[str]:
    """Find a bundled or PATH-installed FFmpeg executable."""
    suffixes = (".exe", "") if os.name == "nt" else ("",)
    directory = os.path.dirname(os.path.abspath(__file__))
    for suffix in suffixes:
        candidate = os.path.join(directory, "ffmpeg" + suffix)
        if os.path.isfile(candidate):
            return candidate
    return shutil.which("ffmpeg")


def validate_options(options: ConversionOptions) -> None:
    if not 0 <= options.crf <= 51:
        raise ValueError("CRF 必须在 0 到 51 之间")
    if len(options.delogo_box) != 4:
        raise ValueError("水印区域必须由 x:y:w:h 四个整数构成")
    x, y, width, height = options.delogo_box
    if x < 0 or y < 0 or width <= 0 or height <= 0:
        raise ValueError("水印区域的 x、y 不能小于 0，宽度和高度必须大于 0")


def parse_delogo_box(value: str) -> Tuple[int, int, int, int]:
    try:
        parts = tuple(int(part.strip()) for part in value.split(":"))
    except ValueError as exc:
        raise ValueError("水印区域格式应为 x:y:w:h，且均为整数") from exc
    if len(parts) != 4:
        raise ValueError("水印区域格式应为 x:y:w:h，且均为整数")
    x, y, width, height = parts
    if x < 0 or y < 0 or width <= 0 or height <= 0:
        raise ValueError("水印区域的 x、y 不能小于 0，宽度和高度必须大于 0")
    return x, y, width, height


def classify_files(paths: Iterable[str]) -> Tuple[List[str], List[str]]:
    videos, audios = [], []
    for path in paths:
        name = os.path.basename(path).lower()
        stem = os.path.splitext(name)[0]
        if not name.endswith(".m4s"):
            continue
        if stem.endswith(AUDIO_SUFFIXES):
            audios.append(path)
        else:
            videos.append(path)
    return videos, audios


def media_key(path: str) -> Tuple[str, str]:
    """Return a folder-scoped key shared by matching video/audio stream names."""
    stem = os.path.splitext(os.path.basename(path))[0]
    stem = re.sub(r"-1-(?:30080|30064|30032|30280|30216|30232)$", "", stem, flags=re.I)
    stem = re.sub(r"-(?:30080|30064|30032|30280|30216|30232)$", "", stem, flags=re.I)
    return os.path.normcase(os.path.dirname(os.path.abspath(path))), stem.casefold()


def build_audio_index(audio_paths: Iterable[str]) -> Dict[Tuple[str, str], str]:
    index = {}
    for audio_path in audio_paths:
        index.setdefault(media_key(audio_path), audio_path)
    return index


def collect_files(paths: Iterable[str], recursive: bool = False) -> List[str]:
    files = set()
    for path in paths:
        if os.path.isfile(path) and path.lower().endswith(".m4s"):
            files.add(os.path.abspath(path))
        elif os.path.isdir(path):
            if recursive:
                for root, dirs, names in os.walk(path):
                    dirs.sort()
                    for name in names:
                        if name.lower().endswith(".m4s"):
                            files.add(os.path.abspath(os.path.join(root, name)))
            else:
                for name in os.listdir(path):
                    full_path = os.path.join(path, name)
                    if os.path.isfile(full_path) and name.lower().endswith(".m4s"):
                        files.add(os.path.abspath(full_path))
    return sorted(files, key=lambda item: (os.path.normcase(item), item))


def output_path_for(src_path: str, output_dir: str) -> str:
    stem = os.path.splitext(os.path.basename(src_path))[0]
    stem = re.sub(r"-1-(?:30080|30064|30032)$", "", stem, flags=re.I)
    stem = re.sub(r"-(?:30080|30064|30032)$", "", stem, flags=re.I)
    return os.path.join(output_dir, stem + ".mp4")


def strip_garbage_prefix(src_path: str) -> Optional[str]:
    """Strip a leading Bilibili M4S prefix using bounded-memory file copying."""
    file_size = os.path.getsize(src_path)
    with open(src_path, "rb") as source:
        header = source.read(min(file_size, 1024 * 1024))

    search_from = 0
    prefix_length = None
    while True:
        index = header.find(b"ftyp", search_from)
        if index < 0:
            break
        search_from = index + 4
        if index < 4:
            continue
        box_size = int.from_bytes(header[index - 4:index], "big")
        candidate = index - 4
        if 8 <= box_size <= file_size - candidate:
            prefix_length = candidate
            break

    if not prefix_length:
        return None

    directory = os.path.dirname(os.path.abspath(src_path))
    basename = os.path.basename(src_path)
    handle, temp_path = tempfile.mkstemp(
        prefix="." + basename + ".", suffix=".clean.m4s", dir=directory
    )
    try:
        with os.fdopen(handle, "wb") as target, open(src_path, "rb") as source:
            source.seek(prefix_length)
            shutil.copyfileobj(source, target, length=1024 * 1024)
        return temp_path
    except Exception:
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise


def _run_ffmpeg(command: List[str]) -> None:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=FFMPEG_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ConversionError(
            f"FFmpeg 转换超时（{FFMPEG_TIMEOUT_SECONDS // 60} 分钟）"
        ) from exc
    except OSError as exc:
        raise ConversionError(f"无法启动 FFmpeg：{exc}") from exc

    if result.returncode:
        lines = (result.stderr or "").strip().splitlines()
        detail = "\n".join(lines[-4:]) if lines else "未知错误"
        raise ConversionError("FFmpeg 转换失败：\n" + detail)


def convert_file(
    video_path: str,
    output_dir: str,
    options: ConversionOptions,
    log_cb: Optional[LOG_CALLBACK] = None,
    audio_path: Optional[str] = None,
    ffmpeg: Optional[str] = None,
) -> Optional[str]:
    """Convert one video stream, optionally merging its matching audio stream."""
    log = log_cb or (lambda _message: None)
    validate_options(options)
    executable = ffmpeg or find_ffmpeg()
    if not executable:
        raise ConversionError("未找到 FFmpeg，请安装 FFmpeg 或将其放入程序目录")
    if not os.path.isfile(video_path):
        raise ConversionError(f"输入文件不存在：{video_path}")
    if audio_path and not os.path.isfile(audio_path):
        raise ConversionError(f"音频文件不存在：{audio_path}")
    os.makedirs(output_dir, exist_ok=True)

    final_path = output_path_for(video_path, output_dir)
    if os.path.exists(final_path) and not options.overwrite:
        log(f"跳过，输出文件已存在（未启用覆盖）：{final_path}")
        return None

    temp_inputs = []
    temp_output = None
    try:
        video_input = strip_garbage_prefix(video_path)
        if video_input:
            temp_inputs.append(video_input)
        else:
            video_input = video_path

        audio_input = None
        if audio_path:
            audio_input = strip_garbage_prefix(audio_path)
            if audio_input:
                temp_inputs.append(audio_input)
            else:
                audio_input = audio_path

        handle, temp_output = tempfile.mkstemp(
            prefix="." + os.path.basename(final_path) + ".",
            suffix=".partial.mp4",
            dir=output_dir,
        )
        os.close(handle)

        command = [
            executable, "-hide_banner", "-nostdin", "-v", "error", "-y",
            "-i", video_input,
        ]
        if audio_input:
            command.extend(["-i", audio_input])
        command.extend(["-map", "0:v:0"])
        if audio_input:
            command.extend(["-map", "1:a:0"])

        if options.delogo:
            x, y, width, height = options.delogo_box
            command.extend([
                "-vf", f"delogo=x={x}:y={y}:w={width}:h={height}",
                "-c:v", "libx264", "-preset", "medium", "-crf", str(options.crf),
            ])
        else:
            command.extend(["-c:v", "copy"])

        if audio_input:
            command.extend(["-c:a", "copy"])
        else:
            command.append("-an")
        command.extend(["-movflags", "+faststart", temp_output])

        log(f"正在转换：{os.path.basename(video_path)}")
        _run_ffmpeg(command)
        if not os.path.isfile(temp_output) or os.path.getsize(temp_output) == 0:
            raise ConversionError("FFmpeg 未生成有效的输出文件")
        if os.path.exists(final_path) and not options.overwrite:
            log(f"跳过，输出文件已存在（未启用覆盖）：{final_path}")
            return None
        os.replace(temp_output, final_path)
        temp_output = None
        log(f"转换完成：{final_path}")
        return final_path
    finally:
        for path in temp_inputs:
            try:
                os.remove(path)
            except OSError:
                pass
        if temp_output:
            try:
                os.remove(temp_output)
            except OSError:
                pass
