#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke test: build the real UI, exercise it, and fail loudly on any error.

Runs headless-hidden (the window is withdrawn) so it never blocks a desktop
session. FFmpeg discovery and dialogs are stubbed — a modal dialog would
otherwise wait forever for a click that never comes.
"""

import os
import sys
import tempfile
import tkinter as tk
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import m4s2mp42  # noqa: E402

FAILURES = []


class StubDialogs:
    """Stands in for tkinter.messagebox; records instead of showing."""

    def __init__(self):
        self.shown = []

    def _record(self, title, message, answer="ok"):
        self.shown.append((title, message))
        return answer

    def showinfo(self, title, message, **_kwargs):
        return self._record(title, message)

    def showwarning(self, title, message, **_kwargs):
        return self._record(title, message)

    def showerror(self, title, message, **_kwargs):
        return self._record(title, message)

    def askyesno(self, title, message, **_kwargs):
        return self._record(title, message, answer=True)


def check(condition, message):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {message}")
    if not condition:
        FAILURES.append(message)


def make_fake_files(directory):
    """Two video streams + one audio stream, like a real Bilibili cache."""
    created = []
    for name, size in (("video-1-30080.m4s", 4096),
                       ("video-1-30064.m4s", 8192),
                       ("audio-1-30280.m4s", 1024)):
        path = os.path.join(directory, name)
        with open(path, "wb") as handle:
            handle.write(b"\x00" * size)
        created.append(path)
    return created


def run():
    root = tk.Tk()
    root.withdraw()

    original_find = m4s2mp42.find_ffmpeg
    original_dialogs = m4s2mp42.messagebox
    original_config = os.environ.get("M4S2MP42_CONFIG_DIR")
    settings_directory = tempfile.TemporaryDirectory()
    os.environ["M4S2MP42_CONFIG_DIR"] = settings_directory.name
    with open(
        os.path.join(settings_directory.name, m4s2mp42.SETTINGS_FILE),
        "w",
        encoding="utf-8",
    ) as handle:
        handle.write('{"mode":"invalid","crf":"broken","box":"bad"}')
    dialogs = StubDialogs()
    m4s2mp42.find_ffmpeg = lambda log_cb=None: None
    m4s2mp42.messagebox = dialogs

    try:
        app = m4s2mp42.App(root)
        root.update()
        check(True, "UI 构建完成，无异常")
        check(app.var_mode.get() == "delogo", "损坏模式设置恢复默认值")
        check(app.var_crf.get() == 18, "损坏 CRF 设置恢复默认值")
        check(app.var_box.get() == "8:25:500:95", "损坏水印区域恢复默认值")

        # --- empty state ------------------------------------------------
        # The root is withdrawn in this harness, so ask the geometry manager
        # instead of winfo_ismapped (which needs a mapped toplevel).
        empty_shown = lambda: app.empty_state.winfo_manager() == "place"
        check(empty_shown(), "空队列时显示空状态占位")
        check(app.tree.get_children() == (), "初始队列为空")

        # --- adding files ----------------------------------------------
        with tempfile.TemporaryDirectory() as tmp:
            files = make_fake_files(tmp)
            added = app._add_paths(files)
            root.update()
            check(added == 3, f"添加 3 个文件（实际 {added}）")
            check(len(app.tree.get_children()) == 3, "列表出现 3 行")
            check(not empty_shown(), "有文件后空状态隐藏")
            check(app.var_outdir.get() == tmp, "输出目录自动填充为文件所在目录")
            kinds = {app.tree.item(item, "values")[2] for item in
                     app.tree.get_children()}
            check(kinds == {"视频", "音频"}, f"正确识别轨道类型：{kinds}")

            # duplicate guard
            app._add_paths(files)
            root.update()
            check(len(app.tree.get_children()) == 3, "重复添加被去重")

            # --- row states -------------------------------------------
            first = files[0]
            for state in ("running", "done", "failed", "skipped", "pending"):
                app._set_row_state(first, state)
            root.update()
            app._update_summary()
            root.update()
            summary = app.chip_files.text
            check("3 个文件" in summary, f"汇总芯片更新：{summary}")

            # --- selection + removal ----------------------------------
            app.tree.selection_set(first)
            app.remove_selected()
            root.update()
            check(len(app.tree.get_children()) == 2, "移除选中项生效")
            app.clear_files()
            root.update()
            check(app.tree.get_children() == (), "清空列表生效")
            check(empty_shown(), "清空后空状态重新出现")

            # --- options ----------------------------------------------
            app._add_paths(files)
            root.update()
            app.var_mode.set("copy")
            app._sync_options()
            root.update()
            check(app.slider_crf._state == "disabled",
                  "无损模式下禁用 CRF/水印控件")
            app.var_mode.set("delogo")
            app._sync_options()
            root.update()
            check(app.slider_crf._state == "normal",
                  "切回去水印模式后控件恢复")

            app.var_box.set("bad-box")
            check(app._validate_box(live=True) is False, "非法水印区域被识别")
            app.var_box.set("8:25:500:95")
            check(app._validate_box(live=True) is True, "合法水印区域通过校验")

            app.var_preset.set("右上 1080P")
            app._apply_preset()
            check(app.var_box.get() == "1420:25:500:95", "预设值写入水印区域")

            app.var_crf.set(24)
            app._on_crf_change()
            root.update()
            check(app.label_crf.cget("text").startswith("24"),
                  f"CRF 标签更新：{app.label_crf.cget('text')}")

            # --- logging ------------------------------------------------
            app._log("日志写入测试")
            check("日志写入测试" in app.log.get("1.0", "end"), "日志可写入")
            app.clear_log()
            check(app.log.get("1.0", "end").strip() == "", "清空日志生效")

            # --- engine chips -------------------------------------------
            app._on_ffmpeg_ready(None)
            check(app.chip_engine.text == "FFmpeg 缺失", "引擎缺失态正确")
            app._on_ffmpeg_ready("C:/fake/ffmpeg.exe")
            root.update()
            check(app.chip_engine.text == "FFmpeg 就绪", "引擎就绪态正确")

            # --- simulated job lifecycle --------------------------------
            app.progress.configure(maximum=3)
            for index in range(1, 4):
                app.events.put(("progress", index))
                app.events.put(("counts", index, 0, 0))
            app.events.put(("finish", 3, 0, 0, False))
            root.update()
            app._poll_events()
            root.update()
            check(app.label_progress.cget("text") == "3 / 3", "进度文本更新")
            check(app.chip_ok.text == "成功 3", "成功计数芯片更新")
            check(app.btn_start.text == "再转一次", "完成后主按钮文案变化")
            check(any("处理完成" in title for title, _ in dialogs.shown),
                  "收尾时弹出完成提示")

            # --- theme switch -------------------------------------------
            app.toggle_theme()
            root.update()
            check(app.theme_mode == "dark", "切换到暗色主题")
            check(app.log.cget("background") == app._t["surface_sunken"],
                  "暗色主题应用到日志面板")
            app.toggle_theme()
            root.update()
            check(app.theme_mode == "light", "切回亮色主题")

            # --- settings round-trip ------------------------------------
            app.var_crf.set(21)
            app._save_settings()
            restored = app._load_settings()
            check(restored.get("crf") == 21, "设置持久化并可读回")
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        FAILURES.append("运行期抛出异常")
    finally:
        m4s2mp42.find_ffmpeg = original_find
        m4s2mp42.messagebox = original_dialogs
        if original_config is None:
            os.environ.pop("M4S2MP42_CONFIG_DIR", None)
        else:
            os.environ["M4S2MP42_CONFIG_DIR"] = original_config
        settings_directory.cleanup()
        try:
            root.destroy()
        except tk.TclError:
            pass

    print()
    if FAILURES:
        print(f"{len(FAILURES)} 项失败：")
        for item in FAILURES:
            print(f"  - {item}")
        sys.exit(1)
    print("全部检查通过。")


if __name__ == "__main__":
    run()
