from __future__ import annotations

import ctypes
import json
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
        state, color = ACCENT_ENABLE_BLURBEHIND, 0xCC202020
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
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TCheckbutton", background="#10151f", foreground="#e8edf5")
        style.map("TCheckbutton", background=[("active", "#10151f")])

        outer = tk.Frame(self.root, bg="#10151f", padx=22, pady=18)
        outer.pack(fill="both", expand=True)
        tk.Label(outer, text="WINDOWS UI TRANSPARENCY", bg="#10151f", fg="#7dd3fc",
                 font=("Segoe UI", 10, "bold")).pack(anchor="w")
        tk.Label(outer, text="Windows 11 の表示をカスタマイズ", bg="#10151f", fg="#f3f6fb",
                 font=("Yu Gothic UI", 19, "bold")).pack(anchor="w", pady=(5, 2))
        tk.Label(outer, text="背景・時計・タスクバーアイコン領域を、対応している範囲で個別調整します。",
                 bg="#10151f", fg="#aab6c8", font=("Yu Gothic UI", 10),
                 wraplength=630, justify="left").pack(anchor="w")

        task_card = tk.Frame(outer, bg="#1b2433", padx=15, pady=12)
        task_card.pack(fill="x", pady=(13, 10))
        tk.Label(task_card, text="1. タスクバー背景", bg="#1b2433", fg="#e8edf5",
                 font=("Yu Gothic UI", 11, "bold")).pack(anchor="w")
        self.mode = tk.StringVar(value=self.last_mode)
        combo = ttk.Combobox(task_card, textvariable=self.mode, state="readonly",
                             values=("透明", "ぼかし", "アクリル風", "通常に戻す"))
        combo.pack(fill="x", pady=(6, 8))
        combo.bind("<<ComboboxSelected>>", self._mode_changed)
        self.opacity_label = tk.Label(task_card, text=f"色の濃さ: {self.last_opacity}%",
                                      bg="#1b2433", fg="#d5deea", font=("Yu Gothic UI", 9))
        self.opacity_label.pack(anchor="w")
        self.opacity = tk.IntVar(value=self.last_opacity)
        self.scale = tk.Scale(task_card, from_=0, to=100, orient="horizontal", variable=self.opacity,
                              command=self._opacity_changed, bg="#1b2433", fg="#e8edf5",
                              troughcolor="#34445c", highlightthickness=0, bd=0,
                              activebackground="#7dd3fc", length=600)
        self.scale.pack(fill="x")
        buttons = tk.Frame(task_card, bg="#1b2433")
        buttons.pack(fill="x", pady=(4, 0))
        tk.Button(buttons, text="背景に適用", command=self.apply_taskbar, bg="#0284c7", fg="white",
                  activebackground="#0369a1", activeforeground="white", relief="flat",
                  font=("Yu Gothic UI", 10, "bold"), padx=14, pady=7, cursor="hand2").pack(side="left")
        tk.Button(buttons, text="背景を標準に戻す", command=self.restore_taskbar, bg="#334155", fg="white",
                  activebackground="#475569", activeforeground="white", relief="flat",
                  font=("Yu Gothic UI", 9), padx=12, pady=7, cursor="hand2").pack(side="left", padx=8)
        tk.Label(task_card, text="※ 背景効果はWindowsのビルドによって効き方が異なります。",
                 bg="#1b2433", fg="#9caac0", font=("Yu Gothic UI", 9)).pack(anchor="w", pady=(5, 0))

        self.clock_opacity = tk.IntVar(value=self.settings["clock_opacity"])
        self.icons_opacity = tk.IntVar(value=self.settings["icons_opacity"])
        self.clock_opacity_label = tk.Label(outer, text=self._component_label("時計", self.clock_opacity.get()),
                                            bg="#10151f", fg="#e8edf5", font=("Yu Gothic UI", 10, "bold"))
        self.clock_opacity_label.pack(anchor="w", pady=(2, 0))
        clock_row = tk.Frame(outer, bg="#10151f")
        clock_row.pack(fill="x")
        tk.Scale(clock_row, from_=0, to=100, orient="horizontal", variable=self.clock_opacity,
                 command=lambda _v: self._update_component_label("clock"),
                 bg="#10151f", fg="#d5deea", troughcolor="#34445c", highlightthickness=0, bd=0,
                 activebackground="#7dd3fc").pack(side="left", fill="x", expand=True)
        tk.Button(clock_row, text="時計に適用", command=lambda: self.apply_component("clock"),
                  bg="#334155", fg="white", activebackground="#475569", relief="flat",
                  font=("Yu Gothic UI", 9), padx=10, pady=5).pack(side="left", padx=(8, 0))

        self.icons_opacity_label = tk.Label(outer, text=self._component_label("アプリアイコン領域", self.icons_opacity.get()),
                                            bg="#10151f", fg="#e8edf5", font=("Yu Gothic UI", 10, "bold"))
        self.icons_opacity_label.pack(anchor="w", pady=(7, 0))
        icons_row = tk.Frame(outer, bg="#10151f")
        icons_row.pack(fill="x")
        tk.Scale(icons_row, from_=0, to=100, orient="horizontal", variable=self.icons_opacity,
                 command=lambda _v: self._update_component_label("icons"),
                 bg="#10151f", fg="#d5deea", troughcolor="#34445c", highlightthickness=0, bd=0,
                 activebackground="#7dd3fc").pack(side="left", fill="x", expand=True)
        tk.Button(icons_row, text="アイコン領域に適用", command=lambda: self.apply_component("icons"),
                  bg="#334155", fg="white", activebackground="#475569", relief="flat",
                  font=("Yu Gothic UI", 9), padx=10, pady=5).pack(side="left", padx=(8, 0))
        tk.Label(outer, text="個別表示の注意: 時計は TrayClockWClass、アプリアイコンは MSTaskListWClass が検出された場合のみ調整を試みます。後者はアイコン1個ずつではなく、グループ全体です。新しいWindows 11では共有XAML描画のため対象が見つからない場合があります。",
                 bg="#10151f", fg="#9caac0", wraplength=630, justify="left",
                 font=("Yu Gothic UI", 9)).pack(anchor="w", pady=(3, 8))

        options = tk.Frame(outer, bg="#1b2433", padx=14, pady=10)
        options.pack(fill="x", pady=(4, 9))
        ttk.Checkbutton(options, text="Explorer再起動後に設定を再適用する",
                        variable=self.auto_reapply, command=self._save_current_settings).pack(anchor="w")
        self.startup_check = ttk.Checkbutton(
            options, text="Windowsへのサインイン時に起動（タスクマネージャーのスタートアップアプリに登録）",
            variable=self.start_with_windows, command=self.toggle_startup)
        self.startup_check.pack(anchor="w", pady=(5, 0))
        if not self._is_frozen_exe():
            self.startup_check.configure(state="disabled")
            tk.Label(options, text="※ スタートアップ登録はEXE版でのみ使用できます。GitHub ActionsでビルドしたEXEから設定してください。",
                     bg="#1b2433", fg="#fbbf24", wraplength=600, justify="left",
                     font=("Yu Gothic UI", 9)).pack(anchor="w", pady=(3, 0))
        tk.Label(options, text="EXEの場所を移動・削除すると登録先が無効になります。解除してから移動してください。",
                 bg="#1b2433", fg="#9caac0", wraplength=600, justify="left",
                 font=("Yu Gothic UI", 9)).pack(anchor="w", pady=(3, 0))

        tk.Label(outer, textvariable=self.status, bg="#10151f", fg="#a7f3d0",
                 wraplength=630, justify="left", font=("Yu Gothic UI", 9)).pack(anchor="w", pady=(2, 0))
        tk.Label(outer, text="制限: スタートメニュー・通知センター等の個別透明化には対応していません。Windows内部APIは将来の更新で動作が変わる場合があります。",
                 bg="#10151f", fg="#8290a5", wraplength=630, justify="left",
                 font=("Yu Gothic UI", 9)).pack(anchor="w", pady=(5, 0))

    @staticmethod
    def _component_label(name: str, value: int) -> str:
        return f"{name}の不透明度: {value}%（0%=透明 / 100%=不透明）"

    def _update_component_label(self, component: str):
        if component == "clock":
            self.clock_opacity_label.configure(text=self._component_label("時計", self.clock_opacity.get()))
        else:
            self.icons_opacity_label.configure(text=self._component_label("アプリアイコン領域", self.icons_opacity.get()))

    def _mode_changed(self, _event=None):
        self.scale.configure(state="disabled" if self.mode.get() == "通常に戻す" else "normal")

    def _opacity_changed(self, _value=None):
        self.opacity_label.configure(text=f"色の濃さ: {self.opacity.get()}%")

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
        ok, message = apply_taskbar_effect(mode, opacity)
        self.status.set(message)
        if ok:
            self.last_mode, self.last_opacity = mode, opacity
            self._save_current_settings()
        else:
            messagebox.showwarning(APP_TITLE, message)

    def restore_taskbar(self):
        self.mode.set("通常に戻す")
        self._mode_changed()
        ok, message = apply_taskbar_effect("通常に戻す")
        self.last_mode = "通常に戻す"
        self._save_current_settings()
        self.status.set(message)
        if not ok:
            messagebox.showwarning(APP_TITLE, message)

    def _set_component_opacity(self, component: str, opacity_percent: int, show_status: bool = True):
        if sys.platform != "win32":
            result = (False, "この機能はWindows専用です。")
        else:
            hwnd, class_name = find_component_window(component)
            if not hwnd:
                label = "時計" if component == "clock" else "アプリアイコン領域"
                expected = "TrayClockWClass" if component == "clock" else "MSTaskListWClass"
                result = (False, f"{label}を個別のウィンドウとして検出できませんでした（{expected}）。このWindows 11ビルドでは共有XAML/DirectComposition描画のため個別制御できない可能性があります。")
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
                                    self.status.set(result[1])
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
        self._save_current_settings()
        self._set_component_opacity(component, value)

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
            self.status.set("Explorerの再起動を検出し、保存済み設定の再適用を試みました。")
        self._last_hwnd = current
        self.root.after(2000, self._watch_explorer)

    def close(self):
        # Do not leave child HWNDs layered after the app exits. Taskbar background
        # accent effects are kept as applied; item-level effects are restored.
        self._restore_all_component_styles()
        self.root.destroy()


def main():
    if sys.platform != "win32":
        print("このアプリはWindows専用です。")
        raise SystemExit(1)
    root = tk.Tk()
    TransparencyApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
