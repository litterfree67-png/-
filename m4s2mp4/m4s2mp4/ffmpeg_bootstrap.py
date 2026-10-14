#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Automatically download a bundled FFmpeg for first-time users.

When FFmpeg is not found on PATH or in the program directory, this module
downloads the official Windows essentials build and extracts ``ffmpeg.exe``
next to the program, so the tool works out of the box.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

# Official Gyan.dev Windows essentials build (stable redirect URL).
FFMPEG_DOWNLOAD_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

# Expected path suffix inside the zip (zip entries always use "/").
ZIP_EXE_SUFFIX = "bin/ffmpeg.exe"


def program_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def bundled_ffmpeg_path() -> str:
    name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    return os.path.join(program_dir(), name)


def _find_ffmpeg_in_dir(directory: str):
    suffixes = (".exe", "") if os.name == "nt" else ("",)
    for suffix in suffixes:
        candidate = os.path.join(directory, "ffmpeg" + suffix)
        if os.path.isfile(candidate):
            return candidate
    return None


def _ffmpeg_on_path():
    return shutil.which("ffmpeg")


def find_or_install_ffmpeg(log_cb=None):
    """Return an FFmpeg path, downloading a bundled build if necessary."""
    log = log_cb or (lambda _message: None)

    bundled = _find_ffmpeg_in_dir(program_dir())
    if bundled:
        return bundled

    on_path = _ffmpeg_on_path()
    if on_path:
        return on_path

    # Nothing available: download a bundled build (Windows only).
    if os.name != "nt":
        log("未找到 FFmpeg，请通过系统包管理器安装（如 apt/brew），或手动放置到程序目录。")
        return None

    log("未检测到 FFmpeg，正在自动下载官方 Windows 版（首次运行约 110 MB）...")
    try:
        _download_and_extract_ffmpeg(log)
    except Exception as exc:  # noqa: BLE001 - surface a friendly message
        log(f"FFmpeg 自动下载失败：{exc}")
        log("请手动从 https://www.gyan.dev/ffmpeg/builds/ 下载，"
            "并将 ffmpeg.exe 放入程序目录。")
        return None

    bundled = _find_ffmpeg_in_dir(program_dir())
    if bundled:
        log("FFmpeg 已就绪。")
    return bundled


def _download_and_extract_ffmpeg(log):
    with tempfile.TemporaryDirectory(prefix="m4s2mp4_ffmpeg_") as tmp:
        zip_path = os.path.join(tmp, "ffmpeg.zip")
        _download(FFMPEG_DOWNLOAD_URL, zip_path, log)

        log("正在解压并提取 ffmpeg.exe ...")
        target = bundled_ffmpeg_path()
        _extract_ffmpeg_exe(zip_path, target)


def _download(url, destination, log):
    def report(block_count, block_size, total_size):
        downloaded = block_count * block_size
        if total_size > 0:
            percent = downloaded * 100 // total_size
            log(f"  下载进度：{percent}% ({downloaded // (1024 * 1024)} MB / "
                f"{total_size // (1024 * 1024)} MB)")
        else:
            log(f"  已下载：{downloaded // (1024 * 1024)} MB")

    urllib.request.urlretrieve(url, destination, reporthook=report)


def _extract_ffmpeg_exe(zip_path, target):
    with zipfile.ZipFile(zip_path, "r") as archive:
        # Locate the ffmpeg.exe entry (nested under a versioned folder/bin).
        candidates = [
            name for name in archive.namelist()
            if name.endswith(ZIP_EXE_SUFFIX) and "ffmpeg.exe" in name
        ]
        if not candidates:
            raise RuntimeError("压缩包中未找到 ffmpeg.exe")
        entry = candidates[0]

        # Extract to a temporary file, then move atomically into place.
        handle, temp_path = tempfile.mkstemp(
            prefix=".ffmpeg.", suffix=".exe", dir=program_dir()
        )
        os.close(handle)
        try:
            with archive.open(entry) as source, open(temp_path, "wb") as dest:
                shutil.copyfileobj(source, dest, length=1024 * 1024)
            os.replace(temp_path, target)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


if __name__ == "__main__":
    path = find_or_install_ffmpeg(log_cb=lambda msg: print(msg, file=sys.stderr))
    if path:
        print(path)
    else:
        sys.exit(1)
