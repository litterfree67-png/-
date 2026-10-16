#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Desktop UI for turning Bilibili M4S caches into MP4.

Layout, state and job orchestration. Conversion itself lives in
``m4s2mp4_core``.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

from m4s2mp4_core import (
    DEFAULT_DELOGO_BOX,
    ConversionError,
    ConversionOptions,
    build_audio_index,
    classify_files,
    collect_files,
    convert_file,
    find_ffmpeg,
    media_key,
    parse_delogo_box,
)
from ui_tokens import SPACE, apply_ttk_theme, font, tokens
from ui_widgets import (
    CanvasSlider,
    Chip,
    ResizeGrip,
    RoundedButton,
    Segmented,
    TitleBar,
    Toggle,
    rounded_points,
)

APP_NAME = "m4s2mp42"
APP_TAGLINE = "Bilibili 缓存 → MP4"
SETTINGS_FILE = "m4s2mp42_settings.json"
LOG_LINE_LIMIT = 1200
SIDE_WIDTH = 320

PRESETS = {
    "左上 默认": "8:25:500:95",
    "左上 紧凑": "8:20:340:70",
    "右上 1080P": "1420:25:500:95",
    "右上 720P": "780:20:340:70",
    "左下角": "8:980:420:80",
}

ROW_STATES = {
    "pending": ("等待", "pending"),
    "running": ("转换中", "running"),
    "done": ("完成", "done"),
    "failed": ("失败", "failed"),
    "skipped": ("跳过", "skipped"),
}

ROLE_TOKEN = {
    "primary": "text",
    "secondary": "text_secondary",
    "muted": "text_muted",
    "inverse": "text_inverse",
}


def user_config_dir():
    override = os.environ.get("M4S2MP42_CONFIG_DIR")
    if override:
        return os.path.abspath(os.path.expanduser(override))
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, APP_NAME)
    base = os.environ.get("XDG_CONFIG_HOME")
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, APP_NAME)


class App:
    def __init__(self, root):
        self.root = root
        self.theme_mode = "light"
        self._t = tokens("light")
        self._themed = []      # (widget, token_key) frames + labels
        self._cards = []       # 1px-bordered surfaces
        self._custom = []      # widgets with apply_theme(t)

        self.files = []
        self.events = queue.Queue()
        self.worker_running = False
        self.cancel_requested = False
        self.ffmpeg_path = None
        self.last_output_dir = ""
        self._maximized = False
        self._restore_geometry = ""

        self.settings = self._load_settings()

        self._configure_window()
        self.style = ttk.Style(root)
        self._build_shell()
        self._apply_theme(self.settings.get("theme", "light"))
        self._restore_settings()
        self.root.after(90, self._poll_events)
        self._detect_ffmpeg_async()
        self._update_empty_state()

    # ------------------------------------------------------------------
    # Window
    # ------------------------------------------------------------------
    def _configure_window(self):
        root = self.root
        root.title(APP_NAME)
        root.overrideredirect(True)
        root.minsize(980, 706)
        width, height = 1120, 844
        x = max(0, (root.winfo_screenwidth() - width) // 2)
        y = max(0, (root.winfo_screenheight() - height) // 3)
        root.geometry(f"{width}x{height}+{x}+{y}")
        root.configure(background=self._t["border"])
        root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # Small widget factories (all register for re-theming)
    # ------------------------------------------------------------------
    def _frame(self, master, token="canvas", **kwargs):
        frame = tk.Frame(master, **kwargs)
        self._themed.append((frame, token))
        return frame

    def _card(self, master, token="surface", padx=SPACE["lg"],
              pady=SPACE["md"]):
        card = tk.Frame(master, highlightthickness=1, padx=padx, pady=pady)
        self._themed.append((card, token))
        self._cards.append(card)
        return card

    def _label(self, master, text, key="body", token="surface",
               role="primary", **kwargs):
        label = tk.Label(master, text=text, font=font(key), **kwargs)
        label._role = role
        self._themed.append((label, token))
        return label

    def _section_label(self, master, text):
        label = self._label(master, text, key="caption", token="surface",
                            role="muted", anchor="w")
        label.configure(font=font("caption", "bold"))
        return label

    def _separator(self, master):
        sep = tk.Frame(master, height=1)
        self._themed.append((sep, "border"))
        return sep

    # ------------------------------------------------------------------
    # Shell
    # ------------------------------------------------------------------
    def _build_shell(self):
        outer = tk.Frame(self.root, highlightthickness=1)
        self.outer = outer
        outer.pack(fill="both", expand=True)

        self.titlebar = TitleBar(
            outer, title=APP_NAME, subtitle=APP_TAGLINE,
            on_minimize=self._minimize,
            on_toggle_max=self._toggle_maximize,
            on_close=self._on_close)
        self.titlebar.pack(fill="x", side="top")
        self.titlebar.add_action("theme", self.toggle_theme, padx=SPACE["xs"])
        self._custom.append(self.titlebar)

        # Pack order matters (cavity model): fixed strips first, expanding
        # body last, so nothing gets squeezed out.
        footer = self._frame(outer, "surface_sunken", height=36)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)

        body = self._frame(outer)
        body.pack(fill="both", expand=True)
        self._build_settings(body)   # rail first: fixed width, right side
        self._build_main(body)
        self._build_statusbar(footer)

        grip_host = self._frame(footer, "surface_sunken")
        grip_host.place(relx=1.0, rely=1.0, anchor="se")
        self.grip = ResizeGrip(grip_host)
        self.grip.pack(side="bottom", anchor="e")
        self._custom.append(self.grip)

        # Global shortcuts
        bindings = (
            ("<Control-o>", lambda _e: self.add_files()),
            ("<Control-Shift-O>", lambda _e: self.add_folder()),
            ("<Control-Return>", lambda _e: self.start()),
            ("<Control-l>", lambda _e: self.clear_log()),
            ("<Control-d>", lambda _e: self.toggle_theme()),
            ("<Control-v>", lambda _e: self.paste_paths()),
        )
        for sequence, handler in bindings:
            self.root.bind(sequence, handler)

    # ------------------------------------------------------------------
    # Main column
    # ------------------------------------------------------------------
    def _build_main(self, body):
        main = self._frame(body)
        main.pack(side="left", fill="both", expand=True,
                  padx=(SPACE["lg"], SPACE["md"]),
                  pady=(SPACE["lg"], SPACE["md"]))
        main.columnconfigure(0, weight=1)
        main.rowconfigure(1, weight=3)
        main.rowconfigure(4, weight=2)

        self._build_hero(main)
        self._build_queue(main)
        self._build_progress(main)
        self._build_log(main)

    def _build_hero(self, main):
        hero = self._card(main, pady=SPACE["lg"])
        hero.grid(row=0, column=0, sticky="ew", pady=(0, SPACE["md"]))

        # Pack the action buttons first (fixed), then let the text column
        # take the rest — this can never overlap at any window width.
        actions = self._frame(hero, "surface")
        actions.pack(side="right", padx=(SPACE["md"], 0))
        self.btn_add_files = RoundedButton(actions, "添加文件", size="lg",
                                           variant="primary",
                                           command=self.add_files)
        self.btn_add_files.pack(side="left", padx=(0, SPACE["sm"]))
        self.btn_add_folder = RoundedButton(actions, "添加文件夹", size="lg",
                                            command=self.add_folder)
        self.btn_add_folder.pack(side="left")
        self._custom += [self.btn_add_files, self.btn_add_folder]

        texts = self._frame(hero, "surface")
        texts.pack(side="left", fill="x", expand=True)
        self.label_hero_title = self._label(
            texts, "把缓存的 m4s 冲洗成 mp4", key="display", anchor="w",
            justify="left")
        self.label_hero_title.pack(anchor="w")
        self.label_hero_sub = self._label(
            texts,
            "自动剥离文件头的垃圾数据；可选去水印重编码、无损快速封装，或合并匹配的音频流。",
            key="body", role="secondary", anchor="w", justify="left")
        self.label_hero_sub.pack(anchor="w", pady=(SPACE["xs"], 0))

        def _reflow(event):
            width = max(260, event.width - 6)
            for label in (self.label_hero_title, self.label_hero_sub):
                label.configure(wraplength=width)

        texts.bind("<Configure>", _reflow)

    def _build_queue(self, main):
        card = self._card(main)
        card.grid(row=1, column=0, sticky="nsew", pady=(0, SPACE["md"]))
        card.columnconfigure(0, weight=1)
        card.rowconfigure(1, weight=1)

        head = self._frame(card, "surface")
        head.grid(row=0, column=0, sticky="ew", pady=(0, SPACE["sm"]))
        self._section_label(head, "文件队列")
        self.section_file_label = None
        self.chip_files = Chip(head, "0 个文件", tone="neutral")
        self.chip_files.pack(side="left", padx=(SPACE["sm"], 0))
        tools = self._frame(head, "surface")
        tools.pack(side="right")
        self.btn_remove = RoundedButton(tools, "移除选中", size="sm",
                                        variant="ghost",
                                        command=self.remove_selected)
        self.btn_remove.pack(side="left", padx=(0, SPACE["xs"]))
        self.btn_clear = RoundedButton(tools, "清空列表", size="sm",
                                       variant="ghost", command=self.clear_files)
        self.btn_clear.pack(side="left")
        self._custom += [self.chip_files, self.btn_remove, self.btn_clear]

        host = self._frame(card, "surface")
        host.grid(row=1, column=0, sticky="nsew")
        host.columnconfigure(0, weight=1)
        host.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            host, columns=("name", "status", "kind", "size", "folder"),
            show="headings", selectmode="extended", style="Queue.Treeview")
        self.tree.heading("name", text="文件")
        self.tree.heading("status", text="状态")
        self.tree.heading("kind", text="轨道")
        self.tree.heading("size", text="大小")
        self.tree.heading("folder", text="所在目录")
        self.tree.column("name", width=300, minwidth=180, stretch=True)
        self.tree.column("status", width=84, minwidth=74, anchor="center",
                         stretch=False)
        self.tree.column("kind", width=72, minwidth=64, anchor="center",
                         stretch=False)
        self.tree.column("size", width=92, minwidth=80, anchor="e",
                         stretch=False)
        self.tree.column("folder", width=250, minwidth=120, stretch=True)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(host, command=self.tree.yview,
                               style="Vertical.TScrollbar")
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<Delete>", lambda _e: self.remove_selected())

        self.empty_state = self._build_empty_state(host)
        self.empty_state.place(relx=0.5, rely=0.5, anchor="center")

    def _build_empty_state(self, master):
        host = self._frame(master, "surface")
        self.empty_mark = tk.Canvas(host, width=56, height=56,
                                    highlightthickness=0, bd=0)
        self.empty_mark.pack()
        self._label(host, "还没有添加文件", key="title", anchor="center").pack(
            pady=(SPACE["sm"], 2))
        self._label(host, "添加 .m4s 文件，或直接选择整个缓存文件夹",
                    key="body", role="secondary", anchor="center").pack()
        self.btn_empty_add = RoundedButton(host, "添加文件", size="md",
                                           variant="primary",
                                           command=self.add_files)
        self.btn_empty_add.pack(pady=(SPACE["md"], 0))
        self._custom.append(self.btn_empty_add)
        return host

    def _build_progress(self, main):
        row = self._frame(main)
        row.grid(row=2, column=0, sticky="ew", pady=(0, SPACE["xs"]))
        self.progress = ttk.Progressbar(row, mode="determinate", maximum=1,
                                        style="Accent.Horizontal.TProgressbar")
        self.progress.pack(side="left", fill="x", expand=True)
        self.label_progress = self._label(row, "0 / 0", key="label",
                                          role="secondary", width=9, anchor="e")
        self.label_progress.pack(side="left", padx=(SPACE["sm"], 0))
        self.label_now = self._label(main, "尚未开始", key="body",
                                     role="secondary", anchor="w")
        self.label_now.grid(row=3, column=0, sticky="ew")

    def _build_log(self, main):
        card = self._card(main)
        card.grid(row=4, column=0, sticky="nsew", pady=(SPACE["sm"], 0))
        card.rowconfigure(1, weight=1)
        card.columnconfigure(0, weight=1)

        head = self._frame(card, "surface")
        head.grid(row=0, column=0, sticky="ew", pady=(0, SPACE["xs"]))
        self._section_label(head, "运行日志")
        self.btn_clear_log = RoundedButton(head, "清空", size="sm",
                                           variant="ghost", command=self.clear_log)
        self.btn_clear_log.pack(side="right")
        self._custom.append(self.btn_clear_log)

        self.log = tk.Text(card, height=5, wrap="word", relief="flat",
                           borderwidth=0, highlightthickness=0,
                           padx=SPACE["md"], pady=SPACE["sm"],
                           font=font("code", mono=True), insertwidth=2,
                           spacing1=2, spacing3=2, state="disabled")
        self.log.grid(row=1, column=0, sticky="nsew")
        log_scroll = ttk.Scrollbar(card, command=self.log.yview,
                                   style="Vertical.TScrollbar")
        log_scroll.grid(row=1, column=1, sticky="ns")
        self.log.configure(yscrollcommand=log_scroll.set)

    # ------------------------------------------------------------------
    # Settings rail
    # ------------------------------------------------------------------
    def _build_settings(self, body):
        side = tk.Frame(body, width=SIDE_WIDTH, highlightthickness=1,
                        padx=SPACE["lg"], pady=SPACE["md"])
        self._themed.append((side, "surface"))
        self._cards.append(side)
        side.pack(side="right", fill="y", padx=(SPACE["md"], SPACE["lg"]),
                  pady=(SPACE["md"], SPACE["sm"]))
        body.update_idletasks()  # reserve the rail before main expands
        side.pack_propagate(False)
        rail_width = SIDE_WIDTH - SPACE["lg"] * 2 - 2

        self._label(side, "冲洗参数", key="title", anchor="w").pack(anchor="w")

        self._section_label(side, "处理模式").pack(anchor="w")
        self.var_mode = tk.StringVar(value="delogo")
        self.seg_mode = Segmented(
            side, [("delogo", "去水印重编码"), ("copy", "无损快速封装")],
            self.var_mode, command=self._sync_options, width=rail_width)
        self.seg_mode.pack(anchor="w", pady=(SPACE["xs"], SPACE["xs"]))
        self._custom.append(self.seg_mode)
        self.label_mode_hint = self._label(side, "", key="caption",
                                           role="secondary", anchor="w",
                                           wraplength=rail_width, justify="left")
        self.label_mode_hint.pack(anchor="w", pady=(0, SPACE["sm"]))

        # Watermark region (delogo only)
        self._section_label(side, "水印区域  X:Y:W:H").pack(anchor="w")
        self.var_box = tk.StringVar(value="8:25:500:95")
        self.entry_box = ttk.Entry(side, textvariable=self.var_box,
                                   style="Mono.TEntry")
        self.entry_box.pack(fill="x", pady=(SPACE["xs"], SPACE["xs"]))
        self.var_preset = tk.StringVar(value="左上 默认")
        self.combo_preset = ttk.Combobox(side, values=list(PRESETS),
                                         textvariable=self.var_preset,
                                         state="readonly")
        self.combo_preset.pack(fill="x")
        self.combo_preset.bind("<<ComboboxSelected>>", self._apply_preset)
        self.label_box_hint = self._label(side, "", key="caption",
                                          role="secondary", anchor="w")
        self.label_box_hint.pack(anchor="w", pady=(0, SPACE["md"]))

        # Quality (delogo only)
        quality_head = self._frame(side, "surface")
        quality_head.pack(fill="x")
        self._section_label(quality_head, "画质 CRF")
        self.label_crf = self._label(quality_head, "18", key="body",
                                     role="secondary", anchor="e")
        self.label_crf.pack(side="right")
        self.var_crf = tk.IntVar(value=18)
        self.slider_crf = CanvasSlider(side, from_=0, to=51,
                                       variable=self.var_crf,
                                       command=self._on_crf_change,
                                       width=rail_width)
        self.slider_crf.pack(anchor="w", pady=(SPACE["xs"], 0))
        self._custom.append(self.slider_crf)
        legend = self._frame(side, "surface")
        legend.pack(fill="x", pady=(0, SPACE["md"]))
        self._label(legend, "0 · 体积大", key="caption",
                    role="muted").pack(side="left")
        self._label(legend, "51 · 体积小", key="caption",
                    role="muted").pack(side="right")

        # Switches
        self._separator(side).pack(fill="x", pady=(0, SPACE["md"]))
        self.var_audio = tk.BooleanVar(value=False)
        self.var_overwrite = tk.BooleanVar(value=False)
        self.var_recursive = tk.BooleanVar(value=True)
        self._switch_row(side, "合并匹配音频", "同目录的 -.30280 音轨自动配对",
                         self.var_audio).pack(fill="x", pady=(0, SPACE["xs"]))
        self._switch_row(side, "覆盖已有 MP4", "关闭时同名文件会被跳过",
                         self.var_overwrite).pack(fill="x",
                                                  pady=(0, SPACE["xs"]))
        self._switch_row(side, "包含子文件夹", "添加文件夹时递归查找",
                         self.var_recursive).pack(fill="x",
                                                  pady=(0, SPACE["sm"]))

        # Output
        self._separator(side).pack(fill="x", pady=(0, SPACE["sm"]))
        self._section_label(side, "输出目录").pack(anchor="w")
        self.var_outdir = tk.StringVar()
        self.entry_outdir = ttk.Entry(side, textvariable=self.var_outdir,
                                      width=24)
        self.entry_outdir.pack(fill="x", pady=(SPACE["xs"], SPACE["xs"]))
        outdir_actions = self._frame(side, "surface")
        outdir_actions.pack(fill="x")
        self.btn_browse = RoundedButton(outdir_actions, "浏览", size="sm",
                                        command=self.choose_outdir)
        self.btn_browse.pack(side="left", padx=(0, SPACE["xs"]))
        self.btn_open_out = RoundedButton(outdir_actions, "打开目录", size="sm",
                                          variant="ghost",
                                          command=self.open_outdir)
        self.btn_open_out.pack(side="left")
        self._custom += [self.btn_browse, self.btn_open_out]

        # Engine + primary actions
        spacer = self._frame(side, "surface")
        spacer.pack(fill="y", expand=True)
        self._separator(side).pack(fill="x", pady=(0, SPACE["sm"]))
        engine_row = self._frame(side, "surface")
        engine_row.pack(fill="x", pady=(0, SPACE["sm"]))
        self._section_label(engine_row, "转换引擎")
        self.chip_engine = Chip(engine_row, "检测中", tone="neutral")
        self.chip_engine.pack(side="right")
        self._custom.append(self.chip_engine)

        self.btn_start = RoundedButton(side, "开始转换", size="wide",
                                       variant="primary", width=rail_width,
                                       command=self.start)
        self.btn_start.pack(anchor="w")
        self.btn_cancel = RoundedButton(side, "停止队列", size="md",
                                        width=rail_width,
                                        command=self.request_cancel)
        self.btn_cancel.pack(anchor="w", pady=(SPACE["xs"], 0))
        self._custom += [self.btn_start, self.btn_cancel]

    def _switch_row(self, master, title, hint, variable):
        row = self._frame(master, "surface")
        texts = self._frame(row, "surface")
        texts.pack(side="left")
        self._label(texts, title, key="body", anchor="w").pack(anchor="w")
        self._label(texts, hint, key="caption", role="muted",
                    anchor="w").pack(anchor="w")
        toggle = Toggle(row, variable=variable)
        toggle.pack(side="right")
        self._custom.append(toggle)
        return row

    def _build_statusbar(self, footer):
        left = self._frame(footer, "surface_sunken")
        left.pack(side="left", padx=SPACE["lg"])
        self.label_status = self._label(left, "就绪", key="body",
                                        token="surface_sunken",
                                        role="secondary", anchor="w")
        self.label_status.pack(side="left")

        right = self._frame(footer, "surface_sunken")
        right.pack(side="right", padx=(0, SPACE["3xl"]))
        self.chip_ok = Chip(right, "成功 0", tone="success")
        self.chip_skip = Chip(right, "跳过 0", tone="warning")
        self.chip_fail = Chip(right, "失败 0", tone="danger")
        self.chip_fail.pack(side="right", padx=(SPACE["xs"], 0))
        self.chip_skip.pack(side="right", padx=(SPACE["xs"], 0))
        self.chip_ok.pack(side="right", padx=(SPACE["xs"], 0))
        self._custom += [self.chip_ok, self.chip_skip, self.chip_fail]

    # ------------------------------------------------------------------
    # Theming
    # ------------------------------------------------------------------
    def _apply_theme(self, mode):
        self.theme_mode = mode
        self._t = tokens(mode)
        t = self._t
        apply_ttk_theme(self.style, t)
        self.root.configure(background=t["border_strong"])
        self.outer.configure(highlightbackground=t["border_strong"])

        for widget, token_key in self._themed:
            try:
                widget.configure(background=t[token_key])
                if isinstance(widget, tk.Label):
                    role = getattr(widget, "_role", "primary")
                    widget.configure(foreground=t[ROLE_TOKEN[role]])
            except tk.TclError:
                continue
        for card in self._cards:
            card.configure(highlightbackground=t["border"])

        self.log.configure(background=t["surface_sunken"], foreground=t["text"],
                           insertbackground=t["accent"],
                           selectbackground=t["accent_soft"],
                           selectforeground=t["accent_soft_text"])
        self._draw_empty_mark()
        self.empty_mark.configure(background=t["surface"])
        self._refresh_tags()

        root = self.root
        root.option_add("*TCombobox*Listbox.background", t["surface"])
        root.option_add("*TCombobox*Listbox.foreground", t["text"])
        root.option_add("*TCombobox*Listbox.selectBackground", t["accent_soft"])
        root.option_add("*TCombobox*Listbox.selectForeground",
                        t["accent_soft_text"])

        for widget in self._custom:
            widget.apply_theme(t)

    def toggle_theme(self):
        self._apply_theme("dark" if self.theme_mode == "light" else "light")
        self.settings["theme"] = self.theme_mode
        self._save_settings()

    def _refresh_tags(self):
        tints = {
            "pending": self._t["surface"],
            "running": self._t["info_soft"],
            "done": self._t["success_soft"],
            "failed": self._t["danger_soft"],
            "skipped": self._t["warning_soft"],
        }
        for state, tint in tints.items():
            self.tree.tag_configure(state, background=tint)
        self.tree.tag_configure("audio", foreground=self._t["text_secondary"])

    def _draw_empty_mark(self):
        if not getattr(self, "empty_mark", None):
            return
        self.empty_mark.delete("all")
        t = self._t
        self.empty_mark.create_polygon(
            rounded_points(2, 2, 52, 52, 10), fill=t["surface_sunken"],
            outline=t["border"], smooth=True)
        self.empty_mark.create_rectangle(14, 14, 42, 42, outline=t["accent"],
                                         fill="", width=1, dash=(3, 2))
        self.empty_mark.create_line(14, 28, 42, 28, fill=t["text_muted"],
                                    dash=(2, 3))

    # ------------------------------------------------------------------
    # Window controls
    # ------------------------------------------------------------------
    def _minimize(self):
        self.root.update_idletasks()
        self.root.overrideredirect(False)
        self.root.iconify()
        self.root.bind("<Map>", self._restore_chrome)

    def _restore_chrome(self, _event=None):
        self.root.after(20, lambda: self.root.overrideredirect(True))
        self.root.unbind("<Map>")

    def _toggle_maximize(self):
        if self._maximized:
            self.root.geometry(self._restore_geometry)
            self._maximized = False
            return
        self._restore_geometry = self.root.geometry()
        width = self.root.winfo_screenwidth()
        height = self.root.winfo_screenheight() - 40
        self.root.geometry(f"{width}x{height}+0+0")
        self._maximized = True

    def _on_close(self):
        if self.worker_running:
            if not messagebox.askyesno(
                    "正在转换",
                    "转换任务仍在运行，确定要退出吗？\n"
                    "当前文件会被中断，已生成的文件不受影响。"):
                return
        self._save_settings()
        self.root.destroy()

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------
    def _settings_path(self):
        return os.path.join(user_config_dir(), SETTINGS_FILE)

    def _load_settings(self):
        defaults = {"theme": "light", "mode": "delogo", "crf": 18,
                    "box": "8:25:500:95", "audio": False, "overwrite": False,
                    "recursive": True}
        try:
            with open(self._settings_path(), "r", encoding="utf-8") as handle:
                stored = json.load(handle)
            if isinstance(stored, dict):
                defaults.update(stored)
        except (OSError, ValueError):
            pass
        return defaults

    def _save_settings(self):
        data = {
            "theme": self.theme_mode,
            "mode": self.var_mode.get(),
            "crf": int(self.var_crf.get()),
            "box": self.var_box.get(),
            "audio": bool(self.var_audio.get()),
            "overwrite": bool(self.var_overwrite.get()),
            "recursive": bool(self.var_recursive.get()),
        }
        try:
            path = self._settings_path()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def _restore_settings(self):
        mode = self.settings.get("mode", "delogo")
        if mode not in {"copy", "delogo"}:
            mode = "delogo"
        try:
            crf = int(self.settings.get("crf", 18))
        except (TypeError, ValueError):
            crf = 18
        crf = min(51, max(0, crf))
        box = str(self.settings.get("box", "8:25:500:95"))
        try:
            parse_delogo_box(box)
        except ValueError:
            box = "8:25:500:95"

        self.var_mode.set(mode)
        self.var_crf.set(crf)
        self.var_box.set(box)
        self.var_audio.set(bool(self.settings.get("audio", False)))
        self.var_overwrite.set(bool(self.settings.get("overwrite", False)))
        self.var_recursive.set(bool(self.settings.get("recursive", True)))
        self._on_crf_change()
        box = self.var_box.get()
        matched = next((label for label, value in PRESETS.items()
                        if value == box), "")
        self.var_preset.set(matched)
        self._sync_options()

    # ------------------------------------------------------------------
    # File queue
    # ------------------------------------------------------------------
    def add_files(self):
        paths = filedialog.askopenfilenames(
            title="选择 M4S 文件",
            filetypes=[("M4S 文件", "*.m4s"), ("所有文件", "*.*")])
        self._add_paths(paths)

    def add_folder(self):
        folder = filedialog.askdirectory(title="选择包含 M4S 文件的文件夹")
        if not folder:
            return
        try:
            paths = collect_files([folder], recursive=self.var_recursive.get())
        except OSError as exc:
            messagebox.showerror("读取失败", str(exc))
            return
        self._add_paths(paths)

    def paste_paths(self):
        try:
            raw = self.root.clipboard_get()
        except tk.TclError:
            return "break"
        paths = [line.strip().strip('"')
                 for line in raw.splitlines() if line.strip()]
        if paths:
            self._add_paths(paths)
        return "break"

    def _add_paths(self, paths):
        if self.worker_running:
            return 0
        added = 0
        for path in paths:
            if not path:
                continue
            path = os.path.abspath(path)
            if os.path.isdir(path):
                try:
                    nested = collect_files([path],
                                           recursive=self.var_recursive.get())
                except OSError:
                    nested = []
                added += self._add_paths(nested)
                continue
            if path.lower().endswith(".m4s") and os.path.isfile(path) \
                    and path not in self.files:
                self._insert_row(path)
                added += 1
        if added:
            self._update_summary()
            self._update_empty_state()
            self._set_status(f"已添加 {added} 个文件")
        return added

    def _insert_row(self, path):
        self.files.append(path)
        videos, audios = classify_files([path])
        kind = "音频" if audios else ("视频" if videos else "未知")
        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0
        tags = ("pending",) + (("audio",) if audios else ())
        self.tree.insert(
            "", "end", iid=path, tags=tags,
            values=(os.path.basename(path), ROW_STATES["pending"][0], kind,
                    self._format_size(size), os.path.dirname(path)))
        if not self.var_outdir.get():
            self.var_outdir.set(os.path.dirname(path))

    def clear_files(self):
        if self.worker_running:
            return
        self.files.clear()
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._update_summary()
        self._update_empty_state()

    def remove_selected(self):
        if self.worker_running:
            return
        for item in self.tree.selection():
            if item in self.files:
                self.files.remove(item)
            self.tree.delete(item)
        self._update_summary()
        self._update_empty_state()

    def _update_summary(self):
        total = 0
        for path in self.files:
            try:
                total += os.path.getsize(path)
            except OSError:
                pass
        count = len(self.files)
        self.chip_files.set(f"{count} 个文件 · {self._format_size(total)}",
                            "accent" if count else "neutral")

    def _update_empty_state(self):
        if self.tree.get_children():
            self.empty_state.place_forget()
        else:
            self.empty_state.place(relx=0.5, rely=0.5, anchor="center")
            self._draw_empty_mark()

    @staticmethod
    def _format_size(size):
        if size == 0:
            return "0 B"
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.2f} TB"

    # ------------------------------------------------------------------
    # Options
    # ------------------------------------------------------------------
    def _sync_options(self):
        delogo = self.var_mode.get() == "delogo"
        self.entry_box.configure(state="normal" if delogo else "disabled")
        self.combo_preset.configure(state="readonly" if delogo else "disabled")
        self.slider_crf.configure_state("normal" if delogo else "disabled")
        self.label_mode_hint.configure(
            text="逐帧重编码并用插值覆盖水印区域，速度较慢但画面干净。"
            if delogo else
            "直接复用原始编码流，秒速完成且不损失画质，但无法去水印。")
        self._validate_box(live=True)
        self._save_settings()

    def _apply_preset(self, _event=None):
        value = PRESETS.get(self.var_preset.get())
        if value:
            self.var_box.set(value)
        self._validate_box(live=True)

    def _on_crf_change(self, _event=None):
        value = int(float(self.var_crf.get()))
        self.var_crf.set(value)
        quality = ("接近无损" if value <= 18 else "高质量" if value <= 23
                   else "标准" if value <= 28 else "高压缩")
        self.label_crf.configure(text=f"{value} · {quality}")
        self._save_settings()

    def _validate_box(self, live=False):
        raw = self.var_box.get().strip()
        try:
            values = [int(part.strip()) for part in raw.split(":")]
        except ValueError:
            self._set_hint(False, "格式应为 x:y:w:h，例如 8:25:500:95")
            return False
        ok = (len(values) == 4 and values[2] > 0 and values[3] > 0
              and values[0] >= 0 and values[1] >= 0)
        self._set_hint(ok, "左上角坐标与宽高，单位像素" if ok else "宽高必须大于 0")
        if not ok and not live:
            messagebox.showerror("水印区域无效",
                                 "请使用 x:y:w:h 格式，四个非负整数，且宽高大于 0。")
        return ok

    def _set_hint(self, ok, text):
        self.label_box_hint.configure(
            text=text,
            foreground=self._t["text_secondary"] if ok else self._t["danger"])

    def choose_outdir(self):
        directory = filedialog.askdirectory(title="选择输出目录")
        if directory:
            self.var_outdir.set(directory)
            self._save_settings()

    def open_outdir(self):
        directory = self.var_outdir.get().strip() or self.last_output_dir
        if not directory:
            messagebox.showinfo("输出目录", "还没有输出目录，先添加文件吧。")
            return
        if not os.path.isdir(directory):
            messagebox.showerror("目录无效", f"目录不存在：{directory}")
            return
        try:
            if os.name == "nt":
                os.startfile(directory)  # user-initiated, safe here
            elif sys.platform == "darwin":
                subprocess.Popen(["open", directory])
            else:
                subprocess.Popen(["xdg-open", directory])
        except OSError as exc:
            messagebox.showerror("打开失败", str(exc))

    # ------------------------------------------------------------------
    # Engine
    # ------------------------------------------------------------------
    def _detect_ffmpeg_async(self):
        def worker():
            try:
                path = find_ffmpeg(log_cb=lambda m: self.events.put(("log", m)))
            except Exception as exc:  # noqa: BLE001 - never break startup
                self.events.put(("log", f"FFmpeg 检测异常：{exc}"))
                path = None
            self.events.put(("ffmpeg", path))

        threading.Thread(target=worker, daemon=True).start()

    def _on_ffmpeg_ready(self, path):
        self.ffmpeg_path = path
        if path:
            self.chip_engine.set("FFmpeg 就绪", "success")
            self._set_status("就绪 · 拖拽或添加 m4s 文件开始")
            self._log(f"FFmpeg：{path}")
        else:
            self.chip_engine.set("FFmpeg 缺失", "danger")
            self._set_status("未检测到 FFmpeg")
            self._log("未检测到 FFmpeg，且自动下载失败。请手动安装 FFmpeg，"
                      "或将 ffmpeg.exe 放入程序目录。")

    # ------------------------------------------------------------------
    # Conversion
    # ------------------------------------------------------------------
    def start(self):
        if self.worker_running:
            return
        if not self.files:
            messagebox.showwarning("提示", "请先添加待转换的 M4S 文件。")
            return

        ffmpeg = self.ffmpeg_path or find_ffmpeg(
            log_cb=lambda m: self.events.put(("log", m)))
        if not ffmpeg:
            self.chip_engine.set("FFmpeg 缺失", "danger")
            messagebox.showerror(
                "缺少 FFmpeg",
                "还没有可用的 FFmpeg。首次运行会自动尝试下载（约 110 MB），"
                "也可以手动安装并把 ffmpeg.exe 放到程序目录。")
            return
        self.ffmpeg_path = ffmpeg
        try:
            probe = subprocess.run([ffmpeg, "-version"], capture_output=True,
                                   timeout=10, check=False)
            if probe.returncode:
                raise OSError("FFmpeg 无法正常运行")
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.chip_engine.set("FFmpeg 异常", "danger")
            messagebox.showerror("FFmpeg 不可用", str(exc))
            return
        self.chip_engine.set("FFmpeg 就绪", "success")

        delogo = self.var_mode.get() == "delogo"
        if delogo and not self._validate_box():
            return
        try:
            options = ConversionOptions(
                delogo=delogo,
                delogo_box=(parse_delogo_box(self.var_box.get()) if delogo
                            else DEFAULT_DELOGO_BOX),
                crf=int(self.var_crf.get()) if delogo else 18,
                overwrite=self.var_overwrite.get())
        except ValueError as exc:
            messagebox.showerror("参数无效", str(exc))
            return

        output_dir = self.var_outdir.get().strip()
        if not output_dir:
            output_dir = os.path.dirname(self.files[0])
            self.var_outdir.set(output_dir)
        if not os.path.isdir(output_dir):
            messagebox.showerror("目录无效", "输出目录不存在，请重新选择。")
            return
        self.last_output_dir = output_dir

        for path in self.files:
            self._set_row_state(path, "pending")

        self.worker_running = True
        self.cancel_requested = False
        self.btn_start.set_text("正在转换…")
        self.btn_start.configure_state("disabled")
        for button in (self.btn_add_files, self.btn_add_folder,
                       self.btn_remove, self.btn_clear, self.btn_empty_add):
            button.configure_state("disabled")
        self.btn_cancel.configure_state("normal")
        self.progress.configure(value=0, maximum=1)
        self.label_progress.configure(text="0 / 0")
        self.chip_ok.set("成功 0", "success")
        self.chip_skip.set("跳过 0", "warning")
        self.chip_fail.set("失败 0", "danger")
        self._set_status("正在准备…")
        self._save_settings()

        threading.Thread(
            target=self._worker,
            args=(tuple(self.files), output_dir, options,
                  self.var_audio.get(), ffmpeg),
            daemon=True).start()

    def request_cancel(self):
        if not self.worker_running:
            return
        self.cancel_requested = True
        self._set_status("正在停止，等待当前文件处理完成…")
        self._log("收到停止请求，完成当前文件后结束。")
        self.btn_cancel.configure_state("disabled")

    def _worker(self, files, output_dir, options, merge_audio, ffmpeg):
        videos, audios = classify_files(files)
        audio_index = build_audio_index(audios)
        total = len(videos)
        self.events.put(("queue-size", max(total, 1)))
        succeeded = failed = skipped = 0

        for index, video in enumerate(videos, start=1):
            if self.cancel_requested:
                self.events.put(("log", "已停止，剩余文件未处理。"))
                break
            audio = audio_index.get(media_key(video)) if merge_audio else None
            name = os.path.basename(video)
            self.events.put(("row-state", video, "running"))
            self.events.put(("status", f"正在处理 {index} / {total} · {name}"))
            if merge_audio and not audio:
                self.events.put(("log", f"未找到匹配音频流：{name}"))
            try:
                result = convert_file(
                    video, output_dir, options,
                    log_cb=lambda m: self.events.put(("log", m)),
                    audio_path=audio, ffmpeg=ffmpeg)
                if result:
                    succeeded += 1
                    self.events.put(("row-state", video, "done"))
                else:
                    skipped += 1
                    self.events.put(("row-state", video, "skipped"))
            except ConversionError as exc:
                failed += 1
                self.events.put(("log", f"失败：{exc}"))
                self.events.put(("row-state", video, "failed"))
            except Exception as exc:  # noqa: BLE001 - keep the queue alive
                failed += 1
                self.events.put(("log", f"处理失败：{exc}"))
                self.events.put(("row-state", video, "failed"))
            self.events.put(("progress", index))
            self.events.put(("counts", succeeded, skipped, failed))

        self.events.put(("finish", succeeded, skipped, failed,
                         self.cancel_requested))

    def _finish(self, succeeded, skipped, failed, cancelled):
        self.worker_running = False
        self.cancel_requested = False
        for button in (self.btn_start, self.btn_add_files, self.btn_add_folder,
                       self.btn_remove, self.btn_clear, self.btn_empty_add):
            button.configure_state("normal")
        self.btn_cancel.configure_state("disabled")
        self.btn_start.set_text("再转一次" if not cancelled else "开始转换")
        suffix = "（已停止）" if cancelled else ""
        self._set_status(f"完成{suffix} · 成功 {succeeded} · 跳过 {skipped}"
                         f" · 失败 {failed}")
        self._log(f"\n处理结束{suffix}：成功 {succeeded}，跳过 {skipped}，"
                  f"失败 {failed}")
        if failed:
            messagebox.showwarning(
                "处理结束",
                f"成功 {succeeded} 个，跳过 {skipped} 个，失败 {failed} 个。\n"
                "详情请查看运行日志。")
        elif not cancelled:
            messagebox.showinfo("处理完成",
                                f"成功 {succeeded} 个，跳过 {skipped} 个。")

    # ------------------------------------------------------------------
    # Event pump
    # ------------------------------------------------------------------
    def _poll_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "log":
                    self._log(event[1])
                elif kind == "ffmpeg":
                    self._on_ffmpeg_ready(event[1])
                elif kind == "row-state":
                    self._set_row_state(event[1], event[2])
                elif kind == "queue-size":
                    self.progress.configure(maximum=max(event[1], 1))
                    self.label_progress.configure(text=f"0 / {event[1]}")
                elif kind == "progress":
                    maximum = int(float(self.progress.cget("maximum")))
                    self.progress.configure(value=min(event[1], maximum))
                    self.label_progress.configure(text=f"{event[1]} / {maximum}")
                elif kind == "counts":
                    self.chip_ok.set(f"成功 {event[1]}", "success")
                    self.chip_skip.set(f"跳过 {event[2]}", "warning")
                    self.chip_fail.set(f"失败 {event[3]}", "danger")
                elif kind == "status":
                    self._set_status(event[1])
                elif kind == "finish":
                    self._finish(*event[1:])
        except queue.Empty:
            pass
        if self.winfo_root_exists():
            self.root.after(90, self._poll_events)

    def winfo_root_exists(self):
        try:
            return bool(self.root.winfo_exists())
        except tk.TclError:
            return False

    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------
    def _set_row_state(self, path, state):
        if not self.tree.exists(path):
            return
        label, tag = ROW_STATES.get(state, ROW_STATES["pending"])
        self.tree.set(path, column="status", value=label)
        extra = ("audio",) if "audio" in self.tree.item(path, "tags") else ()
        self.tree.item(path, tags=(tag,) + extra)

    def _set_status(self, text):
        self.label_status.configure(text=text)

    def _log(self, message):
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log.configure(state="normal")
        self.log.insert("end", f"[{stamp}] {message}\n")
        lines = int(float(self.log.index("end-1c").split(".")[0]))
        if lines > LOG_LINE_LIMIT:
            self.log.delete("1.0", f"{lines - LOG_LINE_LIMIT}.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    def clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")


def main():
    try:  # crisp text on high-DPI displays (Windows 8.1+)
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:  # noqa: BLE001 - non-Windows / older builds
        pass
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
