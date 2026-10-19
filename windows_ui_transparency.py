from __future__ import annotations

import ctypes
import json
import math
import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox
from ctypes import wintypes

if sys.platform == "win32":
    import winreg
else:
    winreg = None

APP_TITLE = "Windows UI Transparency"
APP_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_RUN_VALUE = "WindowsUITransparency"
WCA_ACCENT_POLICY = 19
ACCENT_DISABLED = 0
ACCENT_ENABLE_TRANSPARENTGRADIENT = 2
ACCENT_ENABLE_BLURBEHIND = 3
ACCENT_ENABLE_ACRYLICBLURBEHIND = 4
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
LWA_ALPHA = 0x00000002

user32 = ctypes.windll.user32 if sys.platform == "win32" else None


class ACCENT_POLICY(ctypes.Structure):
    _fields_ = [
        ("AccentState", ctypes.c_int),
        ("AccentFlags", ctypes.c_int),
        ("GradientColor", ctypes.c_uint),
        ("AnimationId", ctypes.c_int),
    ]


class WINDOWCOMPOSITIONATTRIBUTEDATA(ctypes.Structure):
    _fields_ = [
        ("Attribute", ctypes.c_int),
        ("Data", ctypes.c_void_p),
        ("SizeOfData", ctypes.c_size_t),
    ]


def config_file() -> Path:
    base = os.environ.get("APPDATA")
    root = Path(base) if base else Path.home() / ".config"
    return root / "WindowsUITransparency" / "settings.json"


def load_settings() -> dict:
    defaults = {
        "taskbar_mode": "アクリル風",
        "taskbar_opacity": 78,
        "clock_opacity": 100,
        "icons_opacity": 100,
        "auto_reapply": True,
    }
    try:
        data = json.loads(config_file().read_text(encoding="utf-8"))
        if isinstance(data, dict):
            defaults.update(data)
    except (OSError, ValueError, TypeError):
        pass
    if defaults["taskbar_mode"] not in ("透明", "ぼかし", "アクリル風", "通常に戻す"):
        defaults["taskbar_mode"] = "アクリル風"
    for key in ("taskbar_opacity", "clock_opacity", "icons_opacity"):
        try:
            defaults[key] = max(0, min(100, int(defaults[key])))
        except (ValueError, TypeError):
            defaults[key] = 100 if key != "taskbar_opacity" else 78
    defaults["auto_reapply"] = bool(defaults["auto_reapply"])
    return defaults


def save_settings(settings: dict) -> None:
    try:
        path = config_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        # A read-only profile should not prevent the app from being used.
        pass


def find_taskbar():
    return user32.FindWindowW("Shell_TrayWnd", None) if user32 else None


def apply_taskbar_effect(mode: str, opacity: int = 78) -> tuple[bool, str]:
    """Apply a taskbar accent effect using an undocumented Windows API."""
    if sys.platform != "win32":
        return False, "このアプリはWindows専用です。"
    hwnd = find_taskbar()
    if not hwnd:
        return False, "タスクバーが見つかりません。Explorerの再起動後に再試行してください。"
    setter = getattr(user32, "SetWindowCompositionAttribute", None)
    if setter is None:
        return False, "このWindows環境では必要なAPIを利用できません。"

    if mode == "通常に戻す":
        state, color = ACCENT_DISABLED, 0
    elif mode == "透明":
        state = ACCENT_ENABLE_TRANSPARENTGRADIENT
        color = ((max(0, min(100, opacity)) * 255 // 100) << 24) | 0x00202020
    elif mode == "ぼかし":
        state = ACCENT_ENABLE_BLURBEHIND
        alpha = max(0, min(100, opacity)) * 255 // 100
        color = (alpha << 24) | 0x00202020
    else:
        state = ACCENT_ENABLE_ACRYLICBLURBEHIND
        alpha = max(0, min(100, opacity)) * 255 // 100
        color = (alpha << 24) | 0x00202020

    policy = ACCENT_POLICY(state, 2, color, 0)
    data = WINDOWCOMPOSITIONATTRIBUTEDATA(
        WCA_ACCENT_POLICY,
        ctypes.cast(ctypes.pointer(policy), ctypes.c_void_p),
        ctypes.sizeof(policy),
    )
    setter.argtypes = [wintypes.HWND, ctypes.POINTER(WINDOWCOMPOSITIONATTRIBUTEDATA)]
    setter.restype = wintypes.BOOL
    if setter(hwnd, ctypes.byref(data)):
        return True, f"タスクバーを「{mode}」に設定しました。"
    return False, "Windowsが効果の適用を拒否しました。「通常に戻す」を試してください。"


def enum_taskbar_children() -> list[tuple[int, str]]:
    """Return descendant HWNDs and class names that actually exist on this Windows build."""
    taskbar = find_taskbar()
    if not taskbar or user32 is None:
        return []
    found: list[tuple[int, str]] = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd, _lparam):
        name = ctypes.create_unicode_buffer(256)
        if user32.GetClassNameW(hwnd, name, len(name)):
            found.append((int(hwnd), name.value))
        return True

    callback_ref = callback_type(callback)
    user32.EnumChildWindows(taskbar, callback_ref, 0)
    return found


def find_component_window(component: str):
    # Legacy HWNDs exist on some Windows builds. Newer builds may render these
    # components inside a shared XAML/DirectComposition visual instead.
    wanted = {
        "clock": {"TrayClockWClass"},
        "icons": {"MSTaskListWClass"},
    }.get(component, set())
    for hwnd, class_name in enum_taskbar_children():
        if class_name in wanted:
            return hwnd, class_name
    return None, None


def _window_long_function(getter: bool):
    if user32 is None:
        return None
    names = ("GetWindowLongPtrW", "GetWindowLongW") if getter else ("SetWindowLongPtrW", "SetWindowLongW")
    for name in names:
        function = getattr(user32, name, None)
        if function:
            if getter:
                function.argtypes = [wintypes.HWND, ctypes.c_int]
                function.restype = ctypes.c_ssize_t
            else:
                function.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
                function.restype = ctypes.c_ssize_t
            return function
    return None



def _rounded_points(x1: float, y1: float, x2: float, y2: float, radius: float) -> list[float]:
    """Return polygon coordinates with softly rounded corners."""
    radius = max(1.0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
    points: list[tuple[float, float]] = [(x1 + radius, y1), (x2 - radius, y1)]
    corners = [
        (x2 - radius, y1 + radius, -90, 0),
        (x2 - radius, y2 - radius, 0, 90),
        (x1 + radius, y2 - radius, 90, 180),
        (x1 + radius, y1 + radius, 180, 270),
    ]
    for cx, cy, start, end in corners:
        for degree in range(start, end + 1, 15):
            angle = math.radians(degree)
            points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    points.append((x1 + radius, y1))
    flattened: list[float] = []
    for x, y in points:
        flattened.extend((x, y))
    return flattened


def _mix_color(start: str, end: str, amount: float) -> str:
    amount = max(0.0, min(1.0, amount))
    a = tuple(int(start[i:i + 2], 16) for i in (1, 3, 5))
    b = tuple(int(end[i:i + 2], 16) for i in (1, 3, 5))
    rgb = tuple(round(a[i] + (b[i] - a[i]) * amount) for i in range(3))
    return "#" + "".join(f"{part:02x}" for part in rgb)


class RoundedPanel(tk.Canvas):
    """A canvas-drawn rounded card with a normal Tk frame inset inside it."""
    def __init__(self, parent, height: int, fill: str = "#151F2B",
                 border: str = "#293B4B", radius: int = 20, inset: int = 16):
        super().__init__(parent, height=height, bg=parent.cget("bg"),
                         highlightthickness=0, bd=0, relief="flat")
        self.fill = fill
        self.border = border
        self.radius = radius
        self.inset = inset
        self.inner = tk.Frame(self, bg=fill, bd=0, highlightthickness=0)
        self.window_id = self.create_window((inset, 12), anchor="nw", window=self.inner)
        self.bind("<Configure>", self._layout)
        self._layout()

    def _layout(self, _event=None):
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        self.delete("card-shape")
        self.create_polygon(
            _rounded_points(1, 1, width - 2, height - 2, self.radius),
            fill=self.fill, outline=self.border, width=1, tags="card-shape"
        )
        self.tag_lower("card-shape")
        self.coords(self.window_id, self.inset, 12)
        self.itemconfigure(self.window_id,
                           width=max(1, width - self.inset * 2),
                           height=max(1, height - 24))


class PillButton(tk.Canvas):
    """Rounded button with clear hover and press feedback."""
    def __init__(self, parent, text: str, command, width: int = 132, height: int = 38,
                 fill: str = "#263747", hover: str = "#344A5C",
                 selected_fill: str = "#38596D", foreground: str = "#E8EEF2",
                 border: str = "#3D5364", selected: bool = False,
                 radius: int = 18, font=("Yu Gothic UI", 10, "bold")):
        super().__init__(parent, width=width, height=height, bg=parent.cget("bg"),
                         highlightthickness=0, bd=0)
        self.text = text
        self.command = command
        self.width = width
        self.height = height
        self.fill = fill
        self.hover_fill = hover
        self.selected_fill = selected_fill
        self.foreground = foreground
        self.border = border
        self.selected = selected
        self.radius = radius
        self.font = font
        self.hovered = False
        self.pressed = False
        self.enabled = True
        self.bind("<Configure>", self._draw)
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)
        self._draw()

    def set_selected(self, selected: bool):
        self.selected = bool(selected)
        self._draw()

    def set_enabled(self, enabled: bool):
        self.enabled = bool(enabled)
        self.configure(cursor="hand2" if enabled else "arrow")
        self._draw()

    def _draw(self, _event=None):
        self.delete("all")
        w = max(1, self.winfo_width())
        h = max(1, self.winfo_height())
        inset = 3 if self.pressed else (1 if self.hovered else 2)
        fill = self.selected_fill if self.selected else self.fill
        if self.hovered and self.enabled:
            fill = self.hover_fill if not self.selected else _mix_color(self.selected_fill, "#526D7E", 0.35)
        if not self.enabled:
            fill = "#202B36"
        self.create_polygon(
            _rounded_points(inset, inset, w - inset, h - inset, self.radius),
            fill=fill, outline=self.border if self.enabled else "#2C3742", width=1
        )
        fg = self.foreground if self.enabled else "#72808D"
        self.create_text(w / 2, h / 2 - (1 if self.pressed else 0),
                         text=self.text, fill=fg, font=self.font)

    def _enter(self, _event=None):
        self.hovered = True
        self._draw()

    def _leave(self, _event=None):
        self.hovered = False
        self.pressed = False
        self._draw()

    def _press(self, event):
        if not self.enabled:
            return
        self.pressed = True
        self._draw()

    def _release(self, event):
        if not self.enabled:
            return
        inside = 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height()
        was_pressed = self.pressed
        self.pressed = False
        self._draw()
        if inside and was_pressed and self.command:
            self.after(65, self.command)


class SmoothSwitch(tk.Frame):
    """Compact rounded toggle with a short animated thumb transition."""
    def __init__(self, parent, text: str, variable: tk.BooleanVar, command=None,
                 bg: str = "#151F2B", foreground: str = "#DCE5EC",
                 muted: str = "#91A2B2", enabled: bool = True):
        super().__init__(parent, bg=bg, bd=0, highlightthickness=0)
        self.variable = variable
        self.command = command
        self.bg_color = bg
        self.foreground = foreground
        self.muted = muted
        self.enabled = enabled
        self.canvas = tk.Canvas(self, width=48, height=28, bg=bg,
                                highlightthickness=0, bd=0, cursor="hand2")
        self.canvas.pack(side="left", padx=(0, 10))
        self.label = tk.Label(self, text=text, bg=bg, fg=foreground,
                              font=("Yu Gothic UI", 10), anchor="w",
                              justify="left", wraplength=565)
        self.label.pack(side="left", fill="x", expand=True)
        self._position = 35.0 if variable.get() else 13.0
        self.canvas.bind("<Button-1>", self._toggle)
        self.label.bind("<Button-1>", self._toggle)
        self.bind("<Button-1>", self._toggle)
        self.canvas.bind("<Enter>", self._hover)
        self.canvas.bind("<Leave>", self._leave)
        self._draw()

    def set_enabled(self, enabled: bool):
        self.enabled = bool(enabled)
        self.label.configure(fg=self.foreground if enabled else self.muted)
        self.canvas.configure(cursor="hand2" if enabled else "arrow")
        self._draw()

    def _hover(self, _event=None):
        if self.enabled:
            self.canvas.configure(cursor="hand2")

    def _leave(self, _event=None):
        self._draw()

    def _draw(self):
        self.canvas.delete("all")
        on = bool(self.variable.get())
        track = "#536F81" if on else "#2A3A48"
        if not self.enabled:
            track = "#202A34"
        points = _rounded_points(2, 3, 46, 25, 11)
        self.canvas.create_polygon(points, fill=track, outline="#526879" if on else "#354653")
        x = self._position
        knob_fill = "#EDF3F5" if on else "#9EAFBA"
        if not self.enabled:
            knob_fill = "#75838E"
        self.canvas.create_oval(x - 8, 14 - 8, x + 8, 14 + 8,
                                fill=knob_fill, outline="")
        if on:
            self.canvas.create_oval(x - 3, 11, x + 3, 17, fill="#D1E3EA", outline="")

    def _toggle(self, _event=None):
        if not self.enabled:
            return
        old = 35.0 if self.variable.get() else 13.0
        self.variable.set(not self.variable.get())
        target = 35.0 if self.variable.get() else 13.0
        if self.command:
            self.command()
        steps = 4
        for step in range(1, steps + 1):
            value = old + (target - old) * step / steps
            self.after(step * 14, lambda v=value: self._animate_to(v))

    def _animate_to(self, value: float):
        self._position = value
        self._draw()


class TransparencySlider(tk.Frame):
    """Color-feedback slider: low transparency is calm/deeper; high is pale."""
    LOW_COLOR = "#466579"
    HIGH_COLOR = "#D8E5EA"

    def __init__(self, parent, label: str, variable: tk.IntVar, on_change=None,
                 bg: str = "#151F2B", foreground: str = "#E5ECF1",
                 muted: str = "#8FA2B3"):
        super().__init__(parent, bg=bg, bd=0, highlightthickness=0)
        self.variable = variable
        self.on_change = on_change
        self.bg_color = bg
        self.foreground = foreground
        self.muted = muted
        self.dragging = False
        self.hovered = False

        header = tk.Frame(self, bg=bg)
        header.pack(fill="x", pady=(0, 2))
        tk.Label(header, text=label, bg=bg, fg=foreground,
                 font=("Yu Gothic UI", 10, "bold")).pack(side="left")
        self.value_chip = tk.Canvas(header, width=60, height=24, bg=bg,
                                    highlightthickness=0, bd=0)
        self.value_chip.pack(side="right")
        self.canvas = tk.Canvas(self, height=34, bg=bg, highlightthickness=0, bd=0,
                                cursor="hand2")
        self.canvas.pack(fill="x", expand=True)
        self.canvas.bind("<Configure>", self._draw)
        self.canvas.bind("<Button-1>", self._begin_drag)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._end_drag)
        self.canvas.bind("<Enter>", self._enter)
        self.canvas.bind("<Leave>", self._leave)
        self.variable.trace_add("write", self._value_changed)
        self._draw()

    @classmethod
    def _color_for_value(cls, value: int) -> str:
        return _mix_color(cls.LOW_COLOR, cls.HIGH_COLOR, value / 100.0)

    def _value_changed(self, *_args):
        self._draw()

    def _draw(self, _event=None):
        self.canvas.delete("all")
        self.value_chip.delete("all")
        value = max(0, min(100, int(self.variable.get())))
        color = self._color_for_value(value)
        chip_fg = "#F0F4F6" if value < 52 else "#263744"
        self.value_chip.create_polygon(
            _rounded_points(1, 2, 59, 22, 10), fill=color, outline=""
        )
        self.value_chip.create_text(30, 12, text=f"{value}%", fill=chip_fg,
                                    font=("Yu Gothic UI", 9, "bold"))

        width = max(90, self.canvas.winfo_width())
        left, right, y = 9, width - 10, 17
        x = left + (right - left) * value / 100.0
        self.canvas.create_line(left, y, right, y, fill="#293845",
                                width=7, capstyle=tk.ROUND)
        if x > left + 0.5:
            self.canvas.create_line(left, y, x, y, fill=color,
                                    width=7, capstyle=tk.ROUND)
        radius = 8 if self.dragging else (7 if self.hovered else 6)
        self.canvas.create_oval(x - radius - 2, y - radius - 2,
                                x + radius + 2, y + radius + 2,
                                fill="#2A3D4C", outline="")
        self.canvas.create_oval(x - radius, y - radius, x + radius, y + radius,
                                fill=color, outline="#E7EEF1", width=1)

    def _set_from_x(self, x: float):
        width = max(90, self.canvas.winfo_width())
        left, right = 9, width - 10
        value = round((x - left) * 100 / max(1, right - left))
        value = max(0, min(100, value))
        if value != self.variable.get():
            self.variable.set(value)
            if self.on_change:
                self.on_change(value)

    def _begin_drag(self, event):
        self.dragging = True
        self._set_from_x(event.x)
        self._draw()

    def _drag(self, event):
        self._set_from_x(event.x)

    def _end_drag(self, _event=None):
        self.dragging = False
        self._draw()

    def _enter(self, _event=None):
        self.hovered = True
        self._draw()

    def _leave(self, _event=None):
        if not self.dragging:
            self.hovered = False
            self._draw()


class TransparencyApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.settings = load_settings()
        self.last_mode = self.settings["taskbar_mode"]
        self.last_opacity = self.settings["taskbar_opacity"]
        self._component_original_styles: dict[int, int] = {}
        self._component_names: dict[int, str] = {}
        self.root.title(APP_TITLE)
        self.root.geometry("690x850")
        self.root.minsize(610, 740)
        self.root.configure(bg="#10151f")
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.auto_reapply = tk.BooleanVar(value=self.settings["auto_reapply"])
        self.start_with_windows = tk.BooleanVar(value=self._startup_registered())
        self.status = tk.StringVar(value="準備完了。設定を適用してください。")
        self._build_ui()
        self._last_hwnd = find_taskbar()
        self.root.after(1800, self._apply_saved_settings)
        self.root.after(2000, self._watch_explorer)

    def _build_ui(self):
        self.root.configure(bg="#0B1118")
        self.root.geometry("760x980")
        self.root.minsize(700, 880)

        outer = tk.Frame(self.root, bg="#0B1118", padx=22, pady=18)
        outer.pack(fill="both", expand=True)

        # App identity / compact, calm title area.
        header = tk.Frame(outer, bg="#0B1118")
        header.pack(fill="x", pady=(0, 13))
        logo = tk.Canvas(header, width=52, height=52, bg="#0B1118",
                         highlightthickness=0, bd=0)
        logo.pack(side="left", padx=(0, 13))
        logo.create_polygon(_rounded_points(1, 1, 51, 51, 15),
                            fill="#29495E", outline="#607F93", width=1)
        for x1, y1, x2, y2 in ((11, 11, 23, 23), (27, 11, 40, 23),
                               (11, 27, 23, 40), (27, 27, 40, 40)):
            logo.create_polygon(_rounded_points(x1, y1, x2, y2, 3),
                                fill="#DCE8ED", outline="")
        logo.create_polygon(_rounded_points(30, 28, 46, 44, 5),
                            fill="#7FA5B9", outline="#E2EDF1", width=1)
        title_area = tk.Frame(header, bg="#0B1118")
        title_area.pack(side="left", fill="x", expand=True)
        tk.Label(title_area, text="Windows UI Transparency",
                 bg="#0B1118", fg="#E6EDF1",
                 font=("Yu Gothic UI", 17, "bold")).pack(anchor="w")
        tk.Label(title_area, text="Windows 11 の表示を、自分好みに静かに整える",
                 bg="#0B1118", fg="#8DA0AE",
                 font=("Yu Gothic UI", 9)).pack(anchor="w", pady=(2, 0))
        top_pill = RoundedPanel(header, height=36, fill="#14212C",
                                border="#293B49", radius=16, inset=8)
        top_pill.pack(side="right", padx=(8, 0), pady=8)
        tk.Label(top_pill.inner, text="WINDOWS 11",
                 bg="#14212C", fg="#B3C4CE",
                 font=("Segoe UI", 8, "bold")).pack(expand=True)

        # Taskbar background controls.
        task_card = RoundedPanel(outer, height=292, fill="#131E29",
                                 border="#263947", radius=22, inset=18)
        task_card.pack(fill="x", pady=(0, 12))
        tk.Label(task_card.inner, text="タスクバー背景",
                 bg="#131E29", fg="#E7EEF2",
                 font=("Yu Gothic UI", 12, "bold")).pack(anchor="w")
        tk.Label(task_card.inner, text="透明度が高いほどスライダーの色も淡くなります。",
                 bg="#131E29", fg="#8FA2B0",
                 font=("Yu Gothic UI", 9)).pack(anchor="w", pady=(2, 9))

        mode_row = tk.Frame(task_card.inner, bg="#131E29")
        mode_row.pack(fill="x", pady=(0, 10))
        self.mode = tk.StringVar(value=self.last_mode)
        mode_specs = [
            ("透明", "透明"),
            ("ぼかし", "ぼかし"),
            ("アクリル", "アクリル風"),
            ("標準", "通常に戻す"),
        ]
        self.mode_buttons = {}
        for label, value in mode_specs:
            button = PillButton(
                mode_row, label, command=lambda v=value: self.select_mode(v),
                width=112, height=36, fill="#1B2A36", hover="#2B4050",
                selected_fill="#3B5A6D", foreground="#DCE7ED",
                border="#304656", selected=(self.mode.get() == value),
                radius=18, font=("Yu Gothic UI", 9, "bold")
            )
            button.pack(side="left", fill="x", expand=True, padx=(0, 7))
            self.mode_buttons[value] = button

        self.opacity = tk.IntVar(value=self.last_opacity)  # Native alpha / opacity.
        self.taskbar_transparency = tk.IntVar(value=100 - self.last_opacity)
        self.taskbar_slider = TransparencySlider(
            task_card.inner, "背景の透明度", self.taskbar_transparency,
            on_change=self._taskbar_transparency_changed, bg="#131E29",
            foreground="#DDE6EB", muted="#8FA2B0"
        )
        self.taskbar_slider.pack(fill="x", pady=(0, 7))

        action_row = tk.Frame(task_card.inner, bg="#131E29")
        action_row.pack(fill="x", pady=(3, 0))
        PillButton(
            action_row, "適用する", self.apply_taskbar, width=132, height=38,
            fill="#344F61", hover="#45667A", selected_fill="#3B5A6D",
            foreground="#F0F5F7", border="#527185", radius=19
        ).pack(side="left")
        PillButton(
            action_row, "標準に戻す", self.restore_taskbar, width=132, height=38,
            fill="#202E39", hover="#30414D", foreground="#CBD7DE",
            border="#344653", radius=19
        ).pack(side="left", padx=(9, 0))
        tk.Label(task_card.inner,
                 text="※ タスクバーの描画方式はWindowsのビルドによって異なります。",
                 bg="#131E29", fg="#8295A4",
                 font=("Yu Gothic UI", 8)).pack(anchor="w", pady=(8, 0))

        # Component controls.
        item_card = RoundedPanel(outer, height=290, fill="#131E29",
                                 border="#263947", radius=22, inset=18)
        item_card.pack(fill="x", pady=(0, 12))
        tk.Label(item_card.inner, text="個別の表示調整",
                 bg="#131E29", fg="#E7EEF2",
                 font=("Yu Gothic UI", 12, "bold")).pack(anchor="w")
        tk.Label(item_card.inner, text="対象のウィンドウが検出できる環境でのみ適用できます。",
                 bg="#131E29", fg="#8FA2B0",
                 font=("Yu Gothic UI", 9)).pack(anchor="w", pady=(2, 8))

        self.clock_opacity = tk.IntVar(value=self.settings["clock_opacity"])
        self.icons_opacity = tk.IntVar(value=self.settings["icons_opacity"])
        self.clock_transparency = tk.IntVar(value=100 - self.clock_opacity.get())
        self.icons_transparency = tk.IntVar(value=100 - self.icons_opacity.get())

        clock_head = tk.Frame(item_card.inner, bg="#131E29")
        clock_head.pack(fill="x")
        tk.Label(clock_head, text="時計", bg="#131E29", fg="#DDE6EB",
                 font=("Yu Gothic UI", 10, "bold")).pack(side="left")
        PillButton(
            clock_head, "時計に適用", lambda: self.apply_component("clock"),
            width=116, height=32, fill="#1D2E3A", hover="#2F4656",
            foreground="#DCE7ED", border="#314A5A", radius=16,
            font=("Yu Gothic UI", 9, "bold")
        ).pack(side="right")
        self.clock_slider = TransparencySlider(
            item_card.inner, "透明度", self.clock_transparency,
            on_change=self._clock_transparency_changed, bg="#131E29",
            foreground="#DDE6EB", muted="#8FA2B0"
        )
        self.clock_slider.pack(fill="x", pady=(0, 7))

        divider = tk.Frame(item_card.inner, bg="#293B48", height=1)
        divider.pack(fill="x", pady=(1, 8))

        icons_head = tk.Frame(item_card.inner, bg="#131E29")
        icons_head.pack(fill="x")
        tk.Label(icons_head, text="アプリアイコン領域",
                 bg="#131E29", fg="#DDE6EB",
                 font=("Yu Gothic UI", 10, "bold")).pack(side="left")
        PillButton(
            icons_head, "アイコンに適用", lambda: self.apply_component("icons"),
            width=132, height=32, fill="#1D2E3A", hover="#2F4656",
            foreground="#DCE7ED", border="#314A5A", radius=16,
            font=("Yu Gothic UI", 9, "bold")
        ).pack(side="right")
        self.icons_slider = TransparencySlider(
            item_card.inner, "透明度", self.icons_transparency,
            on_change=self._icons_transparency_changed, bg="#131E29",
            foreground="#DDE6EB", muted="#8FA2B0"
        )
        self.icons_slider.pack(fill="x", pady=(0, 2))
        tk.Label(item_card.inner,
                 text="時計・アイコンは新しいWindows 11で独立したウィンドウとして検出できない場合があります。",
                 bg="#131E29", fg="#8295A4", wraplength=655,
                 justify="left", font=("Yu Gothic UI", 8)).pack(anchor="w", pady=(2, 0))

        # Options.
        options_card = RoundedPanel(outer, height=116, fill="#131E29",
                                    border="#263947", radius=22, inset=16)
        options_card.pack(fill="x", pady=(0, 12))
        tk.Label(options_card.inner, text="動作設定",
                 bg="#131E29", fg="#E7EEF2",
                 font=("Yu Gothic UI", 11, "bold")).pack(anchor="w", pady=(0, 5))
        self.auto_reapply = tk.BooleanVar(value=self.settings["auto_reapply"])
        self.reapply_switch = SmoothSwitch(
            options_card.inner, "Explorer再起動後に設定を再適用",
            self.auto_reapply, command=self._save_current_settings,
            bg="#131E29", foreground="#DDE6EB", muted="#7C8D9A"
        )
        self.reapply_switch.pack(fill="x", pady=(1, 5))
        self.start_with_windows = tk.BooleanVar(value=self._startup_registered())
        self.startup_switch = SmoothSwitch(
            options_card.inner, "Windowsサインイン時に起動（タスクマネージャーに表示）",
            self.start_with_windows, command=self.toggle_startup,
            bg="#131E29", foreground="#DDE6EB", muted="#7C8D9A"
        )
        self.startup_switch.pack(fill="x")
        if not self._is_frozen_exe():
            self.startup_switch.set_enabled(False)
            tk.Label(options_card.inner, text="自動起動登録はビルド済みEXEで利用できます。",
                     bg="#131E29", fg="#B39B71",
                     font=("Yu Gothic UI", 8)).pack(anchor="w", pady=(2, 0))

        # Persistent state feedback.
        self.status_panel = RoundedPanel(outer, height=62, fill="#101B25",
                                         border="#273B49", radius=20, inset=14)
        self.status_panel.pack(fill="x")
        status_row = tk.Frame(self.status_panel.inner, bg="#101B25")
        status_row.pack(fill="both", expand=True)
        self.status_dot = tk.Label(status_row, text="●", bg="#101B25",
                                   fg="#8CA4B4", font=("Segoe UI", 12))
        self.status_dot.pack(side="left", padx=(0, 9))
        self.status_label = tk.Label(status_row, textvariable=self.status,
                                     bg="#101B25", fg="#B8C8D2",
                                     font=("Yu Gothic UI", 9), anchor="w",
                                     justify="left", wraplength=640)
        self.status_label.pack(side="left", fill="both", expand=True)
        self.status.trace_add("write", self._refresh_status_style)
        self._refresh_status_style()

    def select_mode(self, mode: str):
        self.mode.set(mode)
        self._mode_changed()
        self._set_status(f"モードを「{mode}」に選択しました。適用するとWindowsに反映されます。")

    def _mode_changed(self, _event=None):
        for value, button in getattr(self, "mode_buttons", {}).items():
            button.set_selected(self.mode.get() == value)

    def _taskbar_transparency_changed(self, value: int):
        self.opacity.set(100 - int(value))
        self._set_status(f"背景の透明度を {value}% に調整中です。［適用する］で反映します。", "info")

    def _clock_transparency_changed(self, value: int):
        self.clock_opacity.set(100 - int(value))
        self._set_status(f"時計の透明度を {value}% に調整中です。［時計に適用］で反映します。", "info")

    def _icons_transparency_changed(self, value: int):
        self.icons_opacity.set(100 - int(value))
        self._set_status(f"アイコン領域の透明度を {value}% に調整中です。［アイコンに適用］で反映します。", "info")

    def _opacity_changed(self, _value=None):
        # Backward compatibility for older code paths.
        if hasattr(self, "taskbar_transparency"):
            self.taskbar_transparency.set(100 - int(self.opacity.get()))

    def _set_status(self, message: str, _kind: str | None = None):
        self.status.set(message)

    def _refresh_status_style(self, *_args):
        message = self.status.get()
        negative = ("検出できませんでした", "個別制御できません", "適用を拒否",
                    "変更できませんでした", "見つかりません", "エラー", "失敗", "対象外")
        positive = ("設定しました", "登録しました", "解除しました", "適用しました",
                    "標準状態に戻しました", "保存しました", "再適用しました", "完了")
        if any(term in message for term in negative):
            color = "#E0B8A8"
            dot = "#CA8D73"
        elif any(term in message for term in positive):
            color = "#C1D8C8"
            dot = "#8EB49A"
        elif "調整中" in message or "適用しています" in message:
            color = "#D3E1E8"
            dot = "#A7C4D4"
        else:
            color = "#B8C8D2"
            dot = "#8CA4B4"
        if hasattr(self, "status_label"):
            self.status_label.configure(fg=color)
            self.status_dot.configure(fg=dot)

    def _is_frozen_exe(self) -> bool:
        return sys.platform == "win32" and bool(getattr(sys, "frozen", False))

    def _startup_registered(self) -> bool:
        if not self._is_frozen_exe():
            return False
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, APP_RUN_KEY, 0, winreg.KEY_READ) as key:
                value, _kind = winreg.QueryValueEx(key, APP_RUN_VALUE)
            return bool(value)
        except OSError:
            return False

    def toggle_startup(self):
        enabled = bool(self.start_with_windows.get())
        if not self._is_frozen_exe():
            self.start_with_windows.set(False)
            messagebox.showinfo(APP_TITLE, "スタートアップ登録はビルド済みのEXEから設定してください。")
            return
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, APP_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                if enabled:
                    exe_path = os.path.abspath(sys.executable)
                    winreg.SetValueEx(key, APP_RUN_VALUE, 0, winreg.REG_SZ, f'"{exe_path}"')
                    message = "Windowsサインイン時の自動起動を登録しました。タスクマネージャーの「スタートアップ アプリ」で確認できます。"
                else:
                    try:
                        winreg.DeleteValue(key, APP_RUN_VALUE)
                    except FileNotFoundError:
                        pass
                    message = "Windowsサインイン時の自動起動登録を解除しました。"
            self.status.set(message)
        except OSError as exc:
            self.start_with_windows.set(not enabled)
            messagebox.showerror(APP_TITLE, f"スタートアップ登録を変更できませんでした。\n{exc}")

    def _save_current_settings(self):
        self.settings = {
            "taskbar_mode": self.mode.get(),
            "taskbar_opacity": int(self.opacity.get()),
            "clock_opacity": int(self.clock_opacity.get()),
            "icons_opacity": int(self.icons_opacity.get()),
            "auto_reapply": bool(self.auto_reapply.get()),
        }
        save_settings(self.settings)

    def _apply_saved_settings(self):
        ok, message = apply_taskbar_effect(self.last_mode, self.last_opacity)
        if self.last_mode == "通常に戻す":
            message = "保存済みの設定により、タスクバーを標準状態に戻しました。" if ok else message
        else:
            message = "保存済みのタスクバー効果を適用しました。" if ok else message
        # Apply item-specific transparency only if the user previously selected less than 100%.
        component_messages = []
        for component, variable in (("clock", self.clock_opacity), ("icons", self.icons_opacity)):
            if int(variable.get()) < 100:
                _success, item_message = self._set_component_opacity(component, int(variable.get()), show_status=False)
                component_messages.append(item_message)
        if component_messages:
            message += " " + " ".join(component_messages)
        self.status.set(message)

    def apply_taskbar(self):
        mode, opacity = self.mode.get(), int(self.opacity.get())
        self._set_status("タスクバーの設定を適用しています…")
        self.root.update_idletasks()
        ok, message = apply_taskbar_effect(mode, opacity)
        self._set_status(("✓ " if ok else "！ ") + message)
        if ok:
            self.last_mode, self.last_opacity = mode, opacity
            self._save_current_settings()
        else:
            messagebox.showwarning(APP_TITLE, message)

    def restore_taskbar(self):
        self.mode.set("通常に戻す")
        self._mode_changed()
        self._set_status("タスクバーを標準状態に戻しています…")
        self.root.update_idletasks()
        ok, message = apply_taskbar_effect("通常に戻す")
        self.last_mode = "通常に戻す"
        self._save_current_settings()
        self._set_status(("✓ " if ok else "！ ") + message)
        if not ok:
            messagebox.showwarning(APP_TITLE, message)

    def _set_component_opacity(self, component: str, opacity_percent: int, show_status: bool = True):
        if sys.platform != "win32":
            result = (False, "この機能はWindows専用です。")
        else:
            hwnd, class_name = find_component_window(component)
            if not hwnd:
                label = "時計" if component == "clock" else "アプリアイコン領域"
                result = (False, f"{label}を個別制御できません。このWindows 11では独立したウィンドウが公開されていない可能性があります。")
            else:
                getter = _window_long_function(True)
                setter = _window_long_function(False)
                if not getter or not setter:
                    result = (False, "ウィンドウの拡張スタイルを取得できません。")
                else:
                    hwnd_key = int(hwnd)
                    current_style = int(getter(hwnd, GWL_EXSTYLE))
                    original_style = self._component_original_styles.get(hwnd_key)
                    if opacity_percent >= 100:
                        if original_style is not None:
                            setter(hwnd, GWL_EXSTYLE, original_style)
                            self._component_original_styles.pop(hwnd_key, None)
                            self._component_names.pop(hwnd_key, None)
                        result = (True, f"{class_name}を不透明（標準表示）に戻しました。")
                    else:
                        if original_style is None:
                            if current_style & WS_EX_LAYERED:
                                result = (False, f"{class_name}は既にレイヤードウィンドウです。元の透明度を安全に復元できないため変更を見送りました。")
                                if show_status:
                                    self._set_status(result[1])
                                return result
                            original_style = current_style
                            self._component_original_styles[hwnd_key] = original_style
                            self._component_names[hwnd_key] = class_name
                        setter(hwnd, GWL_EXSTYLE, original_style | WS_EX_LAYERED)
                        user32.SetLayeredWindowAttributes.argtypes = [
                            wintypes.HWND, wintypes.COLORREF, wintypes.BYTE, wintypes.DWORD
                        ]
                        user32.SetLayeredWindowAttributes.restype = wintypes.BOOL
                        alpha = max(0, min(100, opacity_percent)) * 255 // 100
                        if user32.SetLayeredWindowAttributes(hwnd, 0, alpha, LWA_ALPHA):
                            result = (True, f"{class_name}に不透明度 {opacity_percent}% を設定しました。")
                        else:
                            setter(hwnd, GWL_EXSTYLE, original_style)
                            self._component_original_styles.pop(hwnd_key, None)
                            self._component_names.pop(hwnd_key, None)
                            result = (False, f"{class_name}への透明度設定をWindowsが拒否しました。")
        if show_status:
            self.status.set(result[1])
            if not result[0]:
                messagebox.showwarning(APP_TITLE, result[1])
        return result

    def apply_component(self, component: str):
        value = int(self.clock_opacity.get() if component == "clock" else self.icons_opacity.get())
        label = "時計" if component == "clock" else "アイコン領域"
        self._set_status(f"{label}の設定を適用しています…")
        self.root.update_idletasks()
        self._save_current_settings()
        ok, message = self._set_component_opacity(component, value, show_status=False)
        self._set_status(("✓ " if ok else "！ ") + message)
        if not ok:
            messagebox.showwarning(APP_TITLE, message)

    def _restore_all_component_styles(self):
        setter = _window_long_function(False)
        if not setter:
            return
        if user32:
            user32.IsWindow.argtypes = [wintypes.HWND]
            user32.IsWindow.restype = wintypes.BOOL
        for hwnd_value, old_style in list(self._component_original_styles.items()):
            hwnd = wintypes.HWND(hwnd_value)
            if user32 and user32.IsWindow(hwnd):
                setter(hwnd, GWL_EXSTYLE, old_style)
        self._component_original_styles.clear()
        self._component_names.clear()

    def _watch_explorer(self):
        current = find_taskbar()
        if current and current != self._last_hwnd and self.auto_reapply.get():
            apply_taskbar_effect(self.last_mode, self.last_opacity)
            for component, variable in (("clock", self.clock_opacity), ("icons", self.icons_opacity)):
                if int(variable.get()) < 100:
                    self._set_component_opacity(component, int(variable.get()), show_status=False)
            self._set_status("Explorerの再起動を検出し、保存済み設定の再適用を試みました。")
        self._last_hwnd = current
        self.root.after(2000, self._watch_explorer)

    def close(self):
        # Do not leave child HWNDs layered after the app exits. Taskbar background
        # accent effects are kept as applied; item-level effects are restored.
        self._restore_all_component_styles()
        self.root.destroy()


def bundled_path(relative: str) -> Path:
    # PyInstaller one-file builds extract bundled resources to _MEIPASS.
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / relative


def main():
    if sys.platform != "win32":
        print("このアプリはWindows 11専用です。")
        raise SystemExit(1)
    root = tk.Tk()
    try:
        root.iconbitmap(default=str(bundled_path("assets/windows-ui-transparency.ico")))
    except (tk.TclError, OSError):
        # The EXE still contains the icon resource even when Tk cannot load it.
        pass
    TransparencyApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
