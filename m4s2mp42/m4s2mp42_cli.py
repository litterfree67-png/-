#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Command-line interface for m4s2mp42."""

import argparse
import os
import sys

from m4s2mp4_core import (
    ConversionError,
    ConversionOptions,
    build_audio_index,
    classify_files,
    collect_files,
    convert_file,
    find_ffmpeg,
    media_key,
    parse_delogo_box,
    validate_options,
)


def build_parser():
    parser = argparse.ArgumentParser(
        description="将 B 站 M4S 音视频流转换为 MP4"
    )
    parser.add_argument("inputs", nargs="+", help="M4S 文件或文件夹")
    parser.add_argument("-o", "--output", help="输出目录")
    parser.add_argument("--no-delogo", action="store_true", help="不去水印")
    parser.add_argument(
        "--delogo-box",
        default="8:25:500:95",
        help="水印区域 x:y:w:h",
    )
    parser.add_argument("--audio", action="store_true", help="合并匹配音频")
    parser.add_argument("--crf", type=int, default=18, help="画质参数 0-51")
    parser.add_argument("--recursive", action="store_true", help="递归扫描文件夹")
    parser.add_argument("--overwrite", action="store_true", help="覆盖已有 MP4")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        options = ConversionOptions(
            delogo=not args.no_delogo,
            delogo_box=parse_delogo_box(args.delogo_box),
            crf=args.crf,
            overwrite=args.overwrite,
        )
        validate_options(options)
    except ValueError as exc:
        parser.error(str(exc))

    missing = [path for path in args.inputs if not os.path.exists(path)]
    if missing:
        for path in missing:
            print(f"错误：输入路径不存在：{path}", file=sys.stderr)
        return 2

    files = collect_files(args.inputs, args.recursive)
    videos, audios = classify_files(files)
    if not videos:
        print("错误：没有找到可转换的视频流。", file=sys.stderr)
        return 2

    ffmpeg = find_ffmpeg(log_cb=lambda message: print(message, file=sys.stderr))
    if not ffmpeg:
        print("错误：未找到可用的 FFmpeg。", file=sys.stderr)
        return 2

    output_dir = args.output or os.path.dirname(videos[0])
    try:
        os.makedirs(output_dir, exist_ok=True)
    except OSError as exc:
        print(f"错误：无法创建输出目录：{exc}", file=sys.stderr)
        return 2

    audio_index = build_audio_index(audios)
    succeeded = skipped = failed = 0
    for video in videos:
        audio = audio_index.get(media_key(video)) if args.audio else None
        try:
            result = convert_file(
                video,
                output_dir,
                options,
                log_cb=lambda message: print(message, flush=True),
                audio_path=audio,
                ffmpeg=ffmpeg,
            )
            if result:
                succeeded += 1
            else:
                skipped += 1
        except ConversionError as exc:
            failed += 1
            print(f"失败：{exc}", file=sys.stderr)

    print(f"完成：成功 {succeeded}，跳过 {skipped}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
