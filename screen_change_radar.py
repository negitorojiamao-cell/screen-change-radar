import os
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageChops, ImageGrab, ImageTk

APP_NAME = "Screen Change Radar"
CAPTURE_DIR = Path.home() / "Pictures" / "ScreenChangeRadar"


class ScreenChangeRadar:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("760x590")
        self.root.minsize(680, 520)

        self.running = False
        self.previous_image = None
        self.stop_event = threading.Event()
        self.last_alert_time = 0.0
        self.capture_count = 0
        # These plain Python values are copied from Tk variables on the UI thread.
        self.active_interval = 1
        self.active_pixel_threshold = 28
        self.active_area_threshold = 1.0
        self.active_save_images = True

        self.interval = tk.IntVar(value=1)
        self.pixel_threshold = tk.IntVar(value=28)
        self.area_threshold = tk.DoubleVar(value=1.0)
        self.save_images = tk.BooleanVar(value=True)

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Screen Change Radar", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(outer, text="画面の変化を監視し、変化が大きいと通知・画像保存します。").pack(anchor="w", pady=(2, 12))

        settings = ttk.LabelFrame(outer, text="監視設定", padding=10)
        settings.pack(fill="x")
        row1 = ttk.Frame(settings)
        row1.pack(fill="x", pady=4)
        ttk.Label(row1, text="確認間隔").pack(side="left")
        ttk.Spinbox(row1, from_=1, to=60, textvariable=self.interval, width=5).pack(side="left", padx=(8, 4))
        ttk.Label(row1, text="秒").pack(side="left")
        ttk.Label(row1, text="画素差しきい値").pack(side="left", padx=(24, 8))
        ttk.Scale(row1, from_=5, to=80, variable=self.pixel_threshold, orient="horizontal").pack(side="left", fill="x", expand=True)
        self.pixel_label = ttk.Label(row1, width=4, text="28")
        self.pixel_label.pack(side="left", padx=(8, 0))
        self.pixel_threshold.trace_add("write", self._update_labels)

        row2 = ttk.Frame(settings)
        row2.pack(fill="x", pady=4)
        ttk.Label(row2, text="画面の変化率しきい値").pack(side="left")
        ttk.Scale(row2, from_=0.1, to=20, variable=self.area_threshold, orient="horizontal").pack(side="left", fill="x", expand=True, padx=(8, 8))
        self.area_label = ttk.Label(row2, width=8, text="1.0%")
        self.area_label.pack(side="left")
        self.area_threshold.trace_add("write", self._update_labels)
        ttk.Checkbutton(settings, text="変化前・変化後の画像を保存する", variable=self.save_images).pack(anchor="w", pady=(6, 0))

        controls = ttk.Frame(outer)
        controls.pack(fill="x", pady=12)
        self.start_button = ttk.Button(controls, text="監視開始", command=self.start)
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(controls, text="監視停止", command=self.stop, state="disabled")
        self.stop_button.pack(side="left", padx=8)
        ttk.Button(controls, text="保存フォルダーを開く", command=self.open_capture_folder).pack(side="left", padx=(8, 0))

        status_frame = ttk.LabelFrame(outer, text="状態", padding=10)
        status_frame.pack(fill="x")
        self.status_var = tk.StringVar(value="停止中")
        ttk.Label(status_frame, textvariable=self.status_var, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.stats_var = tk.StringVar(value="キャプチャ: 0回")
        ttk.Label(status_frame, textvariable=self.stats_var).pack(anchor="w", pady=(4, 0))

        preview_frame = ttk.LabelFrame(outer, text="直近の監視画像（縮小表示）", padding=8)
        preview_frame.pack(fill="both", expand=True, pady=(12, 0))
        self.preview_label = ttk.Label(preview_frame, text="監視を開始すると、ここに画面が表示されます。", anchor="center")
        self.preview_label.pack(fill="both", expand=True)

        log_frame = ttk.LabelFrame(outer, text="検知ログ", padding=8)
        log_frame.pack(fill="x", pady=(12, 0))
        self.log = tk.Text(log_frame, height=5, wrap="word", state="disabled")
        self.log.pack(fill="x")

    def _update_labels(self, *_):
        self.pixel_label.configure(text=str(int(self.pixel_threshold.get())))
        self.area_label.configure(text=f"{self.area_threshold.get():.1f}%")

    def _write_log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        def append():
            if not self.root.winfo_exists():
                return
            self.log.configure(state="normal")
            self.log.insert("end", f"[{timestamp}] {message}\n")
            self.log.see("end")
            self.log.configure(state="disabled")
        try:
            self.root.after(0, append)
        except tk.TclError:
            pass

    def start(self):
        if self.running:
            return
        try:
            interval = int(self.interval.get())
            if interval < 1 or interval > 60:
                raise ValueError
            pixel_threshold = int(self.pixel_threshold.get())
            area_threshold = float(self.area_threshold.get())
            if not 5 <= pixel_threshold <= 80 or not 0.1 <= area_threshold <= 20:
                raise ValueError
        except (ValueError, tk.TclError):
            messagebox.showerror("設定エラー", "確認間隔は1～60秒、画素差は5～80、変化率は0.1～20%で設定してください。")
            return

        self.active_interval = interval
        self.active_pixel_threshold = pixel_threshold
        self.active_area_threshold = area_threshold
        self.active_save_images = bool(self.save_images.get())
        self.running = True
        self.stop_event.clear()
        self.previous_image = None
        self.capture_count = 0
        self.last_alert_time = 0.0
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.status_var.set("監視中：最初の画面を基準として取得しています…")
        self._write_log("監視を開始しました。設定変更は次回の監視開始時に反映されます。")
        threading.Thread(target=self._monitor_loop, daemon=True).start()

    def stop(self):
        if not self.running:
            return
        self.running = False
        self.stop_event.set()
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.status_var.set("停止中")
        self._write_log("監視を停止しました。")

    def _monitor_loop(self):
        while not self.stop_event.is_set():
            started = time.monotonic()
            try:
                image = ImageGrab.grab(all_screens=True).convert("RGB")
                self.capture_count += 1
                self.root.after(0, self._show_preview, image.copy())
                self.root.after(0, self.stats_var.set, f"キャプチャ: {self.capture_count}回")

                if self.previous_image is None or self.previous_image.size != image.size:
                    self.previous_image = image
                    self._write_log(f"基準画面を取得しました（{image.width}×{image.height}）。")
                else:
                    area = self._changed_percent(self.previous_image, image)
                    if area >= self.active_area_threshold:
                        self._handle_change(self.previous_image, image, area)
                    self.previous_image = image
            except Exception as exc:
                self._write_log(f"画面取得エラー: {exc}")
                try:
                    self.root.after(0, self.status_var.set, f"画面取得エラー: {exc}")
                except tk.TclError:
                    break

            remaining = max(0.1, self.active_interval - (time.monotonic() - started))
            self.stop_event.wait(remaining)

    def _changed_percent(self, old_image, new_image):
        # Compare quarter-size grayscale images for speed; save full-resolution captures.
        size = (max(1, old_image.width // 4), max(1, old_image.height // 4))
        old_small = old_image.resize(size, Image.Resampling.BILINEAR).convert("L")
        new_small = new_image.resize(size, Image.Resampling.BILINEAR).convert("L")
        diff = ImageChops.difference(old_small, new_small)
        histogram = diff.histogram()
        changed_pixels = sum(histogram[self.active_pixel_threshold + 1:])
        total_pixels = size[0] * size[1]
        return changed_pixels / total_pixels * 100.0 if total_pixels else 0.0

    def _handle_change(self, before, after, area):
        now = time.monotonic()
        if now - self.last_alert_time < 2.0:
            return
        self.last_alert_time = now
        self._write_log(f"画面の変化を検知しました：変化率 約{area:.2f}%")
        try:
            self.root.after(0, self._show_alert_status, area)
            self.root.after(0, self.root.bell)
        except tk.TclError:
            pass

        if self.active_save_images:
            try:
                CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                before_path = CAPTURE_DIR / f"{stamp}_before.png"
                after_path = CAPTURE_DIR / f"{stamp}_after.png"
                before.save(before_path)
                after.save(after_path)
                self._write_log(f"画像保存: {before_path.name} / {after_path.name}")
            except Exception as exc:
                self._write_log(f"画像保存エラー: {exc}")

    def _show_alert_status(self, area):
        if self.root.winfo_exists():
            self.status_var.set(f"変化を検知！ 約{area:.2f}%")

    def _show_preview(self, image):
        if not self.root.winfo_exists():
            return
        image.thumbnail((680, 190))
        photo = ImageTk.PhotoImage(image)
        self.preview_label.configure(image=photo, text="")
        self.preview_label.image = photo

    def open_capture_folder(self):
        CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(CAPTURE_DIR))
        except Exception as exc:
            messagebox.showerror("フォルダーを開けません", str(exc))

    def _on_close(self):
        self.stop_event.set()
        self.running = False
        self.root.destroy()


def main():
    root = tk.Tk()
    try:
        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")
    except Exception:
        pass
    ScreenChangeRadar(root)
    root.mainloop()


if __name__ == "__main__":
    main()
