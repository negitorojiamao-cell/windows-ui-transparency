from __future__ import annotations

import ctypes
import sys
import tkinter as tk
from tkinter import ttk, messagebox
from ctypes import wintypes

APP_TITLE = "Windows UI Transparency"
WCA_ACCENT_POLICY = 19
ACCENT_DISABLED = 0
ACCENT_ENABLE_TRANSPARENTGRADIENT = 2
ACCENT_ENABLE_BLURBEHIND = 3
ACCENT_ENABLE_ACRYLICBLURBEHIND = 4

user32 = ctypes.windll.user32 if sys.platform == "win32" else None


class ACCENT_POLICY(ctypes.Structure):
    _fields_ = [("AccentState", ctypes.c_int), ("AccentFlags", ctypes.c_int),
                ("GradientColor", ctypes.c_uint), ("AnimationId", ctypes.c_int)]


class WINDOWCOMPOSITIONATTRIBUTEDATA(ctypes.Structure):
    _fields_ = [("Attribute", ctypes.c_int), ("Data", ctypes.c_void_p),
                ("SizeOfData", ctypes.c_size_t)]


def find_taskbar():
    return user32.FindWindowW("Shell_TrayWnd", None) if user32 else None


def apply_taskbar_effect(mode: str, opacity: int = 78) -> tuple[bool, str]:
    """Apply a taskbar accent effect using a Windows API that is not officially supported."""
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
        WCA_ACCENT_POLICY, ctypes.cast(ctypes.pointer(policy), ctypes.c_void_p),
        ctypes.sizeof(policy))
    setter.argtypes = [wintypes.HWND, ctypes.POINTER(WINDOWCOMPOSITIONATTRIBUTEDATA)]
    setter.restype = wintypes.BOOL
    if setter(hwnd, ctypes.byref(data)):
        return True, f"タスクバーを「{mode}」に設定しました。"
    return False, "Windowsが効果の適用を拒否しました。「通常に戻す」を試してください。"


class TransparencyApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("560x510")
        self.root.minsize(520, 470)
        self.root.configure(bg="#10151f")
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.last_mode = "アクリル風"
        self.last_opacity = 78
        self.auto_reapply = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="準備完了。モードを選んで適用してください。")
        self._build_ui()
        self._last_hwnd = find_taskbar()
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
        tk.Label(outer, text="タスクバーの背景を透明・ぼかし・アクリル風に変更します。",
                 bg="#10151f", fg="#aab6c8", font=("Yu Gothic UI", 10)).pack(anchor="w")

        card = tk.Frame(outer, bg="#1b2433", padx=16, pady=14)
        card.pack(fill="x", pady=(18, 12))
        tk.Label(card, text="タスクバーの表示モード", bg="#1b2433", fg="#e8edf5",
                 font=("Yu Gothic UI", 11, "bold")).pack(anchor="w")
        self.mode = tk.StringVar(value="アクリル風")
        combo = ttk.Combobox(card, textvariable=self.mode, state="readonly",
                             values=("透明", "ぼかし", "アクリル風", "通常に戻す"))
        combo.pack(fill="x", pady=(8, 12))
        combo.bind("<<ComboboxSelected>>", self._mode_changed)

        self.opacity_label = tk.Label(card, text="色の濃さ: 78%", bg="#1b2433", fg="#d5deea",
                                      font=("Yu Gothic UI", 10))
        self.opacity_label.pack(anchor="w")
        self.opacity = tk.IntVar(value=78)
        self.scale = tk.Scale(card, from_=5, to=100, orient="horizontal", variable=self.opacity,
                              command=self._opacity_changed, bg="#1b2433", fg="#e8edf5",
                              troughcolor="#34445c", highlightthickness=0, bd=0,
                              activebackground="#7dd3fc", length=470)
        self.scale.pack(fill="x")
        tk.Label(card, text="※ 色の濃さはモードやWindowsのビルドにより見え方が変わります。",
                 bg="#1b2433", fg="#9caac0", wraplength=475, justify="left",
                 font=("Yu Gothic UI", 9)).pack(anchor="w", pady=(4, 0))

        buttons = tk.Frame(outer, bg="#10151f")
        buttons.pack(fill="x", pady=(2, 10))
        tk.Button(buttons, text="適用", command=self.apply, bg="#0284c7", fg="white",
                  activebackground="#0369a1", activeforeground="white", relief="flat",
                  font=("Yu Gothic UI", 11, "bold"), padx=18, pady=9, cursor="hand2").pack(side="left")
        tk.Button(buttons, text="通常に戻す", command=self.restore, bg="#334155", fg="white",
                  activebackground="#475569", activeforeground="white", relief="flat",
                  font=("Yu Gothic UI", 10), padx=14, pady=9, cursor="hand2").pack(side="left", padx=8)
        ttk.Checkbutton(outer, text="Explorer再起動後に効果を再適用する",
                        variable=self.auto_reapply).pack(anchor="w", pady=(4, 10))
        tk.Label(outer, textvariable=self.status, bg="#10151f", fg="#a7f3d0",
                 wraplength=500, justify="left", font=("Yu Gothic UI", 9)).pack(anchor="w")
        tk.Label(outer, text="対象: タスクバー背景 / 対象外: すべてのアプリの枠・スタートメニュー等",
                 bg="#10151f", fg="#8290a5", wraplength=500, justify="left",
                 font=("Yu Gothic UI", 9)).pack(anchor="w", pady=(10, 0))

    def _mode_changed(self, _event=None):
        self.scale.configure(state="disabled" if self.mode.get() == "通常に戻す" else "normal")

    def _opacity_changed(self, _value=None):
        self.opacity_label.configure(text=f"色の濃さ: {self.opacity.get()}%")

    def apply(self):
        mode, opacity = self.mode.get(), int(self.opacity.get())
        ok, message = apply_taskbar_effect(mode, opacity)
        self.status.set(message)
        if ok:
            self.last_mode, self.last_opacity = mode, opacity
        else:
            messagebox.showwarning(APP_TITLE, message)

    def restore(self):
        ok, message = apply_taskbar_effect("通常に戻す")
        self.status.set(message)
        if not ok:
            messagebox.showwarning(APP_TITLE, message)

    def _watch_explorer(self):
        current = find_taskbar()
        if current and current != self._last_hwnd and self.auto_reapply.get():
            apply_taskbar_effect(self.last_mode, self.last_opacity)
            self.status.set("Explorerの再起動を検出し、選択中の効果を再適用しました。")
        self._last_hwnd = current
        self.root.after(2000, self._watch_explorer)

    def close(self):
        self.root.destroy()


def main():
    if sys.platform != "win32":
        print("このアプリはWindows 11専用です。")
        raise SystemExit(1)
    root = tk.Tk()
    TransparencyApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
