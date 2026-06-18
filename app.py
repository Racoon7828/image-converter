import re
import sys
import threading
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image, ImageTk

from converter import SUPPORTED_INPUT, SUPPORTED_OUTPUT, convert_image, get_rembg_session

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

_EXT_DISPLAY = "  ".join(e.lstrip('.').upper() for e in sorted(SUPPORTED_INPUT))


class FileItem(ctk.CTkFrame):
    def __init__(self, parent, path: str, on_remove, on_preview, row: int):
        super().__init__(parent, fg_color=("gray88", "gray22"), corner_radius=6)
        self.grid(row=row, column=0, sticky="ew", pady=2)
        self.grid_columnconfigure(0, weight=1)

        name = Path(path).name
        ext = Path(path).suffix.lower().lstrip('.')

        ctk.CTkLabel(self, text=f"[{ext.upper()}]", width=45,
                     font=ctk.CTkFont(size=11), text_color=("gray50", "gray60"),
                     anchor="w").grid(row=0, column=0, padx=(8, 2), pady=5, sticky="w")

        name_lbl = ctk.CTkLabel(self, text=name, anchor="w",
                                 font=ctk.CTkFont(size=12), cursor="hand2")
        name_lbl.grid(row=0, column=1, sticky="ew", padx=4, pady=5)
        name_lbl.bind("<Button-1>", lambda _: on_preview(path))

        ctk.CTkButton(self, text="✕", width=26, height=26,
                      fg_color="transparent", hover_color=("gray70", "gray40"),
                      command=lambda: on_remove(path)).grid(row=0, column=2, padx=6)

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("이미지 변환기")
        self.geometry("1100x620")
        self.minsize(900, 500)

        self._files: list[str] = []
        self._file_widgets: list[FileItem] = []
        self._converting = False
        self._output_dir: str | None = None

        self._build_ui()

    # ── UI 빌드 ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=3)
        self.grid_columnconfigure(2, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_toolbar()
        self._build_file_list()
        self._build_preview()
        self._build_settings()
        self._build_bottom_bar()

    def _build_toolbar(self):
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=0, column=0, columnspan=3, sticky="ew", padx=12, pady=(12, 0))

        ctk.CTkButton(bar, text="+ 파일 추가", width=120, command=self._add_files).pack(side="left", padx=(0, 8))
        ctk.CTkButton(bar, text="폴더 추가", width=110, command=self._add_folder).pack(side="left", padx=(0, 8))
        ctk.CTkButton(bar, text="전체 삭제", width=90,
                      fg_color="transparent", border_width=1,
                      command=self._clear_files).pack(side="left")

        ctk.CTkLabel(bar, text=f"지원: {_EXT_DISPLAY}",
                     font=ctk.CTkFont(size=11), text_color="gray").pack(side="right")

    def _build_file_list(self):
        frame = ctk.CTkFrame(self)
        frame.grid(row=1, column=0, sticky="nsew", padx=(12, 5), pady=10)
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(frame, text="파일 목록",
                     font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 4))

        self._list_scroll = ctk.CTkScrollableFrame(frame)
        self._list_scroll.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))
        self._list_scroll.grid_columnconfigure(0, weight=1)

        self._empty_label = ctk.CTkLabel(self._list_scroll,
                                          text="파일을 추가하거나 폴더를 선택하세요",
                                          text_color="gray")
        self._empty_label.grid(row=0, column=0, pady=30)

    def _build_preview(self):
        frame = ctk.CTkFrame(self)
        frame.grid(row=1, column=1, sticky="nsew", padx=5, pady=10)
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(frame, text="미리보기",
                     font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 4))

        self._preview_lbl = ctk.CTkLabel(frame, text="파일 이름을 클릭하면\n미리보기가 표시됩니다",
                                          text_color="gray", image=None)
        self._preview_lbl.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))
        self._preview_photo = None

    def _build_settings(self):
        frame = ctk.CTkFrame(self)
        frame.grid(row=1, column=2, sticky="nsew", padx=(5, 12), pady=10)
        frame.grid_columnconfigure(0, weight=1)

        row = 0

        ctk.CTkLabel(frame, text="변환 설정",
                     font=ctk.CTkFont(weight="bold")).grid(row=row, column=0, sticky="w", padx=16, pady=(16, 8))
        row += 1

        # 출력 포맷
        ctk.CTkLabel(frame, text="출력 포맷").grid(row=row, column=0, sticky="w", padx=16)
        row += 1
        self._fmt_var = ctk.StringVar(value="PNG")
        ctk.CTkOptionMenu(frame, values=SUPPORTED_OUTPUT,
                          variable=self._fmt_var,
                          command=self._on_format_change).grid(row=row, column=0, sticky="ew", padx=16, pady=(2, 12))
        row += 1

        # 품질 슬라이더
        self._quality_lbl = ctk.CTkLabel(frame, text="품질: 85%")
        self._quality_lbl.grid(row=row, column=0, sticky="w", padx=16)
        row += 1
        self._quality_slider = ctk.CTkSlider(frame, from_=1, to=100, command=self._on_quality_change)
        self._quality_slider.set(85)
        self._quality_slider.grid(row=row, column=0, sticky="ew", padx=16, pady=(2, 14))
        row += 1

        # 구분선
        ctk.CTkFrame(frame, height=1, fg_color=("gray75", "gray35")).grid(
            row=row, column=0, sticky="ew", padx=12, pady=(0, 12))
        row += 1

        # 크기 조절
        ctk.CTkLabel(frame, text="크기 조절 (선택 사항)").grid(row=row, column=0, sticky="w", padx=16)
        row += 1

        size_row = ctk.CTkFrame(frame, fg_color="transparent")
        size_row.grid(row=row, column=0, sticky="ew", padx=16, pady=(4, 0))
        size_row.grid_columnconfigure((1, 3), weight=1)
        row += 1

        ctk.CTkLabel(size_row, text="W", width=14).grid(row=0, column=0)
        self._w_entry = ctk.CTkEntry(size_row, placeholder_text="너비 px")
        self._w_entry.grid(row=0, column=1, padx=(4, 10))
        ctk.CTkLabel(size_row, text="H", width=14).grid(row=0, column=2)
        self._h_entry = ctk.CTkEntry(size_row, placeholder_text="높이 px")
        self._h_entry.grid(row=0, column=3, padx=(4, 0))

        self._aspect_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(frame, text="비율 유지", variable=self._aspect_var).grid(
            row=row, column=0, sticky="w", padx=16, pady=(8, 14))
        row += 1

        # 구분선
        ctk.CTkFrame(frame, height=1, fg_color=("gray75", "gray35")).grid(
            row=row, column=0, sticky="ew", padx=12, pady=(0, 12))
        row += 1

        # 배경 제거
        self._remove_bg_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(frame, text="배경 제거 (AI)",
                        variable=self._remove_bg_var,
                        command=self._on_remove_bg_change).grid(
            row=row, column=0, sticky="w", padx=16, pady=(0, 4))
        row += 1
        self._bg_warn_lbl = ctk.CTkLabel(
            frame, text="⚠ PNG/WebP/SVG 포맷 권장",
            font=ctk.CTkFont(size=11), text_color=("orange", "orange"))
        self._bg_warn_lbl.grid(row=row, column=0, sticky="w", padx=28, pady=(0, 10))
        self._bg_warn_lbl.grid_remove()
        row += 1

        # 구분선
        ctk.CTkFrame(frame, height=1, fg_color=("gray75", "gray35")).grid(
            row=row, column=0, sticky="ew", padx=12, pady=(0, 12))
        row += 1

        # 출력 폴더
        ctk.CTkLabel(frame, text="출력 폴더").grid(row=row, column=0, sticky="w", padx=16)
        row += 1

        dir_row = ctk.CTkFrame(frame, fg_color="transparent")
        dir_row.grid(row=row, column=0, sticky="ew", padx=16, pady=(4, 0))
        dir_row.grid_columnconfigure(0, weight=1)
        row += 1

        self._dir_var = ctk.StringVar(value="원본 파일과 같은 폴더")
        ctk.CTkLabel(dir_row, textvariable=self._dir_var,
                     anchor="w", font=ctk.CTkFont(size=11),
                     text_color=("gray40", "gray70"), wraplength=160).grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(dir_row, text="선택", width=48,
                      command=self._select_output_dir).grid(row=0, column=1, padx=(6, 0))

        self._update_quality_state()

    def _build_bottom_bar(self):
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=2, column=0, columnspan=3, sticky="ew", padx=12, pady=(0, 12))
        bar.grid_columnconfigure(1, weight=1)

        self._convert_btn = ctk.CTkButton(
            bar, text="▶  변환 시작", width=150, height=42,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._start_conversion)
        self._convert_btn.grid(row=0, column=0, padx=(0, 16))

        right = ctk.CTkFrame(bar, fg_color="transparent")
        right.grid(row=0, column=1, sticky="ew")
        right.grid_columnconfigure(0, weight=1)

        self._status_lbl = ctk.CTkLabel(right, text="파일을 추가하세요", text_color="gray")
        self._status_lbl.grid(row=0, column=0, sticky="w")

        self._progress = ctk.CTkProgressBar(right)
        self._progress.set(0)
        self._progress.grid(row=1, column=0, sticky="ew", pady=(6, 0))

    # ── 파일 관리 ──────────────────────────────────────────────────────────────

    def _add_files(self):
        exts = " ".join(f"*{e}" for e in sorted(SUPPORTED_INPUT))
        paths = filedialog.askopenfilenames(
            title="이미지 파일 선택",
            filetypes=[("이미지 파일", exts), ("모든 파일", "*.*")])
        for p in paths:
            if p not in self._files:
                self._files.append(p)
                self._append_widget(p)
        self._refresh_status()

    def _add_folder(self):
        folder = filedialog.askdirectory(title="폴더 선택")
        if not folder:
            return
        added = 0
        for path in sorted(Path(folder).iterdir()):
            if path.is_file() and path.suffix.lower() in SUPPORTED_INPUT:
                s = str(path)
                if s not in self._files:
                    self._files.append(s)
                    self._append_widget(s)
                    added += 1
        if added == 0:
            messagebox.showinfo("알림", "해당 폴더에 지원 이미지가 없습니다.")
        self._refresh_status()

    def _remove_file(self, path: str):
        if path in self._files:
            self._files.remove(path)
        self._rebuild_widgets()
        self._refresh_status()

    def _clear_files(self):
        self._files.clear()
        self._rebuild_widgets()
        self._refresh_status()

    def _append_widget(self, path: str):
        if self._empty_label.winfo_ismapped():
            self._empty_label.grid_remove()
        w = FileItem(self._list_scroll, path, self._remove_file, self._show_preview, len(self._file_widgets))
        self._file_widgets.append(w)

    def _show_preview(self, path: str):
        if Path(path).suffix.lower() == '.svg':
            self._preview_lbl.configure(image=None, text="SVG 미리보기\n지원 안 됨")
            self._preview_photo = None
            return

        self._preview_lbl.update_idletasks()
        max_w = max(self._preview_lbl.winfo_width() - 20, 300)
        max_h = max(self._preview_lbl.winfo_height() - 20, 300)

        img = Image.open(path)
        img.thumbnail((max_w, max_h), Image.LANCZOS)
        photo = ImageTk.PhotoImage(img)

        self._preview_photo = photo
        self._preview_lbl.configure(image=photo, text="")

    def _rebuild_widgets(self):
        for w in self._file_widgets:
            w.destroy()
        self._file_widgets.clear()
        if not self._files:
            self._empty_label.grid(row=0, column=0, pady=30)
        else:
            for p in self._files:
                self._append_widget(p)

    def _refresh_status(self):
        n = len(self._files)
        self._status_lbl.configure(text="파일을 추가하세요" if n == 0 else f"{n}개 파일 준비됨")
        self._progress.set(0)

    # ── 설정 콜백 ─────────────────────────────────────────────────────────────

    def _on_format_change(self, _):
        self._update_quality_state()
        self._update_bg_warn()

    def _on_remove_bg_change(self):
        self._update_bg_warn()

    def _update_bg_warn(self):
        no_alpha = self._fmt_var.get() in ('JPEG', 'BMP')
        if self._remove_bg_var.get() and no_alpha:
            self._bg_warn_lbl.grid()
        else:
            self._bg_warn_lbl.grid_remove()

    def _update_quality_state(self):
        if self._fmt_var.get() in ('JPEG', 'WebP'):
            self._quality_lbl.grid()
            self._quality_slider.grid()
        else:
            self._quality_lbl.grid_remove()
            self._quality_slider.grid_remove()

    def _on_quality_change(self, val):
        self._quality_lbl.configure(text=f"품질: {int(float(val))}%")

    def _select_output_dir(self):
        folder = filedialog.askdirectory(title="출력 폴더 선택")
        if folder:
            self._output_dir = folder
            self._dir_var.set(f"…/{Path(folder).name}")

    # ── 변환 ──────────────────────────────────────────────────────────────────

    def _start_conversion(self):
        if self._converting:
            return
        if not self._files:
            messagebox.showwarning("경고", "변환할 파일을 추가하세요.")
            return

        width = height = None
        try:
            w = self._w_entry.get().strip()
            h = self._h_entry.get().strip()
            if w:
                width = int(w)
            if h:
                height = int(h)
        except ValueError:
            messagebox.showerror("입력 오류", "너비/높이는 숫자(px)로 입력하세요.")
            return

        params = dict(
            output_format=self._fmt_var.get(),
            quality=int(self._quality_slider.get()),
            width=width,
            height=height,
            keep_aspect=self._aspect_var.get(),
            remove_bg=self._remove_bg_var.get(),
        )

        self._converting = True
        self._convert_btn.configure(state="disabled", text="변환 중…")

        t = threading.Thread(target=self._run, args=(list(self._files), params), daemon=True)
        t.start()

    def _run(self, files: list[str], params: dict):
        if params.get('remove_bg'):
            self.after(0, self._status_lbl.configure, {"text": "AI 모델 확인 중…"})
            self.after(0, self._progress.set, 0)
            self._preload_rembg_model()

        total = len(files)
        errors: list[str] = []

        for i, path in enumerate(files):
            out_dir = self._output_dir or str(Path(path).parent)
            try:
                convert_image(path, out_dir, **params)
            except Exception as e:
                errors.append(f"{Path(path).name}: {e}")

            self.after(0, self._progress.set, (i + 1) / total)
            self.after(0, self._status_lbl.configure,
                       {"text": f"변환 중: {i + 1} / {total}"})

        self.after(0, self._done, total, errors)

    def _preload_rembg_model(self):
        """모델 미캐시 시 다운로드하며 진행률을 UI에 반영."""
        class _StderrCapture:
            def __init__(self_, cb):
                self_._cb = cb
                self_._buf = ''
                self_._real = sys.stderr
            def write(self_, text):
                self_._real.write(text)
                self_._buf += text
                m = re.search(r'(\d+)%\|', self_._buf)
                if m:
                    self_._cb(int(m.group(1)))
                    self_._buf = ''
            def flush(self_):
                self_._real.flush()

        def _update(pct):
            self.after(0, self._status_lbl.configure,
                       {"text": f"AI 모델 다운로드 중: {pct}%"})
            self.after(0, self._progress.set, pct / 100)

        orig = sys.stderr
        sys.stderr = _StderrCapture(_update)
        try:
            get_rembg_session()
        finally:
            sys.stderr = orig

        self.after(0, self._status_lbl.configure, {"text": "모델 준비 완료, 변환 시작…"})
        self.after(0, self._progress.set, 0)

    def _done(self, total: int, errors: list[str]):
        self._converting = False
        self._convert_btn.configure(state="normal", text="▶  변환 시작")

        if errors:
            msg = f"{total - len(errors)}/{total}개 성공\n\n실패 목록:\n" + "\n".join(errors)
            messagebox.showwarning("완료 (일부 실패)", msg)
        else:
            self._status_lbl.configure(text=f"완료!  {total}개 파일 변환됨")
            messagebox.showinfo("완료", f"{total}개 파일이 성공적으로 변환되었습니다.")


if __name__ == "__main__":
    App().mainloop()
