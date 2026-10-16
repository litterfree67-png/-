# -*- coding: utf-8 -*-
"""Canvas-drawn controls: rounded buttons, switches, segmented control, slider.

ttk has no way to express these, so they are drawn here. Every widget exposes
``apply_theme(t)`` so the app can re-skin itself without rebuilding layouts.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont

from ui_tokens import RADIUS, SPACE, TYPE_SCALE, font as tk_font


def rounded_points(x, y, w, h, r):
    """Points list for a rounded rectangle usable with create_polygon(smooth)."""
    r = min(r, w / 2, h / 2)
    return [
        x + r, y,
        x + w - r, y,
        x + w, y + r / 2,
        x + w, y + h - r,
        x + w - r, y + h,
        x + r, y + h,
        x, y + h - r / 2,
        x, y + r,
    ]


def _family(spec):
    return spec[0] if isinstance(spec, (tuple, list)) else spec


class ThemedMixin:
    """Registers widgets so the app can re-theme everything at once."""

    def register_retheme(self, callback):
        self._retheme = callback
        return self

    def apply_theme(self, t):  # pragma: no cover - overridden
        pass


# ---------------------------------------------------------------------------
# Buttons
# ---------------------------------------------------------------------------
class RoundedButton(tk.Canvas, ThemedMixin):
    """A rounded, bordered button with default / hover / press / disabled states."""

    SIZES = {
        "sm": {"h": 28, "font": "caption", "padx": 12},
        "md": {"h": 34, "font": "body", "padx": 16},
        "lg": {"h": 42, "font": "title", "padx": 22},
        "wide": {"h": 46, "font": "subtitle", "padx": 26},
    }

    def __init__(self, master, text="", command=None, variant="secondary",
                 size="md", width=None, **kwargs):
        spec = self.SIZES[size]
        self.text = text
        self.command = command
        self.variant = variant
        self.size = size
        self._fixed_width = width
        self._state = "normal"
        self._pressed = False
        self._hover = False
        self._t = None

        tk.Canvas.__init__(
            self, master,
            height=spec["h"],
            width=width or 80,
            highlightthickness=0,
            bd=0,
            relief="flat",
            takefocus=1,
            **kwargs,
        )
        self.bind("<Configure>", self._on_configure)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Return>", self._invoke_key)
        self.bind("<space>", self._invoke_key)
        self.bind("<FocusIn>", lambda _e: self._set_hover(True))
        self.bind("<FocusOut>", lambda _e: self._set_hover(False))

    # -- lifecycle ---------------------------------------------------------
    def apply_theme(self, t):
        self._t = t
        self._font_tuple = tk_font(self.SIZES[self.size]["font"],
                                   "bold" if self.variant == "primary" else "regular")
        self._font = tkfont.Font(root=self, font=self._font_tuple)
        width = self._fixed_width or self._measure_width(t)
        self.configure(width=width, background=self._parent_bg(t))
        self._width = width
        self._draw()

    def _measure_width(self, t):
        padx = self.SIZES[self.size]["padx"]
        text_w = self._font.measure(self.text)
        return int(text_w + padx * 2)

    def _parent_bg(self, t=None):
        try:
            bg = self.master.cget("background")
            if bg:
                return bg
        except tk.TclError:
            pass
        return (t or self._t or {}) .get("surface", "#FFFFFF")

    # -- state -------------------------------------------------------------
    def set_text(self, text):
        self.text = text
        if self._t:
            if not self._fixed_width:
                self.configure(width=self._measure_width(self._t))
            self._draw()

    def configure_state(self, state):
        self._state = state
        if self._t:
            self._draw()

    state = configure_state

    def invoke(self):
        if self._state == "disabled" or not self.command:
            return
        self.command()

    # -- events ------------------------------------------------------------
    def _on_configure(self, event):
        """Keep the painted surface in sync when a layout stretches us."""
        if not self._t or self._fixed_width:
            return
        width = max(self._measure_width(self._t), event.width)
        if width != getattr(self, "_width", None):
            self._width = width
            if self._width != self.winfo_width():
                self.configure(width=width)
            self._draw()

    def _on_enter(self, _event=None):
        self._set_hover(True)

    def _on_leave(self, _event=None):
        self._set_hover(False)

    def _set_hover(self, value):
        if self._state == "disabled" or self._hover == value:
            return
        self._hover = value
        self._draw()

    def _on_press(self, _event=None):
        if self._state == "disabled":
            return
        self._pressed = True
        self._draw()

    def _on_release(self, _event=None):
        if self._state == "disabled":
            return
        was_pressed = self._pressed
        self._pressed = False
        self._draw()
        if was_pressed:
            self.invoke()

    def _invoke_key(self, _event=None):
        self.invoke()
        return "break"

    # -- painting ----------------------------------------------------------
    def _colors(self):
        t = self._t
        if self._state == "disabled":
            fill = t["surface_sunken"]
            edge = t["border"]
            text = t["text_muted"]
        elif self.variant == "primary":
            fill = t["accent_press"] if self._pressed else (
                t["accent_hover"] if self._hover else t["accent"])
            edge = fill
            text = t["text_on_accent"]
        elif self.variant == "ghost":
            fill = t["accent_soft"] if self._hover or self._pressed else ""
            edge = "" if not self._hover else t["accent"]
            text = t["accent_soft_text"]
        else:  # secondary
            fill = t["surface"]
            if self._hover:
                fill = t["surface_hover"]
            edge = t["border_strong"] if self._hover else t["border"]
            text = t["text"]
        return fill, edge, text

    def _draw(self):
        if not self._t:
            return
        self.delete("all")
        h = int(self.cget("height"))
        w = int(self.cget("width"))
        fill, edge, text_color = self._colors()
        r = RADIUS["md"]
        if fill:
            self.create_polygon(rounded_points(1, 1, w - 2, h - 2, r),
                                fill=fill, outline="", smooth=True)
        if edge:
            self.create_polygon(rounded_points(1, 1, w - 2, h - 2, r),
                                fill="", outline=edge, smooth=True, width=1)
        self.create_text(w / 2, h / 2, text=self.text, fill=text_color,
                         font=self._font_tuple)


# ---------------------------------------------------------------------------
# Switch
# ---------------------------------------------------------------------------
class Toggle(tk.Canvas, ThemedMixin):
    """A 42x24 switch wired to a BooleanVar."""

    W, H = 42, 24

    def __init__(self, master, variable, command=None, **kwargs):
        self.variable = variable
        self.command = command
        self._t = None
        self._hover = False
        self._anim = None
        self._pos = 1.0 if variable.get() else 0.0
        tk.Canvas.__init__(self, master, width=self.W, height=self.H,
                           highlightthickness=0, bd=0, takefocus=1, **kwargs)
        self.bind("<ButtonRelease-1>", self._toggle)
        self.bind("<Return>", self._toggle_key)
        self.bind("<space>", self._toggle_key)
        self.bind("<Enter>", lambda _e: self._set_hover(True))
        self.bind("<Leave>", lambda _e: self._set_hover(False))
        variable.trace_add("write", lambda *_: self._draw())

    def apply_theme(self, t):
        self._t = t
        self.configure(background=self._parent_bg())
        self._draw()

    def _parent_bg(self):
        try:
            bg = self.master.cget("background")
            return bg if bg else "#FFFFFF"
        except tk.TclError:
            return "#FFFFFF"

    def _toggle(self, _event=None):
        self.variable.set(not self.variable.get())
        if self.command:
            self.command()
        self._animate()

    def _toggle_key(self, _event=None):
        self._toggle()
        return "break"

    def _set_hover(self, value):
        self._hover = value
        self._draw()

    def _animate(self):
        target = 1.0 if self.variable.get() else 0.0
        start = self._pos
        steps = 8

        def step(i=0):
            if not self.winfo_exists():
                return
            self._pos = start + (target - start) * ((i + 1) / steps)
            self._draw()
            if i + 1 < steps:
                self.after(14, step, i + 1)

        step()

    def _draw(self):
        if not self._t:
            return
        t = self._t
        self.delete("all")
        on = self.variable.get()
        target = 1.0 if on else 0.0
        # Snap once the easing lands close enough to its target.
        p = target if abs(self._pos - target) < 0.01 else self._pos
        track = t["accent_hover"] if (on and self._hover) else (
            t["accent"] if on else t["border_strong"])
        r = 8
        self.create_polygon(rounded_points(1, 1, self.W - 2, self.H - 2, self.H / 2),
                            fill=track, outline="", smooth=True)
        x = 3 + p * (self.W - 6 - r * 2)
        self.create_oval(x, 3, x + r * 2, 3 + r * 2,
                         fill=t["surface"], outline=t["accent"] if on else t["text_muted"],
                         width=1)


# ---------------------------------------------------------------------------
# Segmented control
# ---------------------------------------------------------------------------
class Segmented(tk.Canvas, ThemedMixin):
    """Horizontal segmented picker backed by a StringVar."""

    H = 32

    def __init__(self, master, options, variable, command=None, width=None, **kwargs):
        self.options = list(options)          # [(value, label), ...]
        self.variable = variable
        self.command = command
        self._t = None
        self._hot = None
        tk.Canvas.__init__(self, master, height=self.H,
                           width=width or (140 * len(options)),
                           highlightthickness=0, bd=0, takefocus=1, **kwargs)
        self.bind("<ButtonRelease-1>", self._click)
        self.bind("<Motion>", self._motion)
        self.bind("<Leave>", lambda _e: self._set_hot(None))
        self.bind("<Return>", self._cycle)
        variable.trace_add("write", lambda *_: self._draw())

    def apply_theme(self, t):
        self._t = t
        self._measure = tkfont.Font(root=self, font=tk_font("body"))
        self.configure(background=self._parent_bg(t))
        self._resize()
        self._draw()

    def _parent_bg(self, t=None):
        try:
            bg = self.master.cget("background")
            if bg:
                return bg
        except tk.TclError:
            pass
        return (t or self._t or {}).get("surface", "#FFFFFF")

    def _resize(self):
        padx = SPACE["xl"]
        self._bounds = []
        total = 0
        for _value, label in self.options:
            width = max(96, self._measure.measure(label) + padx * 2)
            self._bounds.append((total, total + width))
            total += width
        self._total = total
        self.configure(width=total)

    def _hit(self, x):
        for i, (start, end) in enumerate(self._bounds):
            if start <= x <= end:
                return i
        return None

    def _motion(self, event):
        index = self._hit(event.x)
        if index != self._hot:
            self._set_hot(index)

    def _set_hot(self, index):
        self._hot = index
        self._draw()

    def _click(self, event):
        index = self._hit(event.x)
        if index is None:
            return
        value = self.options[index][0]
        if value != self.variable.get():
            self.variable.set(value)
            if self.command:
                self.command()

    def _cycle(self, _event):
        values = [v for v, _ in self.options]
        current = self.variable.get()
        nxt = values[(values.index(current) + 1) % len(values)] if current in values else values[0]
        self.variable.set(nxt)
        if self.command:
            self.command()
        return "break"

    def _draw(self):
        if not self._t:
            return
        t = self._t
        self.delete("all")
        h = int(self.cget("height"))
        inset = 1
        self.create_polygon(rounded_points(inset, inset, self._total - inset * 2,
                                           h - inset * 2, RADIUS["md"]),
                            fill=t["surface_sunken"], outline=t["border"], smooth=True)
        current = self.variable.get()
        for i, (value, label) in enumerate(self.options):
            start, end = self._bounds[i]
            selected = value == current
            if selected:
                self.create_polygon(rounded_points(start + 2, 3, end - start - 4, h - 6,
                                                   RADIUS["sm"]),
                                    fill=t["surface"], outline=t["border_strong"],
                                    smooth=True)
                fill = t["accent"]
            else:
                fill = t["accent_soft_text"] if self._hot == i else t["text_secondary"]
            self.create_text((start + end) / 2, h / 2, text=label, fill=fill,
                             font=tk_font("body", "bold" if selected else "regular"))


# ---------------------------------------------------------------------------
# Status chips
# ---------------------------------------------------------------------------
class Chip(tk.Canvas, ThemedMixin):
    """Small status pill used for counts, states and badges."""

    TONES = ("neutral", "success", "warning", "danger", "info", "accent")

    def __init__(self, master, text="", tone="neutral", height=22, **kwargs):
        self.text = text
        self.tone = tone
        self._t = None
        tk.Canvas.__init__(self, master, height=height, width=64,
                           highlightthickness=0, bd=0, **kwargs)

    def apply_theme(self, t):
        self._t = t
        self._font_tuple = tk_font("label", "bold")
        self._font = tkfont.Font(root=self, font=self._font_tuple)
        self.configure(background=self._parent_bg(t))
        self._draw()

    def _parent_bg(self, t=None):
        try:
            bg = self.master.cget("background")
            if bg:
                return bg
        except tk.TclError:
            pass
        return (t or self._t or {}).get("surface", "#FFFFFF")

    def set(self, text, tone=None):
        self.text = text
        if tone:
            self.tone = tone
        if self._t:
            self._draw()

    configure_text = set

    def _draw(self):
        if not self._t:
            return
        t = self._t
        self.delete("all")
        bg_key = {
            "neutral": "surface_sunken", "success": "success_soft",
            "warning": "warning_soft", "danger": "danger_soft",
            "info": "info_soft", "accent": "accent_soft",
        }[self.tone]
        fg_key = {
            "neutral": "text_secondary", "success": "success",
            "warning": "warning", "danger": "danger",
            "info": "info", "accent": "accent_soft_text",
        }[self.tone]
        width = max(28, self._font.measure(self.text) + SPACE["md"] * 2)
        h = int(self.cget("height"))
        self.configure(width=width)
        self.create_polygon(rounded_points(1, 1, width - 2, h - 2, h / 2),
                            fill=t[bg_key], outline="", smooth=True)
        self.create_text(width / 2, h / 2 + 0.5, text=self.text, fill=t[fg_key],
                         font=self._font_tuple)


# ---------------------------------------------------------------------------
# Window chrome
# ---------------------------------------------------------------------------
class TitleBar(tk.Frame, ThemedMixin):
    """Borderless window chrome: drag handle, product mark, window controls."""

    HEIGHT = 46

    def __init__(self, master, title, subtitle="", on_minimize=None,
                 on_toggle_max=None, on_close=None, **kwargs):
        tk.Frame.__init__(self, master, height=self.HEIGHT, **kwargs)
        self.configure(borderwidth=0, highlightthickness=0)
        self._t = None
        self._widgets = []
        self._drag = None

        self.logo = tk.Canvas(self, width=26, height=26, highlightthickness=0, bd=0)
        self.logo.pack(side="left", padx=(SPACE["lg"], SPACE["sm"]))
        self.logo.bind("<ButtonPress-1>", self._start_drag)
        self.logo.bind("<B1-Motion>", self._do_drag)

        self.text_col = tk.Frame(self)
        self.text_col.pack(side="left", fill="y")
        self.title_label = tk.Label(self.text_col, text=title, anchor="w")
        self.title_label.pack(side="top", anchor="w", pady=(6, 0))
        self.subtitle_label = tk.Label(self.text_col, text=subtitle, anchor="w")
        self.subtitle_label.pack(side="top", anchor="w")

        self.actions = tk.Frame(self)
        self.actions.pack(side="right", padx=(0, SPACE["xs"]))

        self.btn_max = self._chrome_button("max", on_toggle_max)
        self.btn_min = self._chrome_button("min", on_minimize)
        self.btn_close = self._chrome_button("close", on_close, danger=True)

        for widget in (self.title_label, self.subtitle_label, self.text_col):
            widget.bind("<ButtonPress-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._do_drag)
        self.bind("<ButtonPress-1>", self._start_drag)
        self.bind("<B1-Motion>", self._do_drag)
        self.bind("<Double-Button-1>", lambda _e: on_toggle_max and on_toggle_max())

    def add_action(self, name, command, tip="", padx=0):
        """Add an extra vector-icon button to the left of window controls."""
        canvas = self._chrome_button(name, command)
        canvas.pack_configure(padx=(padx, SPACE["lg"]))
        return canvas

    def _chrome_button(self, icon, command, danger=False):
        canvas = tk.Canvas(self.actions, width=34, height=32,
                           highlightthickness=0, bd=0)
        canvas._icon = icon
        self._paint_icon(canvas, icon, danger)
        canvas.bind("<ButtonRelease-1>", lambda _e: command and command())
        canvas.bind("<Enter>",
                    lambda _e: self._paint_icon(canvas, icon, danger, hover=True))
        canvas.bind("<Leave>",
                    lambda _e: self._paint_icon(canvas, icon, danger))
        self._widgets.append((canvas, icon, danger))
        canvas.pack(side="right")
        return canvas

    def _paint_icon(self, canvas, icon, danger, hover=False):
        canvas.delete("all")
        if not self._t:
            return
        t = self._t
        canvas.configure(
            background=t["danger"] if (danger and hover) else
            (self._lighten() if hover else t["inverse"]))
        color = t["text_inverse"]
        mid = 17.0
        if icon == "min":
            canvas.create_line(11, 21.5, 23, 21.5, fill=color, width=1.4)
        elif icon == "max":
            canvas.create_rectangle(11.5, 10.5, 22.5, 21.5, outline=color,
                                    width=1.4)
        elif icon == "close":
            canvas.create_line(12, 11, 22, 21, fill=color, width=1.4)
            canvas.create_line(22, 11, 12, 21, fill=color, width=1.4)
        elif icon == "theme":
            # Half-filled circle: the classic light/dark switch mark.
            canvas.create_oval(mid - 6.5, 16 - 6.5, mid + 6.5, 16 + 6.5,
                               outline=color, width=1.4)
            canvas.create_arc(mid - 6.5, 16 - 6.5, mid + 6.5, 16 + 6.5,
                              start=90, extent=180, fill=color, outline="")

    def _hover_bg(self, danger):
        return self._t["danger"] if danger else self._lighten()

    def _lighten(self):
        if not self._t:
            return "#333333"
        hex_value = self._t["inverse"].lstrip("#")
        channels = [int(hex_value[i:i + 2], 16) for i in (0, 2, 4)]
        lifted = "".join(f"{min(255, c + 26):02X}" for c in channels)
        return "#" + lifted

    def apply_theme(self, t):
        self._t = t
        bg = t["inverse"]
        self.configure(background=bg)
        self.logo.configure(background=bg)
        self.actions.configure(background=bg)
        self.text_col.configure(background=bg)
        self.title_label.configure(background=bg, foreground=t["text_inverse"],
                                   font=tk_font("body", "bold"))
        self.subtitle_label.configure(background=bg,
                                      foreground=t["text_secondary"],
                                      font=tk_font("caption"))
        for canvas, icon, danger in self._widgets:
            self._paint_icon(canvas, icon, danger)
        self._draw_logo()

    def _draw_logo(self):
        self.logo.delete("all")
        t = self._t
        # A film sprocket: rounded square aperture + two sprocket holes.
        self.logo.create_polygon(rounded_points(1, 1, 24, 24, RADIUS["md"]),
                                 fill=t["accent"], outline="", smooth=True)
        self.logo.create_rectangle(5, 8, 8, 12, fill=t["inverse"], outline="")
        self.logo.create_rectangle(5, 15, 8, 19, fill=t["inverse"], outline="")
        self.logo.create_rectangle(18, 8, 21, 12, fill=t["inverse"], outline="")
        self.logo.create_rectangle(18, 15, 21, 19, fill=t["inverse"], outline="")

    # -- window dragging ---------------------------------------------------
    def _start_drag(self, event):
        self._drag = (event.x_root, event.y_root,
                      self.winfo_toplevel().winfo_x(),
                      self.winfo_toplevel().winfo_y())

    def _do_drag(self, event):
        if not self._drag:
            return
        x_root, y_root, x, y = self._drag
        self.winfo_toplevel().geometry(
            f"+{x + event.x_root - x_root}+{y + event.y_root - y_root}"
        )


class CanvasSlider(tk.Canvas, ThemedMixin):
    """A clean horizontal slider: 4px track, filled portion, round knob."""

    HEIGHT = 26

    def __init__(self, master, from_=0, to=51, variable=None, command=None,
                 **kwargs):
        self.min_value = from_
        self.max_value = to
        self.variable = variable
        self.command = command
        self._state = "normal"
        self._t = None
        self._dragging = False
        tk.Canvas.__init__(self, master, height=self.HEIGHT,
                           highlightthickness=0, bd=0, takefocus=1, **kwargs)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Configure>", lambda _e: self._draw())
        self.variable.trace_add("write", lambda *_: self._draw())

    def configure_state(self, state):
        self._state = state
        self._draw()

    state = configure_state

    # -- theming -----------------------------------------------------------
    def apply_theme(self, t):
        self._t = t
        self.configure(background=self._parent_bg(t))
        self._draw()

    def _parent_bg(self, t=None):
        try:
            bg = self.master.cget("background")
            if bg:
                return bg
        except tk.TclError:
            pass
        return (t or self._t or {}).get("surface", "#FFFFFF")

    # -- interaction -------------------------------------------------------
    def _value_at(self, x):
        width = max(1, self.winfo_width() - 20)
        ratio = min(1.0, max(0.0, (x - 10) / width))
        return round(self.min_value + ratio * (self.max_value - self.min_value))

    def _on_press(self, event):
        if self._state == "disabled":
            return
        self._dragging = True
        self._commit(self._value_at(event.x))

    def _on_drag(self, event):
        if self._dragging and self._state != "disabled":
            self._commit(self._value_at(event.x))

    def _on_release(self, _event):
        self._dragging = False

    def _commit(self, value):
        if value != self.variable.get():
            self.variable.set(value)
        if self.command:
            self.command()

    # -- painting ----------------------------------------------------------
    def _draw(self):
        if not self._t:
            return
        t = self._t
        self.delete("all")
        requested = int(float(self.cget("width")))
        width = self.winfo_width()
        width = width if width > 10 else max(requested, 120)
        height = self.HEIGHT
        span = max(1, width - 20)
        ratio = ((self.variable.get() - self.min_value)
                 / (self.max_value - self.min_value))
        ratio = min(1.0, max(0.0, ratio))
        disabled = self._state == "disabled"
        track_fill = t["surface_sunken"]
        fill = t["border_strong"] if disabled else t["accent"]
        knob_fill = t["surface_sunken"] if disabled else t["surface"]
        knob_edge = t["border_strong"] if disabled else t["accent"]
        y = height / 2
        self.create_rectangle(10, y - 2, 10 + span, y + 2,
                              fill=track_fill, outline="", width=0)
        self.create_rectangle(10, y - 2, 10 + span * ratio, y + 2,
                              fill=fill, outline="", width=0)
        knob_x = 10 + span * ratio
        self.create_oval(knob_x - 8, y - 8, knob_x + 8, y + 8,
                         fill=knob_fill, outline=knob_edge, width=2)


class ResizeGrip(tk.Canvas, ThemedMixin):
    """Bottom-right grip that resizes a borderless window."""

    SIZE = 16

    def __init__(self, master, **kwargs):
        tk.Canvas.__init__(self, master, width=self.SIZE, height=self.SIZE,
                           highlightthickness=0, bd=0, cursor="sizing", **kwargs)
        self._t = None
        self._origin = None
        self.bind("<ButtonPress-1>", self._start)
        self.bind("<B1-Motion>", self._resize)

    def apply_theme(self, t):
        self._t = t
        self.configure(background=self._parent_bg())
        self.delete("all")
        color = t["text_muted"]
        s = self.SIZE
        for i in range(3):
            offset = 3 + i * 4
            self.create_line(offset, s - 3, s - 3, offset, fill=color, width=1)

    def _parent_bg(self):
        try:
            return self.master.cget("background") or "#FFFFFF"
        except tk.TclError:
            return "#FFFFFF"

    def _start(self, event):
        top = self.winfo_toplevel()
        self._origin = (event.x_root, event.y_root, top.winfo_width(),
                        top.winfo_height())

    def _resize(self, event):
        if not self._origin:
            return
        x_root, y_root, w, h = self._origin
        new_w = max(self.master.winfo_toplevel().minsize()[0], w + event.x_root - x_root)
        new_h = max(self.master.winfo_toplevel().minsize()[1], h + event.y_root - y_root)
        self.master.winfo_toplevel().geometry(f"{int(new_w)}x{int(new_h)}")
