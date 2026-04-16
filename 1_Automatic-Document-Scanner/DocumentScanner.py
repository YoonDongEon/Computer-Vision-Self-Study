import io
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import cv2
import fitz
import numpy as np
from PIL import Image, ImageEnhance, ImageTk


def pil_image_to_png_bytes(pil_image):
    buffer = io.BytesIO()
    pil_image.save(buffer, format="PNG")
    return buffer.getvalue()


class DocumentScannerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("자동 문서 스캐너")
        self.root.geometry("1360x820")
        self.root.minsize(1080, 700)
        self.root.configure(bg="#f4f1ea")

        self.original_image = None
        self.display_image = None
        self.scanned_image = None
        self.output_image = None
        self.points = []
        self.current_file_path = None
        self.is_pdf = False
        self.pdf_document = None
        self.pdf_page_index = 0
        self.pdf_page_count = 0

        self.scale_factor = 1.0
        self.canvas_offset_x = 0
        self.canvas_offset_y = 0
        self.drag_index = None

        self.scan_mode = tk.StringVar(value="컬러")
        self.brightness = tk.DoubleVar(value=1.0)
        self.contrast = tk.DoubleVar(value=1.15)
        self.sharpness = tk.DoubleVar(value=1.2)
        self.threshold = tk.IntVar(value=165)

        self._build_style()
        self._build_ui()

    def _build_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("Panel.TFrame", background="#fbfaf7")
        style.configure("Sidebar.TFrame", background="#efe7da")
        style.configure("PanelTitle.TLabel", background="#fbfaf7", foreground="#3d352d",
                        font=("Helvetica", 13, "bold"))
        style.configure("Hint.TLabel", background="#efe7da", foreground="#6f6256",
                        font=("Helvetica", 9))
        style.configure("SidebarTitle.TLabel", background="#efe7da", foreground="#3d352d",
                        font=("Helvetica", 12, "bold"))

    def _build_ui(self):
        header = tk.Frame(self.root, bg="#1f3c45", padx=22, pady=16)
        header.pack(fill=tk.X)

        tk.Label(
            header,
            text="Automatic Document Scanner",
            bg="#1f3c45",
            fg="#f7f2ea",
            font=("Helvetica", 20, "bold"),
        ).pack(anchor="w")

        tk.Label(
            header,
            text="자동 문서 검출, 드래그 보정, 스캔 후 후처리까지 한 번에 수행하는 GUI 프로그램",
            bg="#1f3c45",
            fg="#cfe0de",
            font=("Helvetica", 10),
        ).pack(anchor="w", pady=(4, 0))

        toolbar = tk.Frame(self.root, bg="#f4f1ea", padx=16, pady=12)
        toolbar.pack(fill=tk.X)

        btn_cfg = dict(
            relief=tk.FLAT,
            bd=0,
            font=("Helvetica", 10, "bold"),
            padx=14,
            pady=8,
            cursor="hand2",
            fg="white",
        )

        tk.Button(toolbar, text="이미지/PDF 열기", bg="#3f7d6d",
                  command=self.open_document, **btn_cfg).pack(side=tk.LEFT, padx=(0, 8))
        tk.Button(toolbar, text="문서 자동 검출", bg="#ca7c3a",
                  command=self.auto_detect_document, **btn_cfg).pack(side=tk.LEFT, padx=8)
        tk.Button(toolbar, text="점 초기화", bg="#7a6c61",
                  command=self.reset_points, **btn_cfg).pack(side=tk.LEFT, padx=8)
        tk.Button(toolbar, text="스캔 실행", bg="#214f8f",
                  command=self.scan_document, **btn_cfg).pack(side=tk.LEFT, padx=8)
        tk.Button(toolbar, text="결과 저장", bg="#7a3e65",
                  command=self.save_result, **btn_cfg).pack(side=tk.LEFT, padx=8)

        self.status_label = tk.Label(
            toolbar,
            text="이미지를 열어주세요.",
            bg="#f4f1ea",
            fg="#51463d",
            font=("Helvetica", 10),
        )
        self.status_label.pack(side=tk.LEFT, padx=18)

        body = tk.Frame(self.root, bg="#f4f1ea", padx=14, pady=8)
        body.pack(fill=tk.BOTH, expand=True)

        left_panel = ttk.Frame(body, style="Panel.TFrame", padding=12)
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8), pady=(0, 10))

        right_panel = ttk.Frame(body, style="Panel.TFrame", padding=12)
        right_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 8), pady=(0, 10))

        sidebar = ttk.Frame(body, style="Sidebar.TFrame", padding=14)
        sidebar.pack(side=tk.RIGHT, fill=tk.Y, padx=(8, 0), pady=(0, 10))
        sidebar.pack_propagate(False)
        sidebar.configure(width=295)

        tk.Label(left_panel, text="원본 이미지 / 문서 영역", bg="#fbfaf7", fg="#3d352d",
                 font=("Helvetica", 13, "bold")).pack(anchor="w")
        tk.Label(left_panel,
                 text="자동 검출 후 꼭짓점을 드래그하여 문서 외곽을 세밀하게 보정할 수 있습니다.",
                 bg="#fbfaf7", fg="#7b7168", font=("Helvetica", 9)).pack(anchor="w", pady=(4, 10))

        self.canvas_original = tk.Canvas(
            left_panel, bg="#e6ddd2", highlightthickness=1,
            highlightbackground="#d2c5b6", cursor="crosshair"
        )
        self.canvas_original.pack(fill=tk.BOTH, expand=True)
        self.canvas_original.bind("<Button-1>", self.on_canvas_press)
        self.canvas_original.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas_original.bind("<ButtonRelease-1>", self.on_canvas_release)

        tk.Label(right_panel, text="스캔 결과 미리보기", bg="#fbfaf7", fg="#3d352d",
                 font=("Helvetica", 13, "bold")).pack(anchor="w")
        tk.Label(right_panel,
                 text="문서 검출 후 스캔을 실행하면 컬러, 그레이스케일, 흑백 모드로 결과를 확인할 수 있습니다.",
                 bg="#fbfaf7", fg="#7b7168", font=("Helvetica", 9)).pack(anchor="w", pady=(4, 10))

        self.canvas_result = tk.Canvas(
            right_panel, bg="#ebe6de", highlightthickness=1,
            highlightbackground="#d2c5b6"
        )
        self.canvas_result.pack(fill=tk.BOTH, expand=True)

        self._build_sidebar(sidebar)

    def _build_sidebar(self, parent):
        ttk.Label(parent, text="스캔 설정", style="SidebarTitle.TLabel").pack(anchor="w")
        ttk.Label(
            parent,
            text="1. 이미지를 불러오고\n2. 자동 검출 후 점을 조정하고\n3. 스캔 실행과 후처리를 진행하세요.",
            style="Hint.TLabel",
            justify=tk.LEFT,
        ).pack(anchor="w", pady=(4, 14))

        ttk.Separator(parent, orient="horizontal").pack(fill=tk.X, pady=8)

        page_row = tk.Frame(parent, bg="#efe7da")
        page_row.pack(fill=tk.X, pady=(0, 12))

        tk.Label(page_row, text="PDF 페이지", bg="#efe7da", fg="#473d35",
                 font=("Helvetica", 10, "bold")).pack(side=tk.LEFT)

        self.page_label = tk.Label(
            page_row, text="이미지 문서", bg="#efe7da", fg="#8f4e1e",
            font=("Helvetica", 9, "bold")
        )
        self.page_label.pack(side=tk.RIGHT)

        page_nav = tk.Frame(parent, bg="#efe7da")
        page_nav.pack(fill=tk.X, pady=(0, 10))

        self.prev_page_button = tk.Button(
            page_nav, text="이전 페이지", command=self.go_to_previous_page,
            bg="#b9aa98", fg="white", relief=tk.FLAT, font=("Helvetica", 9, "bold"),
            cursor="hand2", state=tk.DISABLED
        )
        self.prev_page_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))

        self.next_page_button = tk.Button(
            page_nav, text="다음 페이지", command=self.go_to_next_page,
            bg="#b9aa98", fg="white", relief=tk.FLAT, font=("Helvetica", 9, "bold"),
            cursor="hand2", state=tk.DISABLED
        )
        self.next_page_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))

        tk.Label(parent, text="출력 모드", bg="#efe7da", fg="#473d35",
                 font=("Helvetica", 10, "bold")).pack(anchor="w")
        mode_box = ttk.Combobox(
            parent, textvariable=self.scan_mode, state="readonly",
            values=["컬러", "그레이스케일", "흑백"], font=("Helvetica", 10)
        )
        mode_box.pack(fill=tk.X, pady=(6, 12))
        mode_box.bind("<<ComboboxSelected>>", lambda _e: self.apply_adjustments())

        self._add_slider(parent, "밝기", self.brightness, 0.7, 1.5, 0.05)
        self._add_slider(parent, "대비", self.contrast, 0.8, 2.0, 0.05)
        self._add_slider(parent, "선명도", self.sharpness, 0.5, 2.5, 0.05)

        tk.Label(parent, text="흑백 임계값", bg="#efe7da", fg="#473d35",
                 font=("Helvetica", 10, "bold")).pack(anchor="w", pady=(10, 0))
        threshold_frame = tk.Frame(parent, bg="#efe7da")
        threshold_frame.pack(fill=tk.X, pady=(6, 4))
        self.threshold_value_label = tk.Label(
            threshold_frame, text=str(self.threshold.get()), bg="#efe7da",
            fg="#8f4e1e", font=("Helvetica", 10, "bold")
        )
        self.threshold_value_label.pack(side=tk.RIGHT)
        tk.Scale(
            parent,
            variable=self.threshold,
            from_=80,
            to=220,
            orient=tk.HORIZONTAL,
            resolution=1,
            command=self._on_threshold_change,
            bg="#efe7da",
            fg="#473d35",
            troughcolor="#d7c6b6",
            highlightthickness=0,
            showvalue=False,
            length=240,
        ).pack(fill=tk.X)

        ttk.Separator(parent, orient="horizontal").pack(fill=tk.X, pady=12)

        tk.Button(
            parent,
            text="후처리 적용",
            command=self.apply_adjustments,
            bg="#3a5f75",
            fg="white",
            relief=tk.FLAT,
            font=("Helvetica", 10, "bold"),
            pady=8,
            cursor="hand2",
        ).pack(fill=tk.X)

        tk.Button(
            parent,
            text="설정 초기화",
            command=self.reset_adjustments,
            bg="#8a8178",
            fg="white",
            relief=tk.FLAT,
            font=("Helvetica", 10),
            pady=7,
            cursor="hand2",
        ).pack(fill=tk.X, pady=(8, 0))

        ttk.Separator(parent, orient="horizontal").pack(fill=tk.X, pady=12)

        tk.Label(parent, text="선택된 꼭짓점 좌표", bg="#efe7da", fg="#473d35",
                 font=("Helvetica", 10, "bold")).pack(anchor="w")
        self.points_text = tk.Text(
            parent, height=12, bg="#fbfaf7", fg="#50453d",
            relief=tk.FLAT, bd=0, font=("Courier", 9), state=tk.DISABLED
        )
        self.points_text.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

    def _add_slider(self, parent, label, variable, from_, to, resolution):
        frame = tk.Frame(parent, bg="#efe7da")
        frame.pack(fill=tk.X, pady=(2, 8))

        tk.Label(frame, text=label, bg="#efe7da", fg="#473d35",
                 font=("Helvetica", 10, "bold")).pack(side=tk.LEFT)
        value_label = tk.Label(frame, text=f"{variable.get():.2f}", bg="#efe7da",
                               fg="#8f4e1e", font=("Helvetica", 10, "bold"))
        value_label.pack(side=tk.RIGHT)

        variable.trace_add("write", lambda *_: value_label.config(text=f"{variable.get():.2f}"))

        tk.Scale(
            parent,
            variable=variable,
            from_=from_,
            to=to,
            resolution=resolution,
            orient=tk.HORIZONTAL,
            command=lambda _v: self._on_adjustment_change(),
            bg="#efe7da",
            fg="#473d35",
            troughcolor="#d7c6b6",
            highlightthickness=0,
            showvalue=False,
            length=240,
        ).pack(fill=tk.X)

    def _on_adjustment_change(self):
        if self.scanned_image is not None:
            self.apply_adjustments()

    def _on_threshold_change(self, _value):
        self.threshold_value_label.config(text=str(self.threshold.get()))
        if self.scanned_image is not None and self.scan_mode.get() == "흑백":
            self.apply_adjustments()

    def open_document(self):
        path = filedialog.askopenfilename(
            title="문서 파일 선택",
            filetypes=[
                ("이미지 파일", "*.jpg *.jpeg *.png *.bmp *.tiff *.webp"),
                ("PDF 문서", "*.pdf"),
                ("지원 파일", "*.jpg *.jpeg *.png *.bmp *.tiff *.webp *.pdf"),
                ("모든 파일", "*.*"),
            ],
        )
        if not path:
            return

        self._close_pdf_document()

        ext = os.path.splitext(path)[1].lower()
        self.current_file_path = path
        self.is_pdf = ext == ".pdf"

        if self.is_pdf:
            try:
                self.pdf_document = fitz.open(path)
            except Exception as exc:
                messagebox.showerror("오류", f"PDF를 불러오지 못했습니다.\n{exc}")
                self._reset_document_state()
                return

            self.pdf_page_count = len(self.pdf_document)
            self.pdf_page_index = 0
            if self.pdf_page_count == 0:
                messagebox.showerror("오류", "페이지가 없는 PDF입니다.")
                self._reset_document_state()
                return

            self._load_pdf_page(self.pdf_page_index)
        else:
            image = cv2.imread(path)
            if image is None:
                messagebox.showerror("오류", "이미지를 불러오지 못했습니다.")
                self._reset_document_state()
                return

            self.pdf_page_count = 0
            self.pdf_page_index = 0
            self._set_source_image(image, f"이미지 로드 완료: {os.path.basename(path)}")

    def _reset_document_state(self):
        self.current_file_path = None
        self.is_pdf = False
        self.original_image = None
        self.display_image = None
        self.scanned_image = None
        self.output_image = None
        self.points = []
        self.pdf_page_index = 0
        self.pdf_page_count = 0
        self._update_page_controls()

    def _close_pdf_document(self):
        if self.pdf_document is not None:
            self.pdf_document.close()
            self.pdf_document = None

    def _load_pdf_page(self, page_index):
        if self.pdf_document is None:
            return

        page = self.pdf_document.load_page(page_index)
        matrix = fitz.Matrix(2.0, 2.0)
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.height, pixmap.width, pixmap.n)
        image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

        self._set_source_image(
            image,
            f"PDF 로드 완료: {os.path.basename(self.current_file_path)}  |  페이지 {page_index + 1}/{self.pdf_page_count}"
        )

    def _set_source_image(self, image, status_message):
        self.original_image = image
        self.display_image = image.copy()
        self.scanned_image = None
        self.output_image = None
        self.points = []
        self.drag_index = None

        self._show_on_canvas(self.original_image, self.canvas_original, store_transform=True)
        self.canvas_result.delete("all")
        self._refresh_points_info()
        self._update_page_controls()
        self.update_status(status_message)

        self.auto_detect_document()

    def _update_page_controls(self):
        if self.is_pdf and self.pdf_page_count > 0:
            self.page_label.config(text=f"{self.pdf_page_index + 1} / {self.pdf_page_count}")

            prev_state = tk.NORMAL if self.pdf_page_index > 0 else tk.DISABLED
            next_state = tk.NORMAL if self.pdf_page_index < self.pdf_page_count - 1 else tk.DISABLED
            self.prev_page_button.config(state=prev_state)
            self.next_page_button.config(state=next_state)
        else:
            self.page_label.config(text="이미지 문서")
            self.prev_page_button.config(state=tk.DISABLED)
            self.next_page_button.config(state=tk.DISABLED)

    def go_to_previous_page(self):
        if not self.is_pdf or self.pdf_document is None or self.pdf_page_index <= 0:
            return
        self.pdf_page_index -= 1
        self._load_pdf_page(self.pdf_page_index)

    def go_to_next_page(self):
        if not self.is_pdf or self.pdf_document is None or self.pdf_page_index >= self.pdf_page_count - 1:
            return
        self.pdf_page_index += 1
        self._load_pdf_page(self.pdf_page_index)

    def auto_detect_document(self):
        if self.original_image is None:
            self.update_status("먼저 이미지를 열어주세요.")
            return

        corners = self._detect_document_corners(self.original_image)
        if corners is None:
            self.points = []
            self._render_original_with_overlay()
            self._refresh_points_info()
            self.update_status("문서 자동 검출 실패: 수동으로 4개 점을 지정하거나 더 선명한 이미지를 사용하세요.")
            return

        self.points = [tuple(map(int, pt)) for pt in corners]
        self._render_original_with_overlay()
        self._refresh_points_info()
        self.update_status("문서 영역 자동 검출 완료: 점을 드래그해서 미세 조정할 수 있습니다.")

    def _detect_document_corners(self, image):
        h, w = image.shape[:2]
        target_height = 1100
        scale = target_height / h if h > target_height else 1.0
        resized = cv2.resize(image, (int(w * scale), int(h * scale))) if scale != 1.0 else image.copy()

        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        edged = cv2.Canny(blur, 60, 180)

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        edged = cv2.morphologyEx(edged, cv2.MORPH_CLOSE, kernel, iterations=2)

        contours, _ = cv2.findContours(edged, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        contours = sorted(contours, key=cv2.contourArea, reverse=True)

        min_area = resized.shape[0] * resized.shape[1] * 0.15
        for contour in contours[:15]:
            area = cv2.contourArea(contour)
            if area < min_area:
                continue

            perimeter = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
            if len(approx) == 4:
                points = approx.reshape(4, 2).astype(np.float32)
                return self._rescale_points(self._order_points(points), 1.0 / scale)

        for contour in contours[:10]:
            area = cv2.contourArea(contour)
            if area < min_area:
                continue

            rect = cv2.minAreaRect(contour)
            box = cv2.boxPoints(rect).astype(np.float32)
            return self._rescale_points(self._order_points(box), 1.0 / scale)

        return None

    def _rescale_points(self, points, ratio):
        if abs(ratio - 1.0) < 1e-9:
            return points
        return points * ratio

    def _order_points(self, points):
        rect = np.zeros((4, 2), dtype=np.float32)
        s = points.sum(axis=1)
        diff = np.diff(points, axis=1)

        rect[0] = points[np.argmin(s)]
        rect[2] = points[np.argmax(s)]
        rect[1] = points[np.argmin(diff)]
        rect[3] = points[np.argmax(diff)]
        return rect

    def _show_on_canvas(self, image, canvas, store_transform=False):
        canvas.update_idletasks()
        canvas_width = canvas.winfo_width()
        canvas_height = canvas.winfo_height()

        if canvas_width <= 1 or canvas_height <= 1:
            canvas_width, canvas_height = 620, 520

        h, w = image.shape[:2]
        scale = min(canvas_width / w, canvas_height / h)
        new_w = max(1, int(w * scale))
        new_h = max(1, int(h * scale))
        offset_x = (canvas_width - new_w) // 2
        offset_y = (canvas_height - new_h) // 2

        if store_transform:
            self.scale_factor = scale
            self.canvas_offset_x = offset_x
            self.canvas_offset_y = offset_y

        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(rgb).resize((new_w, new_h), Image.LANCZOS)
        tk_image = ImageTk.PhotoImage(pil_image)

        canvas.delete("all")
        canvas.create_image(offset_x, offset_y, anchor=tk.NW, image=tk_image)

        if canvas is self.canvas_original:
            self._tk_original = tk_image
        else:
            self._tk_result = tk_image

    def _render_original_with_overlay(self):
        if self.original_image is None:
            return

        self._show_on_canvas(self.original_image, self.canvas_original, store_transform=True)

        if not self.points:
            return

        canvas_points = [self._image_to_canvas_point(pt) for pt in self.points]
        flat_points = [coord for pt in canvas_points for coord in pt]

        self.canvas_original.create_polygon(
            flat_points,
            fill="#f4b860",
            outline="#8f4e1e",
            width=3,
            stipple="gray25",
        )

        labels = ["1", "2", "3", "4"]
        colors = ["#d1495b", "#2e86ab", "#3a7d44", "#f18f01"]
        for idx, ((cx, cy), label, color) in enumerate(zip(canvas_points, labels, colors)):
            self.canvas_original.create_oval(cx - 9, cy - 9, cx + 9, cy + 9,
                                             fill=color, outline="white", width=2)
            self.canvas_original.create_text(cx, cy - 18, text=label,
                                             fill="#2f2a24", font=("Helvetica", 10, "bold"))

            if idx > 0:
                px, py = canvas_points[idx - 1]
                self.canvas_original.create_line(px, py, cx, cy, fill="#fffaf2",
                                                 width=2, dash=(5, 4))

        fx, fy = canvas_points[0]
        lx, ly = canvas_points[-1]
        self.canvas_original.create_line(lx, ly, fx, fy, fill="#fffaf2", width=2, dash=(5, 4))

    def _image_to_canvas_point(self, point):
        x, y = point
        canvas_x = int(x * self.scale_factor) + self.canvas_offset_x
        canvas_y = int(y * self.scale_factor) + self.canvas_offset_y
        return canvas_x, canvas_y

    def _canvas_to_image_point(self, x, y):
        img_x = int((x - self.canvas_offset_x) / self.scale_factor)
        img_y = int((y - self.canvas_offset_y) / self.scale_factor)
        return img_x, img_y

    def on_canvas_press(self, event):
        if self.original_image is None:
            self.update_status("먼저 이미지를 열어주세요.")
            return

        if self.points:
            index = self._find_nearest_point(event.x, event.y)
            if index is not None:
                self.drag_index = index
                return

        if len(self.points) >= 4:
            self.update_status("이미 4개의 점이 있습니다. 꼭짓점을 드래그하거나 '점 초기화'를 사용하세요.")
            return

        img_x, img_y = self._canvas_to_image_point(event.x, event.y)
        if not self._is_inside_image(img_x, img_y):
            self.update_status("이미지 영역 안쪽을 클릭해주세요.")
            return

        self.points.append((img_x, img_y))
        self._render_original_with_overlay()
        self._refresh_points_info()

        if len(self.points) == 4:
            self.points = [tuple(map(int, pt)) for pt in self._order_points(np.array(self.points, dtype=np.float32))]
            self._render_original_with_overlay()
            self._refresh_points_info()
            self.update_status("4개 점 지정 완료: 스캔 실행 또는 드래그 보정을 진행하세요.")
        else:
            self.update_status(f"수동 점 지정 중: {len(self.points)}/4")

    def on_canvas_drag(self, event):
        if self.original_image is None or self.drag_index is None:
            return

        img_x, img_y = self._canvas_to_image_point(event.x, event.y)
        h, w = self.original_image.shape[:2]
        img_x = int(np.clip(img_x, 0, w - 1))
        img_y = int(np.clip(img_y, 0, h - 1))

        self.points[self.drag_index] = (img_x, img_y)
        self.points = [tuple(map(int, pt)) for pt in self._order_points(np.array(self.points, dtype=np.float32))]
        self._render_original_with_overlay()
        self._refresh_points_info()

    def on_canvas_release(self, _event):
        if self.drag_index is not None:
            self.drag_index = None
            self.update_status("문서 꼭짓점 위치를 수정했습니다.")

    def _find_nearest_point(self, canvas_x, canvas_y):
        if not self.points:
            return None

        best_index = None
        best_distance = 18
        for idx, point in enumerate(self.points):
            px, py = self._image_to_canvas_point(point)
            distance = ((canvas_x - px) ** 2 + (canvas_y - py) ** 2) ** 0.5
            if distance <= best_distance:
                best_distance = distance
                best_index = idx
        return best_index

    def _is_inside_image(self, x, y):
        if self.original_image is None:
            return False
        h, w = self.original_image.shape[:2]
        return 0 <= x < w and 0 <= y < h

    def reset_points(self):
        self.points = []
        self.drag_index = None
        self._refresh_points_info()
        if self.original_image is not None:
            self._render_original_with_overlay()
        self.update_status("문서 꼭짓점이 초기화되었습니다.")

    def scan_document(self):
        if self.original_image is None:
            messagebox.showwarning("경고", "이미지를 먼저 열어주세요.")
            return

        if len(self.points) != 4:
            messagebox.showwarning("경고", "문서 영역 꼭짓점 4개가 필요합니다.")
            return

        src = np.array(self.points, dtype=np.float32)
        width_top = np.linalg.norm(src[1] - src[0])
        width_bottom = np.linalg.norm(src[2] - src[3])
        height_left = np.linalg.norm(src[3] - src[0])
        height_right = np.linalg.norm(src[2] - src[1])

        max_width = max(int(width_top), int(width_bottom), 1)
        max_height = max(int(height_left), int(height_right), 1)

        dst = np.array([
            [0, 0],
            [max_width - 1, 0],
            [max_width - 1, max_height - 1],
            [0, max_height - 1],
        ], dtype=np.float32)

        matrix = cv2.getPerspectiveTransform(src, dst)
        warped = cv2.warpPerspective(self.original_image, matrix, (max_width, max_height))

        self.scanned_image = warped
        self.apply_adjustments()
        self.update_status(f"스캔 완료: {max_width} x {max_height} px")

    def apply_adjustments(self):
        if self.scanned_image is None:
            return

        rgb = cv2.cvtColor(self.scanned_image, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(rgb)
        pil_image = ImageEnhance.Brightness(pil_image).enhance(self.brightness.get())
        pil_image = ImageEnhance.Contrast(pil_image).enhance(self.contrast.get())
        pil_image = ImageEnhance.Sharpness(pil_image).enhance(self.sharpness.get())

        mode = self.scan_mode.get()
        if mode == "그레이스케일":
            pil_image = pil_image.convert("L").convert("RGB")
        elif mode == "흑백":
            gray = pil_image.convert("L")
            threshold = self.threshold.get()
            binary = gray.point(lambda px: 255 if px > threshold else 0, mode="1")
            pil_image = binary.convert("RGB")

        self.output_image = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
        self._show_on_canvas(self.output_image, self.canvas_result)

    def save_result(self):
        if self.output_image is None:
            messagebox.showwarning("경고", "저장할 결과가 없습니다. 먼저 스캔을 실행하세요.")
            return

        path = filedialog.asksaveasfilename(
            title="스캔 결과 저장",
            defaultextension=".png",
            filetypes=[
                ("PNG", "*.png"),
                ("JPEG", "*.jpg"),
                ("BMP", "*.bmp"),
                ("PDF", "*.pdf"),
                ("모든 파일", "*.*"),
            ],
        )
        if not path:
            return

        ext = os.path.splitext(path)[1].lower()

        try:
            if ext == ".pdf":
                self._save_output_as_pdf(path)
            else:
                self._save_output_as_image(path)
        except Exception as exc:
            messagebox.showerror("오류", f"파일 저장에 실패했습니다.\n{exc}")
            return

        self.update_status(f"저장 완료: {os.path.basename(path)}")
        messagebox.showinfo("저장 완료", f"스캔 결과를 저장했습니다.\n\n{path}")

    def _save_output_as_image(self, path):
        if not cv2.imwrite(path, self.output_image):
            raise RuntimeError("이미지 파일 저장 중 오류가 발생했습니다.")

    def _save_output_as_pdf(self, path):
        rgb_image = cv2.cvtColor(self.output_image, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(rgb_image)

        if pil_image.mode != "RGB":
            pil_image = pil_image.convert("RGB")

        width_px, height_px = pil_image.size
        pdf_width = width_px * 72 / 96
        pdf_height = height_px * 72 / 96

        pdf_document = fitz.open()
        page = pdf_document.new_page(width=pdf_width, height=pdf_height)

        image_bytes = pil_image_to_png_bytes(pil_image)
        page.insert_image(page.rect, stream=image_bytes)
        pdf_document.save(path)
        pdf_document.close()

    def reset_adjustments(self):
        self.scan_mode.set("컬러")
        self.brightness.set(1.0)
        self.contrast.set(1.15)
        self.sharpness.set(1.2)
        self.threshold.set(165)
        self.threshold_value_label.config(text=str(self.threshold.get()))

        if self.scanned_image is not None:
            self.apply_adjustments()

        self.update_status("후처리 설정을 기본값으로 되돌렸습니다.")

    def _refresh_points_info(self):
        labels = ["1. 좌상단", "2. 우상단", "3. 우하단", "4. 좌하단"]
        self.points_text.config(state=tk.NORMAL)
        self.points_text.delete("1.0", tk.END)

        if not self.points:
            self.points_text.insert(
                tk.END,
                "아직 선택된 점이 없습니다.\n\n"
                "자동 검출 버튼을 누르거나\n"
                "이미지 위를 클릭해 4개의 꼭짓점을 지정하세요.",
            )
        else:
            for idx, (x, y) in enumerate(self.points):
                self.points_text.insert(tk.END, f"{labels[idx]}\n   x = {x:>4}, y = {y:>4}\n\n")

        self.points_text.config(state=tk.DISABLED)

    def update_status(self, message):
        self.status_label.config(text=message)


if __name__ == "__main__":
    root = tk.Tk()
    app = DocumentScannerApp(root)
    root.mainloop()
