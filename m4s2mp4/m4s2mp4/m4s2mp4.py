#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tkinter GUI for converting Bilibili M4S streams to MP4."""

import os
import queue
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from m4s2mp4_core import (
    ConversionError,
    ConversionOptions,
    DEFAULT_DELOGO_BOX,
    build_audio_index,
    classify_files,
    convert_file,
    find_ffmpeg,
    media_key,
    parse_delogo_box,
)


class M4s2Mp4App:
    def __init__(self, root):
        self.root = root
        self.root.title("m4s2mp4")
        self.root.geometry("920x740")
        self.root.minsize(800, 680)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.files = []
        self.events = queue.Queue()
        self.worker_active = False
        self.action_buttons = []
        self.ffmpeg_status = tk.StringVar(value="检查 FFmpeg...")
        self.file_summary = tk.StringVar(value="0 个文件 · 0 B")
        self.job_status = tk.StringVar(value="就绪")
        self.progress_text = tk.StringVar(value="0 / 0")
        self.ffmpeg = None
        self._configure_style()
        self.build_ui()
        self._sync_option_states()
        self.root.after(100, self._poll_events)
        self._ensure_ffmpeg_async()

    def _configure_style(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", font=("Microsoft YaHei UI", 9), foreground="#26343d")
        style.configure("TFrame", background="#f2f5f7")
        style.configure("TLabel", background="#f2f5f7", foreground="#26343d")
        style.configure("Muted.TLabel", foreground="#64737d")
        style.configure("Header.TFrame", background="#24333c")
        style.configure(
            "HeaderTitle.TLabel",
            background="#24333c",
            foreground="#ffffff",
            font=("Microsoft YaHei UI", 15, "bold"),
        )
        style.configure(
            "HeaderStatus.TLabel",
            background="#354b55",
            foreground="#d7edf0",
            padding=(10, 5),
            font=("Microsoft YaHei UI", 9, "bold"),
        )
        style.configure(
            "TLabelframe",
            background="#f2f5f7",
            bordercolor="#d6dee3",
            relief="solid",
        )
        style.configure(
            "TLabelframe.Label",
            background="#f2f5f7",
            foreground="#364650",
            font=("Microsoft YaHei UI", 9, "bold"),
        )
        style.configure("TButton", padding=(10, 7), background="#ffffff")
        style.map(
            "TButton",
            background=[("active", "#e7eef1"), ("disabled", "#edf0f2")],
            foreground=[("disabled", "#9ba7ad")],
        )
        style.configure(
            "Primary.TButton",
            padding=(18, 8),
            background="#16748a",
            foreground="#ffffff",
            font=("Microsoft YaHei UI", 10, "bold"),
            borderwidth=0,
        )
        style.map(
            "Primary.TButton",
            background=[("active", "#125e70"), ("disabled", "#a8c0c7")],
            foreground=[("disabled", "#f5f8f9")],
        )
        style.configure(
            "Treeview",
            rowheight=29,
            background="#ffffff",
            fieldbackground="#ffffff",
            foreground="#26343d",
            bordercolor="#d6dee3",
            font=("Microsoft YaHei UI", 9),
        )
        style.configure(
            "Treeview.Heading",
            background="#e8eef1",
            foreground="#43535d",
            padding=(8, 7),
            font=("Microsoft YaHei UI", 9, "bold"),
        )
        style.map(
            "Treeview",
            background=[("selected", "#d5e9ed")],
            foreground=[("selected", "#183d49")],
        )
        style.configure(
            "Horizontal.TProgressbar",
            background="#16839a",
            troughcolor="#dfe7ea",
            bordercolor="#dfe7ea",
            lightcolor="#16839a",
            darkcolor="#16839a",
            thickness=10,
        )

    def build_ui(self):
        self.root.configure(background="#f2f5f7")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        shell = ttk.Frame(self.root, padding=(16, 10, 16, 8))
        shell.grid(row=0, column=0, sticky="nsew")
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(1, weight=3)
        shell.rowconfigure(5, weight=2)

        header = ttk.Frame(shell, style="Header.TFrame", padding=(16, 11))
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="m4s2mp4", style="HeaderTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            header, textvariable=self.ffmpeg_status, style="HeaderStatus.TLabel"
        ).grid(row=0, column=1, sticky="e")

        list_frame = ttk.LabelFrame(shell, text="文件队列", padding=(10, 8, 10, 10))
        list_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 8))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(list_frame)
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        toolbar.columnconfigure(4, weight=1)
        buttons = (
            ("添加文件", self.add_files),
            ("添加文件夹", self.add_folder),
            ("移除选中", self.remove_selected),
            ("清空列表", self.clear_files),
        )
        for column, (text, command) in enumerate(buttons):
            button = ttk.Button(toolbar, text=text, command=command)
            button.grid(row=0, column=column, padx=(0, 6))
            self.action_buttons.append(button)
        ttk.Label(toolbar, textvariable=self.file_summary, style="Muted.TLabel").grid(
            row=0, column=5, sticky="e", padx=(8, 2)
        )

        self.tree = ttk.Treeview(
            list_frame,
            columns=("name", "folder", "type", "size"),
            show="headings",
            selectmode="extended",
            height=5,
        )
        self.tree.heading("name", text="文件名")
        self.tree.heading("folder", text="所在文件夹")
        self.tree.heading("type", text="类型")
        self.tree.heading("size", text="大小")
        self.tree.column("name", width=300, minwidth=160, stretch=True)
        self.tree.column("folder", width=300, minwidth=150, stretch=True)
        self.tree.column("type", width=90, minwidth=80, anchor="center", stretch=False)
        self.tree.column("size", width=100, minwidth=90, anchor="e", stretch=False)
        self.tree.tag_configure("audio", foreground="#54717c")
        self.tree.grid(row=1, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.bind("<Delete>", lambda _event: self.remove_selected())
        self.root.bind("<Control-o>", lambda _event: self.add_files())
        self.root.bind("<Control-Return>", lambda _event: self.start_convert())

        option_frame = ttk.LabelFrame(shell, text="转换选项", padding=(10, 7, 10, 9))
        option_frame.grid(row=2, column=0, sticky="ew", pady=(0, 7))
        for column in (1, 3, 5):
            option_frame.columnconfigure(column, weight=1)

        self.var_delogo = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            option_frame,
            text="去除水印",
            variable=self.var_delogo,
            command=self._sync_option_states,
        ).grid(row=0, column=0, sticky="w", padx=(3, 16), pady=(1, 8))

        self.var_audio = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            option_frame,
            text="合并匹配音频",
            variable=self.var_audio,
        ).grid(row=0, column=1, sticky="w", padx=(3, 16), pady=(1, 8))

        self.var_overwrite = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            option_frame,
            text="覆盖已有 MP4",
            variable=self.var_overwrite,
        ).grid(row=0, column=2, sticky="w", padx=(3, 10), pady=(1, 8))

        ttk.Label(option_frame, text="水印区域", style="Muted.TLabel").grid(
            row=1, column=0, sticky="w", padx=(3, 6), pady=2
        )
        self.var_box = tk.StringVar(value="8:25:500:95")
        self.entry_box = ttk.Entry(
            option_frame, textvariable=self.var_box, width=18, justify="center"
        )
        self.entry_box.grid(row=1, column=1, sticky="w", padx=(0, 18), pady=2)

        ttk.Label(option_frame, text="CRF", style="Muted.TLabel").grid(
            row=1, column=2, sticky="w", padx=(3, 6), pady=2
        )
        self.var_crf = tk.StringVar(value="18")
        self.spin_crf = ttk.Spinbox(
            option_frame,
            from_=0,
            to=51,
            increment=1,
            textvariable=self.var_crf,
            width=6,
            justify="center",
        )
        self.spin_crf.grid(row=1, column=3, sticky="w", padx=(0, 6), pady=2)
        ttk.Label(option_frame, text="0–51", style="Muted.TLabel").grid(
            row=1, column=4, sticky="w", padx=(0, 8), pady=2
        )

        output_frame = ttk.Frame(shell)
        output_frame.grid(row=3, column=0, sticky="ew", pady=(0, 7))
        output_frame.columnconfigure(1, weight=1)
        ttk.Label(output_frame, text="输出目录", style="Muted.TLabel").grid(
            row=0, column=0, sticky="w", padx=(1, 9)
        )
        self.var_outdir = tk.StringVar()
        ttk.Entry(output_frame, textvariable=self.var_outdir).grid(
            row=0, column=1, sticky="ew", padx=(0, 7)
        )
        ttk.Button(output_frame, text="浏览...", command=self.choose_outdir).grid(
            row=0, column=2
        )

        action_frame = ttk.Frame(shell)
        action_frame.grid(row=4, column=0, sticky="ew", pady=(0, 3))
        action_frame.columnconfigure(1, weight=1)
        self.btn_convert = ttk.Button(
            action_frame,
            text="开始转换",
            style="Primary.TButton",
            command=self.start_convert,
        )
        self.btn_convert.grid(row=0, column=0, sticky="w", padx=(0, 12))
        self.progress = ttk.Progressbar(
            action_frame, mode="determinate", maximum=1, style="Horizontal.TProgressbar"
        )
        self.progress.grid(row=0, column=1, sticky="ew", padx=(0, 10))
        ttk.Label(action_frame, textvariable=self.progress_text, style="Muted.TLabel").grid(
            row=0, column=2, sticky="e", padx=(0, 2)
        )

        log_frame = ttk.LabelFrame(shell, text="运行日志", padding=(8, 7, 8, 8))
        log_frame.grid(row=5, column=0, sticky="nsew", pady=(2, 5))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(1, weight=1)
        log_toolbar = ttk.Frame(log_frame)
        log_toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        ttk.Button(
            log_toolbar, text="清空日志", command=self.clear_log
        ).pack(side="right")
        self.log = scrolledtext.ScrolledText(
            log_frame,
            height=6,
            state="disabled",
            font=("Consolas", 9),
            background="#ffffff",
            foreground="#2f414a",
            insertbackground="#16748a",
            selectbackground="#d5e9ed",
            relief="flat",
            padx=9,
            pady=8,
            wrap="word",
        )
        self.log.grid(row=1, column=0, sticky="nsew")

        footer = ttk.Frame(shell)
        footer.grid(row=6, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.job_status, style="Muted.TLabel").grid(
            row=0, column=0, sticky="w"
        )

    def _sync_option_states(self):
        enabled = self.var_delogo.get()
        state = "normal" if enabled else "disabled"
        self.entry_box.configure(state=state)
        self.spin_crf.configure(state=state)

    def log_msg(self, message):
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _ensure_ffmpeg_async(self):
        """Check for FFmpeg, transparently downloading a bundled build in the
        background if none is available (keeps the UI responsive)."""
        self.ffmpeg_status.set("检查 FFmpeg...")
        self.log_msg("正在检测 FFmpeg ...")

        def worker():
            try:
                path = find_ffmpeg(log_cb=lambda msg: self.events.put(("log", msg)))
                self.events.put(("ffmpeg_ready", path))
            except Exception as exc:  # noqa: BLE001
                self.events.put(("log", f"FFmpeg 检测异常：{exc}"))
                self.events.put(("ffmpeg_ready", None))

        threading.Thread(target=worker, daemon=True).start()

    def add_files(self):
        paths = filedialog.askopenfilenames(
            title="选择 M4S 文件",
            filetypes=[("M4S 文件", "*.m4s"), ("所有文件", "*.*")],
        )
        self._add_paths(paths)

    def add_folder(self):
        folder = filedialog.askdirectory(title="选择包含 M4S 文件的文件夹")
        if not folder:
            return
        try:
            paths = [
                entry.path
                for entry in os.scandir(folder)
                if entry.is_file() and entry.name.lower().endswith(".m4s")
            ]
        except OSError as exc:
            messagebox.showerror("读取失败", str(exc))
            return
        self._add_paths(sorted(paths, key=str.casefold))

    def _add_paths(self, paths):
        for path in paths:
            path = os.path.abspath(path)
            if not path.lower().endswith(".m4s") or not os.path.isfile(path):
                continue
            if path in self.files:
                continue
            self.files.append(path)
            try:
                size = os.path.getsize(path)
            except OSError:
                size = 0
            videos, audios = classify_files([path])
            kind = "音频流" if audios else "视频流" if videos else "未知"
            tags = ("audio",) if audios else ()
            self.tree.insert(
                "",
                "end",
                iid=path,
                values=(
                    os.path.basename(path),
                    os.path.dirname(path),
                    kind,
                    self._format_size(size),
                ),
                tags=tags,
            )
        if self.files and not self.var_outdir.get():
            self.var_outdir.set(os.path.dirname(self.files[0]))
        self._update_file_summary()

    def _update_file_summary(self):
        total_size = 0
        for path in self.files:
            try:
                total_size += os.path.getsize(path)
            except OSError:
                pass
        self.file_summary.set(f"{len(self.files)} 个文件 · {self._format_size(total_size)}")

    @staticmethod
    def _format_size(size):
        if size == 0:
            return "0 B"
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    def clear_files(self):
        self.files.clear()
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._update_file_summary()

    def remove_selected(self):
        for item in self.tree.selection():
            if item in self.files:
                self.files.remove(item)
            self.tree.delete(item)
        self._update_file_summary()

    def choose_outdir(self):
        directory = filedialog.askdirectory(title="选择输出目录")
        if directory:
            self.var_outdir.set(directory)

    def start_convert(self):
        if self.worker_active:
            return
        if not self.files:
            messagebox.showwarning("提示", "请先添加待转换的 M4S 文件。")
            return

        ffmpeg = self.ffmpeg or find_ffmpeg(
            log_cb=lambda msg: self.events.put(("log", msg))
        )
        if not ffmpeg:
            self.ffmpeg_status.set("FFmpeg 未就绪")
            messagebox.showerror(
                "缺少 FFmpeg",
                "正在下载 FFmpeg 或下载失败。请稍候重试，"
                "或手动安装 FFmpeg 并将 ffmpeg.exe 放在程序目录。",
            )
            return
        try:
            version = subprocess.run(
                [ffmpeg, "-version"],
                capture_output=True,
                timeout=10,
                check=False,
            )
            if version.returncode:
                raise OSError("FFmpeg 无法正常运行")
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.ffmpeg_status.set("FFmpeg 不可用")
            messagebox.showerror("FFmpeg 不可用", str(exc))
            return
        self.ffmpeg_status.set("FFmpeg 已就绪")

        try:
            delogo = self.var_delogo.get()
            options = ConversionOptions(
                delogo=delogo,
                delogo_box=(
                    parse_delogo_box(self.var_box.get())
                    if delogo
                    else DEFAULT_DELOGO_BOX
                ),
                crf=int(self.var_crf.get().strip()) if delogo else 18,
                overwrite=self.var_overwrite.get(),
            )
        except ValueError as exc:
            messagebox.showerror("选项无效", str(exc))
            return
        if not 0 <= options.crf <= 51:
            messagebox.showerror("选项无效", "CRF 必须在 0 到 51 之间。")
            return

        output_dir = self.var_outdir.get().strip()
        if not output_dir:
            output_dir = os.path.dirname(self.files[0])
            self.var_outdir.set(output_dir)
        if not os.path.isdir(output_dir):
            messagebox.showerror("目录无效", "输出目录不存在，请重新选择。")
            return

        self.worker_active = True
        self.progress.configure(value=0, maximum=1)
        self.progress_text.set("0 / 0")
        self.job_status.set("正在准备转换...")
        self.btn_convert.configure(state="disabled")
        for button in self.action_buttons:
            button.configure(state="disabled")
        threading.Thread(
            target=self._convert_worker,
            args=(tuple(self.files), output_dir, options, self.var_audio.get(), ffmpeg),
            daemon=True,
        ).start()

    def _convert_worker(self, files, output_dir, options, merge_audio, ffmpeg):
        videos, audios = classify_files(files)
        audio_index = build_audio_index(audios)
        total = len(videos)
        self.events.put(("total", max(total, 1)))
        succeeded = 0
        failed = 0

        for index, video in enumerate(videos, start=1):
            audio = audio_index.get(media_key(video)) if merge_audio else None
            label = os.path.basename(video)
            short_name = label
            if len(short_name) > 48:
                short_name = short_name[:22] + "..." + short_name[-23:]
            if audio:
                label += " + " + os.path.basename(audio)
            self.events.put(("log", f"\n处理：{label}"))
            self.events.put(("status", f"正在处理 {index} / {total}：{short_name}"))
            if merge_audio and not audio:
                self.events.put(("log", "未找到匹配音频流，将仅转换视频。"))
            try:
                result = convert_file(
                    video,
                    output_dir,
                    options,
                    log_cb=lambda message: self.events.put(("log", message)),
                    audio_path=audio,
                    ffmpeg=ffmpeg,
                )
                if result:
                    succeeded += 1
            except ConversionError as exc:
                failed += 1
                self.events.put(("log", f"失败：{exc}"))
            except Exception as exc:
                failed += 1
                self.events.put(("log", f"处理失败：{exc}"))
            self.events.put(("progress", index))

        self.events.put(("done", succeeded, failed, total - succeeded - failed))

    def _on_ffmpeg_ready(self, path):
        self.ffmpeg = path
        if path:
            self.ffmpeg_status.set("FFmpeg 已就绪")
            self.job_status.set("就绪")
        else:
            self.ffmpeg_status.set("FFmpeg 未就绪")
            self.job_status.set("未检测到 FFmpeg")
            self.log_msg("未检测到 FFmpeg，且自动下载失败。请手动下载并放入程序目录。")

    def _poll_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "log":
                    self.log_msg(event[1])
                elif kind == "ffmpeg_ready":
                    self._on_ffmpeg_ready(event[1])
                elif kind == "total":
                    self.progress.configure(maximum=event[1])
                    self.progress_text.set(f"0 / {event[1] if event[1] else 0}")
                elif kind == "progress":
                    self.progress.configure(value=event[1])
                    maximum = int(float(self.progress.cget("maximum")))
                    self.progress_text.set(f"{event[1]} / {maximum}")
                elif kind == "status":
                    self.job_status.set(event[1])
                elif kind == "done":
                    _, succeeded, failed, skipped = event
                    self.worker_active = False
                    self.btn_convert.configure(state="normal")
                    for button in self.action_buttons:
                        button.configure(state="normal")
                    self.job_status.set(
                        f"完成 · 成功 {succeeded} · 跳过 {skipped} · 失败 {failed}"
                    )
                    self.log_msg(
                        f"\n处理结束：成功 {succeeded}，跳过 {skipped}，失败 {failed}"
                    )
                    if failed:
                        messagebox.showwarning(
                            "处理结束",
                            f"成功 {succeeded} 个，跳过 {skipped} 个，失败 {failed} 个。"
                            "详情请查看日志。",
                        )
                    else:
                        messagebox.showinfo(
                            "处理完成",
                            f"成功 {succeeded} 个，跳过 {skipped} 个。",
                        )
        except queue.Empty:
            pass
        self.root.after(100, self._poll_events)

    def _on_close(self):
        if self.worker_active:
            messagebox.showwarning("正在转换", "转换完成后再关闭程序。")
            return
        self.root.destroy()


def main():
    root = tk.Tk()
    M4s2Mp4App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
