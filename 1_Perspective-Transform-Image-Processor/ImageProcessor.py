import cv2                          # OpenCV: 이미지 처리 및 투시변환 핵심 라이브러리
import numpy as np                  # NumPy: 좌표 배열 및 LUT 계산에 사용
import tkinter as tk                # tkinter: GUI 윈도우 구성의 기본 모듈
from tkinter import ttk, filedialog, messagebox  # ttk: 구분선, filedialog: 파일탐색기, messagebox: 경고창
from PIL import Image, ImageTk, ImageEnhance     # PIL: 밝기/대비/선명도 조정, tkinter 이미지 변환
import os                           # os: 파일 경로에서 파일명 추출용


""" 메인 애플리케이션 클래스 """
class PerspectiveTransformApp:
    """
    투시변환(Perspective Transform) 이미지 처리 GUI 애플리케이션

    [전체 동작 흐름]
      1) 이미지 열기 → 원본 캔버스에 표시
      2) 원본 캔버스에서 4점 클릭 → 변환 영역 지정
      3) '변환 실행' → 투시변환 결과 오른쪽 캔버스에 표시
      4) 사이드바 슬라이더로 밝기/대비/선명도 조정 → '효과 적용'
      5) '결과 저장' → PNG/JPG/BMP 중 선택하여 파일 저장
    """

    def __init__(self, root):
        """
        앱 초기화 메서드 — 루트 윈도우를 받아 상태 변수를 세팅하고 UI를 생성한다.

        Args:
            root (tk.Tk): tkinter 최상위 윈도우 객체
        """
        self.root = root

        # 이미지 데이터 변수 
        self.original_image    = None   # 원본 이미지 (OpenCV BGR 포맷 ndarray)
        self.transformed_image = None   # 투시변환만 적용된 이미지 (BGR ndarray)
        self.adjusted_image    = None   # 밝기·대비·선명도까지 적용된 최종 이미지 (BGR ndarray)

        # 4점 좌표 관련 변수 
        self.points        = []   # 사용자가 클릭한 원본 이미지 픽셀 좌표 [(x,y), ...]
        self.point_markers = []   # 캔버스에 그려진 마커(원·선·숫자)의 Canvas 아이템 ID 목록
                                  # → reset_points() 에서 이 ID들로 마커를 일괄 삭제

        # 캔버스-이미지 좌표 변환 파라미터
        # 이미지를 캔버스에 비율 유지하며 축소 표시할 때
        # "캔버스 픽셀 좌표 ↔ 원본 이미지 픽셀 좌표" 변환에 필요한 값들
        self.scale_factor    = 1.0  # 원본 이미지를 캔버스에 표시할 때 적용된 축소 배율
        self.canvas_offset_x = 0    # 캔버스 중앙 배치 시 이미지 좌측 여백(px)
        self.canvas_offset_y = 0    # 캔버스 중앙 배치 시 이미지 상단 여백(px)

        # 슬라이더와 연동되는 tkinter 변수 
        # tk.DoubleVar: 슬라이더 위젯과 값이 자동으로 양방향 동기화된다
        self.brightness = tk.DoubleVar(value=1.0)  # 밝기  (1.0 = 원본 그대로)
        self.contrast   = tk.DoubleVar(value=1.0)  # 대비  (1.0 = 원본 그대로)
        self.sharpness  = tk.DoubleVar(value=1.0)  # 선명도(1.0 = 원본 그대로)

        self._build_ui()   # UI 레이아웃 구성 시작

    # 1-1) UI 구성 메서드
    def _build_ui(self):
        """
        전체 UI 레이아웃을 생성한다.

        레이아웃 구조:
        ┌────────────────────────── 툴바 (상단 고정) ─────────────────────────┐
        │  [원본 캔버스]    │    [결과 캔버스]    │   [사이드바 - 슬라이더]    │
        └────────────────────────────────────────────────────────────────────┘
        """

        # 상단 툴바 프레임
        toolbar = tk.Frame(self.root, bg="#2c2c2c", pady=6)
        toolbar.pack(side=tk.TOP, fill=tk.X)   # 화면 상단에 가로로 꽉 채움

        # 버튼에 공통으로 적용할 스타일 딕셔너리 (** 언패킹으로 재사용)
        btn_cfg = dict(
            font=("Arial", 10, "bold"),
            relief=tk.FLAT,   # 버튼 테두리를 납작하게(평면) 표시
            padx=12, pady=4,
            fg="white"
        )

        # 각 기능 버튼 생성 — command= 에 각 기능 메서드를 연결
        tk.Button(toolbar, text="📂  이미지 열기",
                  command=self.open_image,
                  bg="#4a90d9", **btn_cfg).pack(side=tk.LEFT, padx=5)

        tk.Button(toolbar, text="🔄  점 초기화",
                  command=self.reset_points,
                  bg="#e67e22", **btn_cfg).pack(side=tk.LEFT, padx=5)

        tk.Button(toolbar, text="✨  변환 실행",
                  command=self.apply_transform,
                  bg="#27ae60", **btn_cfg).pack(side=tk.LEFT, padx=5)

        tk.Button(toolbar, text="💾  결과 저장",
                  command=self.save_result,
                  bg="#8e44ad", **btn_cfg).pack(side=tk.LEFT, padx=5)

        # 현재 동작 상태를 실시간으로 보여주는 상태 레이블
        self.status_label = tk.Label(
            toolbar,
            text="📌  이미지를 열어주세요.",
            bg="#2c2c2c", fg="#ecf0f1",
            font=("Arial", 9)
        )
        self.status_label.pack(side=tk.LEFT, padx=20)

        # 메인 컨텐츠 프레임 (캔버스 2개 + 사이드바 포함)
        content = tk.Frame(self.root, bg="#1a1a2e")
        content.pack(fill=tk.BOTH, expand=True)  # 남은 공간 전체를 차지하도록

        # 왼쪽: 원본 이미지 캔버스
        left_frame = tk.Frame(content, bg="#1a1a2e")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True,
                        padx=(10, 5), pady=10)

        tk.Label(
            left_frame,
            text="원본 이미지  ✦  클릭 순서: ①좌상 → ②우상 → ③우하 → ④좌하",
            bg="#1a1a2e", fg="#00d4ff",
            font=("Arial", 10, "bold")
        ).pack(pady=(0, 4))

        # cursor="crosshair": 마우스 커서를 십자(+) 모양으로 바꿔 정밀 클릭 유도
        self.canvas_orig = tk.Canvas(
            left_frame, bg="#0d0d1a",
            cursor="crosshair",
            highlightthickness=1,
            highlightbackground="#00d4ff"
        )
        self.canvas_orig.pack(fill=tk.BOTH, expand=True)
        # 마우스 왼쪽 클릭(<Button-1>) 이벤트 발생 시 on_canvas_click 메서드 호출
        self.canvas_orig.bind("<Button-1>", self.on_canvas_click)

        # 가운데: 변환 결과 캔버스
        mid_frame = tk.Frame(content, bg="#1a1a2e")
        mid_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True,
                       padx=(5, 10), pady=10)

        tk.Label(
            mid_frame,
            text="투시변환 결과",
            bg="#1a1a2e", fg="#00d4ff",
            font=("Arial", 10, "bold")
        ).pack(pady=(0, 4))

        self.canvas_result = tk.Canvas(
            mid_frame, bg="#0d0d1a",
            highlightthickness=1,
            highlightbackground="#00d4ff"
        )
        self.canvas_result.pack(fill=tk.BOTH, expand=True)

        # 오른쪽: 사이드바
        self._build_sidebar(content)

    def _build_sidebar(self, parent):
        """
        우측 사이드바 UI를 구성한다.

        포함 요소:
          - 밝기 / 대비 / 선명도 슬라이더 (각각 수치 레이블 포함)
          - 출력 이미지 크기(너비·높이) 입력 필드
          - '효과 적용' 버튼 / '슬라이더 초기화' 버튼
          - 현재 선택된 4점 좌표 표시 텍스트박스

        Args:
            parent (tk.Frame): 사이드바를 배치할 부모 컨테이너 위젯
        """
        # 사이드바 고정 너비 프레임
        sidebar = tk.Frame(parent, bg="#16213e", width=245,
                           relief=tk.RIDGE, bd=2)
        sidebar.pack(side=tk.RIGHT, fill=tk.Y, padx=10, pady=10)
        # pack_propagate(False): 자식 위젯이 아무리 커도 사이드바 너비(width=245)를 고정
        sidebar.pack_propagate(False)

        # 사이드바 제목
        tk.Label(
            sidebar, text="⚙   이미지 조정",
            bg="#16213e", fg="#e94560",
            font=("Arial", 12, "bold")
        ).pack(pady=(15, 5))

        # 구분선
        ttk.Separator(sidebar, orient="horizontal").pack(fill=tk.X, padx=10, pady=3)

        # 슬라이더 3종 생성 (_add_slider 헬퍼 메서드 재사용)
        self._add_slider(
            parent=sidebar,
            label="☀   밝기",
            var=self.brightness,
            from_=0.1, to=3.0, res=0.05,
            desc="1.0 = 원본  |  >1.0 밝게  |  <1.0 어둡게"
        )
        self._add_slider(
            parent=sidebar,
            label="◑   대비",
            var=self.contrast,
            from_=0.1, to=3.0, res=0.05,
            desc="1.0 = 원본  |  >1.0 강하게  |  <1.0 약하게"
        )
        self._add_slider(
            parent=sidebar,
            label="🔍   선명도",
            var=self.sharpness,
            from_=0.0, to=5.0, res=0.1,
            desc="1.0 = 원본  |  >1.0 선명  |  <1.0 흐릿하게"
        )

        ttk.Separator(sidebar, orient="horizontal").pack(fill=tk.X, padx=10, pady=8)

        # 출력 크기 입력 필드
        tk.Label(
            sidebar, text="📐   출력 크기 (픽셀)",
            bg="#16213e", fg="#f0a500",
            font=("Arial", 10, "bold")
        ).pack(pady=(0, 4))

        size_frame = tk.Frame(sidebar, bg="#16213e")
        size_frame.pack(fill=tk.X, padx=15)

        # (레이블 텍스트, 인스턴스 속성명, 기본값) 묶음으로 반복 생성
        for row, (lbl, attr, default) in enumerate([
            ("너  비", "out_width",  "600"),
            ("높  이", "out_height", "400"),
        ]):
            tk.Label(size_frame, text=f"{lbl} :",
                     bg="#16213e", fg="white",
                     font=("Arial", 9)).grid(row=row, column=0, sticky="w", pady=3)
            entry = tk.Entry(size_frame, width=8, font=("Arial", 9))
            entry.insert(0, default)
            entry.grid(row=row, column=1, padx=8, pady=3)
            # setattr로 self.out_width, self.out_height 동적 생성
            setattr(self, attr, entry)

        ttk.Separator(sidebar, orient="horizontal").pack(fill=tk.X, padx=10, pady=8)

        # 기능 버튼 2개
        tk.Button(
            sidebar, text="🎨   효과 적용",
            command=self.apply_adjustments,
            bg="#4a90d9", fg="white",
            font=("Arial", 10, "bold"),
            relief=tk.FLAT, pady=6
        ).pack(fill=tk.X, padx=15, pady=3)

        tk.Button(
            sidebar, text="↩   슬라이더 초기화",
            command=self.reset_adjustments,
            bg="#636e72", fg="white",
            font=("Arial", 9),
            relief=tk.FLAT, pady=4
        ).pack(fill=tk.X, padx=15, pady=3)

        ttk.Separator(sidebar, orient="horizontal").pack(fill=tk.X, padx=10, pady=8)

        # 선택된 점 좌표 표시 텍스트박스
        tk.Label(
            sidebar, text="📍   선택된 점 좌표",
            bg="#16213e", fg="#f0a500",
            font=("Arial", 10, "bold")
        ).pack(pady=(0, 4))

        # state=DISABLED: 읽기 전용으로 초기화 (내용 변경 시에만 NORMAL로 전환)
        self.points_info = tk.Text(
            sidebar, height=10, width=24,
            bg="#0d0d1a", fg="#00d4ff",
            font=("Courier", 8),
            state=tk.DISABLED, relief=tk.FLAT
        )
        self.points_info.pack(padx=10, pady=(0, 10))

    def _add_slider(self, parent, label, var, from_, to, res, desc):
        """
        슬라이더 1개 + 현재 값 레이블 + 설명 텍스트를 묶어서 생성하는 헬퍼 메서드.
        3개 슬라이더(밝기·대비·선명도)의 동일한 구조를 한 곳에서 관리한다.

        Args:
            parent (tk.Widget) : 슬라이더를 추가할 부모 위젯
            label  (str)       : 슬라이더 좌측 상단에 표시할 항목 이름
            var    (DoubleVar) : 슬라이더 값과 연동할 tkinter 변수
            from_  (float)     : 슬라이더 최솟값
            to     (float)     : 슬라이더 최댓값
            res    (float)     : 슬라이더 스텝(단계) 크기
            desc   (str)       : 슬라이더 아래 표시할 설명 문구
        """
        # 슬라이더 전체를 감싸는 개별 프레임
        frame = tk.Frame(parent, bg="#16213e")
        frame.pack(fill=tk.X, padx=10, pady=6)

        # 상단 한 줄: [항목명]  ...  [현재 수치]
        header = tk.Frame(frame, bg="#16213e")
        header.pack(fill=tk.X)

        tk.Label(
            header, text=label,
            bg="#16213e", fg="#f0a500",
            font=("Arial", 10, "bold")
        ).pack(side=tk.LEFT)

        # 현재 슬라이더 값을 소수점 2자리로 표시하는 레이블
        val_lbl = tk.Label(
            header, text=f"{var.get():.2f}",
            bg="#16213e", fg="#00d4ff",
            font=("Arial", 9, "bold")
        )
        val_lbl.pack(side=tk.RIGHT)

        # var 값이 변경될 때마다 val_lbl 텍스트를 자동 업데이트 (trace 콜백)
        # *_ 로 trace가 전달하는 (name, index, mode) 인자를 모두 무시
        var.trace_add("write",
                      lambda *_: val_lbl.config(text=f"{var.get():.2f}"))

        # 슬라이더 위젯
        # showvalue=False: 슬라이더 핸들 위에 기본 출력되는 숫자를 숨김 → val_lbl로 대체
        tk.Scale(
            frame,
            variable=var,
            from_=from_, to=to,
            resolution=res,
            orient=tk.HORIZONTAL,
            bg="#16213e", fg="white",
            troughcolor="#2c3e50",   # 슬라이더 홈 색상 (어두운 남색)
            highlightthickness=0,
            showvalue=False,
            length=210
        ).pack(fill=tk.X)

        # 슬라이더 아래 설명 텍스트 (작은 회색 글씨)
        tk.Label(
            frame, text=desc,
            bg="#16213e", fg="#7f8c8d",
            font=("Arial", 7)
        ).pack(anchor="w")

    # 1-2) 이미지 열기 / 캔버스 표시
    def open_image(self):
        """
        파일 탐색기 다이얼로그를 열어 이미지 파일을 선택한다.
        선택된 이미지를 OpenCV로 읽어 원본 캔버스에 표시한다.
        """
        path = filedialog.askopenfilename(
            title="이미지 파일 선택",
            filetypes=[
                ("이미지 파일", "*.jpg *.jpeg *.png *.bmp *.tiff *.webp"),
                ("모든 파일",   "*.*"),
            ]
        )
        if not path:
            return   # 파일 선택 취소 시 아무것도 하지 않음

        # cv2.imread: 이미지를 BGR 포맷의 numpy ndarray로 읽음
        img = cv2.imread(path)
        if img is None:
            messagebox.showerror("오류", "이미지를 불러올 수 없습니다.\n지원 포맷인지 확인하세요.")
            return

        # 새 이미지를 불러왔으므로 이전 변환 결과·조정값 모두 초기화
        self.original_image    = img
        self.transformed_image = None
        self.adjusted_image    = None

        # 점 초기화 + 원본 캔버스에 이미지 표시 (scale_factor 등 함께 계산)
        self.reset_points()

        h, w = img.shape[:2]
        self.update_status(
            f"✅  이미지 로드 완료: {os.path.basename(path)}  ({w} × {h} px)"
        )

    def _show_on_canvas(self, cv_img, canvas, store_scale=False):
        """
        OpenCV 이미지를 지정된 캔버스 크기에 맞게 비율을 유지하며 표시한다.

        변환 공식 (원본 이미지 좌표 → 캔버스 픽셀 좌표):
          canvas_x = orig_x * scale_factor + canvas_offset_x
          canvas_y = orig_y * scale_factor + canvas_offset_y

        역변환 (캔버스 픽셀 좌표 → 원본 이미지 좌표):
          orig_x = (canvas_x - canvas_offset_x) / scale_factor
          orig_y = (canvas_y - canvas_offset_y) / scale_factor

        Args:
            cv_img      (ndarray) : BGR 포맷의 OpenCV 이미지
            canvas      (Canvas)  : 이미지를 그릴 tkinter 캔버스 위젯
            store_scale (bool)    : True일 때 scale_factor·offset 을 인스턴스에 저장.
                                    원본 캔버스 표시 시 반드시 True로 호출해야
                                    클릭 좌표 역변환이 정확하게 동작한다.
        """
        # 캔버스의 현재 표시 크기를 가져오기 전 갱신 요청
        canvas.update_idletasks()
        cw = canvas.winfo_width()
        ch = canvas.winfo_height()

        # 아직 윈도우가 렌더링되기 전이면 기본값 사용
        if cw <= 1 or ch <= 1:
            cw, ch = 540, 420

        h, w = cv_img.shape[:2]

        # 가로·세로 중 더 많이 줄여야 하는 방향의 비율을 채택 (비율 유지 축소)
        scale = min(cw / w, ch / h)
        new_w = int(w * scale)
        new_h = int(h * scale)

        # 이미지를 캔버스 정중앙에 배치하기 위한 여백 계산
        off_x = (cw - new_w) // 2
        off_y = (ch - new_h) // 2

        if store_scale:
            # 클릭 이벤트의 좌표 역변환에 사용할 값 저장
            self.scale_factor    = scale
            self.canvas_offset_x = off_x
            self.canvas_offset_y = off_y

        # OpenCV BGR → RGB 변환 (PIL/tkinter는 RGB 포맷 사용)
        rgb     = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb).resize((new_w, new_h), Image.LANCZOS)
        tk_img  = ImageTk.PhotoImage(pil_img)

        # 기존 캔버스 내용 전부 삭제 후 새 이미지 그리기
        canvas.delete("all")
        canvas.create_image(off_x, off_y, anchor=tk.NW, image=tk_img)

        # ★ 중요: ImageTk.PhotoImage 객체는 지역 변수로 두면 GC(가비지 컬렉터)가
        #   즉시 수거해버려 이미지가 빈 화면으로 보인다.
        #   반드시 인스턴스 변수에 참조를 유지해야 한다.
        if canvas is self.canvas_orig:
            self._tk_orig   = tk_img   # 원본 캔버스용 참조 보관
        else:
            self._tk_result = tk_img   # 결과 캔버스용 참조 보관

    # 1-3) 마우스 클릭 이벤트 처리
    def on_canvas_click(self, event):
        """
        원본 캔버스 클릭 시 자동으로 호출되는 이벤트 핸들러.

        동작:
          1) 캔버스 픽셀 좌표를 원본 이미지 픽셀 좌표로 역변환
          2) self.points 리스트에 좌표 추가
          3) 캔버스에 색깔 마커(원+숫자)와 연결선 그리기
          4) 4점이 모두 선택되면 닫는 선을 추가하고 변환 안내 메시지 출력

        Args:
            event (tk.Event): tkinter 마우스 이벤트 객체.
                              event.x, event.y 에 캔버스 픽셀 좌표가 담긴다.
        """
        # 이미지가 로드되지 않은 상태에서 클릭 시 경고
        if self.original_image is None:
            self.update_status("⚠  먼저 이미지를 열어주세요.")
            return

        # 이미 4점을 다 선택한 경우
        if len(self.points) >= 4:
            self.update_status("⚠  4점이 이미 선택됐습니다. '점 초기화' 후 다시 클릭하세요.")
            return

        # ── 캔버스 좌표 → 원본 이미지 좌표 역변환 ──────────────────
        # 공식: orig = (canvas_pos - offset) / scale
        orig_x = int((event.x - self.canvas_offset_x) / self.scale_factor)
        orig_y = int((event.y - self.canvas_offset_y) / self.scale_factor)

        # 이미지 경계 밖 클릭 무시 (캔버스 여백 부분 클릭 방지)
        h, w = self.original_image.shape[:2]
        if not (0 <= orig_x < w and 0 <= orig_y < h):
            self.update_status("⚠  이미지 영역 바깥을 클릭했습니다. 이미지 위를 클릭해주세요.")
            return

        # 유효한 좌표를 리스트에 추가
        self.points.append((orig_x, orig_y))
        idx = len(self.points)   # 현재 선택된 점 번호 (1~4)

        # ── 캔버스 마커 그리기 ───────────────────────────────────────
        # 점 번호별 구분 색상 (1=빨강, 2=초록, 3=파랑, 4=주황)
        COLORS = ["#e74c3c", "#2ecc71", "#3498db", "#f39c12"]
        color  = COLORS[idx - 1]
        r = 7   # 마커 원의 반지름(픽셀)

        # 원본 좌표 → 캔버스 좌표 변환 (표시용)
        # 공식: canvas_pos = orig * scale + offset
        cx = int(orig_x * self.scale_factor) + self.canvas_offset_x
        cy = int(orig_y * self.scale_factor) + self.canvas_offset_y

        # 마커 원 그리기 (fill: 내부 색, outline: 테두리 색)
        oid = self.canvas_orig.create_oval(
            cx - r, cy - r, cx + r, cy + r,
            fill=color, outline="white", width=2
        )
        # 점 번호 텍스트 그리기 (원 우측 상단에 위치)
        tid = self.canvas_orig.create_text(
            cx + 14, cy - 14,
            text=str(idx), fill=color,
            font=("Arial", 11, "bold")
        )
        # 마커 아이템 ID를 저장 → reset_points()에서 삭제할 때 사용
        self.point_markers.extend([oid, tid])

        # ── 이전 점과 점선 연결 (2번째 점부터) ─────────────────────
        if idx >= 2:
            px, py = self.points[-2]   # 바로 직전에 선택된 점의 원본 좌표
            pcx = int(px * self.scale_factor) + self.canvas_offset_x
            pcy = int(py * self.scale_factor) + self.canvas_offset_y
            lid = self.canvas_orig.create_line(
                pcx, pcy, cx, cy,
                fill="white", width=1,
                dash=(6, 3)   # 6px 실선 + 3px 공백 반복 = 점선 효과
            )
            self.point_markers.append(lid)

        # 4번째 점: 첫 번째 점으로 닫는 선을 추가하여 사각형 완성
        if idx == 4:
            fx, fy = self.points[0]
            fcx = int(fx * self.scale_factor) + self.canvas_offset_x
            fcy = int(fy * self.scale_factor) + self.canvas_offset_y
            lid = self.canvas_orig.create_line(
                cx, cy, fcx, fcy,
                fill="white", width=1, dash=(6, 3)
            )
            self.point_markers.append(lid)
            self.update_status("✅  4점 선택 완료!  '변환 실행' 버튼을 눌러주세요.")
        else:
            # 다음에 클릭해야 할 점 안내
            NEXT_LABELS = ["좌상단", "우상단", "우하단", "좌하단"]
            self.update_status(
                f"점 {idx}/4 선택됨 ({NEXT_LABELS[idx-1]}: x={orig_x}, y={orig_y})"
                + (f"  →  다음: {NEXT_LABELS[idx]} 클릭" if idx < 4 else "")
            )

        # 사이드바 좌표 정보 갱신
        self._refresh_points_info()

    def _refresh_points_info(self):
        """
        사이드바의 '선택된 점 좌표' 텍스트박스를
        현재 self.points 목록 기준으로 갱신한다.
        """
        LABELS = ["① 좌상단", "② 우상단", "③ 우하단", "④ 좌하단"]

        self.points_info.config(state=tk.NORMAL)    # 내용 수정을 위해 편집 가능 상태로
        self.points_info.delete("1.0", tk.END)       # 기존 텍스트 전체 삭제

        for i, (x, y) in enumerate(self.points):
            self.points_info.insert(
                tk.END,
                f"{LABELS[i]}\n   x = {x:>4},  y = {y:>4}\n\n"
            )

        self.points_info.config(state=tk.DISABLE)
                                
    # 1-4) 투시변환 실행
    def apply_transform(self):
        """
        선택된 4개의 점을 이용해 투시변환을 수행하고 결과 캔버스에 표시한다.

        투시변환 원리:
          - src_pts: 원본 이미지에서 사용자가 클릭한 4개의 꼭짓점 좌표
          - dst_pts: 변환 후 직사각형의 4개 꼭짓점 (출력 크기에 맞게 매핑)
          - M = cv2.getPerspectiveTransform(src_pts, dst_pts): 3×3 투시변환 행렬 계산
          - cv2.warpPerspective(img, M, size): 행렬 M을 이미지에 적용
        """
        if self.original_image is None:
            messagebox.showwarning("경고", "이미지를 먼저 불러주세요.")
            return

        if len(self.points) != 4:
            messagebox.showwarning(
                "경고",
                f"정확히 4개의 점이 필요합니다.\n(현재 선택: {len(self.points)}개)"
            )
            return

        # 출력 크기 입력값 파싱 및 유효성 검사
        try:
            out_w = int(self.out_width.get())
            out_h = int(self.out_height.get())
            if out_w <= 0 or out_h <= 0:
                raise ValueError
        except (ValueError, tk.TclError):
            messagebox.showerror("오류", "출력 너비/높이에 양의 정수를 입력하세요.")
            return

        # 투시변환 행렬 계산
        # numpy float32 배열로 변환 (OpenCV 요구 포맷)
        # 클릭 순서: [좌상, 우상, 우하, 좌하]
        src_pts = np.float32(self.points)

        # 변환 후 이미지의 네 꼭짓점 좌표 (직사각형)
        dst_pts = np.float32([
            [0,       0      ],   # 좌상단 모서리
            [out_w-1, 0      ],   # 우상단 모서리
            [out_w-1, out_h-1],   # 우하단 모서리
            [0,       out_h-1],   # 좌하단 모서리
        ])

        # 투시변환 행렬 M (3×3): src_pts의 각 점을 dst_pts로 정확히 매핑하는 변환
        M = cv2.getPerspectiveTransform(src_pts, dst_pts)

        # 행렬 M을 원본 이미지 전체에 적용 → 원근 왜곡이 보정된 이미지 생성
        warped = cv2.warpPerspective(self.original_image, M, (out_w, out_h))

        # 결과 이미지 저장 (슬라이더 조정의 원본으로 사용)
        self.transformed_image = warped
        self.adjusted_image    = warped.copy()

        # 슬라이더 값을 기본값(1.0)으로 초기화
        self.reset_adjustments(silent=True)

        # 결과 캔버스에 표시
        self._show_on_canvas(warped, self.canvas_result)
        self.update_status(
            f"✅  투시변환 완료!  출력 크기: {out_w} × {out_h} px  |"
            f"  '효과 적용'으로 밝기·대비·선명도를 조정하세요."
        )

    # 1-5-1) 하이라이트 보호 밝기 조정
    def _apply_brightness_hp(self, pil_img: Image.Image, factor: float) -> Image.Image:
        """
        하이라이트 보호(Highlight Protection) 밝기 조정.
        기존 ImageEnhance.Brightness 의 선형 곱셈을 비선형 곡선으로 대체한다.

        ┌──────────────────────────────────────────────────────────┐
        │  기존 선형:       output = p × factor                    │
        │    → 밝은 픽셀도 동일 비율 상승 → 255 초과 시 하드 클리핑  │
        │                                                          │
        │  하이라이트 보호: output = 1 − (1 − p) ^ factor          │
        │    → 밝은 영역(p → 1)에서 기울기가 0 에 수렴             │
        │    → 이미 밝은 픽셀은 증가폭이 자동으로 억제됨            │
        └──────────────────────────────────────────────────────────┘

        수식 성질 (factor > 1):
          f(0) = 0       → 순수 검정은 불변
          f(1) = 1       → 순수 흰색도 불변 (하이라이트 완벽 보호)
          f'(p) = factor × (1-p)^(factor-1)
                  → p가 클수록(밝을수록) 기울기 감소 → 증가폭 자동 억제

        밝기 감소(factor < 1):
          선형 그대로 유지. 어두운 쪽은 클리핑 우려가 없으므로 단순 선형 사용.

        구현 방식 — LUT(Look-Up Table):
          0~255 각 정수에 대한 변환값을 미리 계산한 배열을 만들고
          이미지 배열에 인덱싱으로 한 번에 적용 → 픽셀별 반복문 불필요, 고속 처리

        Args:
            pil_img (PIL.Image): RGB 포맷 PIL 이미지
            factor  (float)    : 밝기 배율 (1.0 = 원본, >1.0 밝게, <1.0 어둡게)

        Returns:
            PIL.Image: 밝기 조정이 적용된 RGB PIL 이미지
        """
        # factor가 1.0과 거의 같으면 변환 불필요 (부동소수점 오차 허용)
        if abs(factor - 1.0) < 1e-9:
            return pil_img

        # LUT 배열 생성 (0~255 정수 → 변환값 0~255 정수)
        # np.arange(256): [0, 1, 2, ..., 255]
        # / 255.0 → [0.0, 0.00392, ..., 1.0]  (0.0~1.0 정규화)
        indices = np.arange(256, dtype=np.float32) / 255.0

        if factor > 1.0:
            # 하이라이트 보호 곡선 적용
            # f(p) = 1 - (1-p)^factor
            # 예) factor=2.0, p=0.9(밝음): 1 - 0.1^2 = 0.99  → 증가폭 미미
            #     factor=2.0, p=0.2(어두움): 1 - 0.8^2 = 0.36 → 증가폭 큼
            lut = 1.0 - (1.0 - indices) ** factor
        else:
            # 밝기 감소: 선형 유지
            # 어두운 방향은 클리핑 우려가 없으므로 단순 선형 사용
            lut = indices * factor

        # 0~255 정수 범위로 역스케일 후 uint8 변환
        lut = np.clip(lut * 255.0, 0, 255).astype(np.uint8)

        # 이미지에 LUT 적용
        # PIL 이미지 → numpy 배열 (shape: H×W×C, dtype: uint8)
        img_arr = np.array(pil_img)
        # lut[img_arr]: img_arr의 각 픽셀값(0~255)을 LUT 인덱스로 사용
        #               → 변환된 픽셀값으로 한 번에 교체 (벡터 연산)
        result = lut[img_arr]

        return Image.fromarray(result.astype(np.uint8))

    # 1-5-2) 밝기 / 대비 / 선명도 조정 적용
    def apply_adjustments(self):
        """
        사이드바 슬라이더 값을 투시변환 결과 이미지에 적용하고 결과 캔버스를 갱신한다.

        적용 순서:
          ① 밝기  → _apply_brightness_hp() 로 하이라이트 보호 곡선 적용
                     (기존 ImageEnhance.Brightness 의 선형 방식에서 교체)
          ② 대비  → PIL ImageEnhance.Contrast  (밝기 보정 이후 대비 조정)
          ③ 선명도 → PIL ImageEnhance.Sharpness (마지막에 적용하여 아티팩트 최소화)

        순서가 중요한 이유:
          - 밝기를 먼저 맞춘 뒤 대비를 조정해야 자연스러운 결과가 나온다.
          - 선명도는 항상 마지막에 적용해야 밝기·대비 보정 단계에서
            생긴 미세한 노이즈를 증폭시키지 않는다.
        """
        if self.transformed_image is None:
            messagebox.showwarning("경고", "먼저 '변환 실행'을 눌러 투시변환을 수행하세요.")
            return

        # OpenCV BGR → RGB (PIL 처리를 위해 채널 순서 변환)
        rgb_arr = cv2.cvtColor(self.transformed_image, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb_arr)

        # ① 밝기: 하이라이트 보호 LUT 곡선 적용 ─────────────────────
        #    기존: ImageEnhance.Brightness(pil_img).enhance(factor)  ← 선형, 클리핑 발생
        #    변경: _apply_brightness_hp(pil_img, factor)             ← 비선형, 하이라이트 보호
        pil_img = self._apply_brightness_hp(pil_img, self.brightness.get())

        # ② 대비: PIL 기본 방식 유지 (대비 조정은 하이라이트 보호 불필요)
        pil_img = ImageEnhance.Contrast(pil_img).enhance(self.contrast.get())

        # ③ 선명도: PIL 기본 방식 유지 (선명도는 가장 마지막에)
        pil_img = ImageEnhance.Sharpness(pil_img).enhance(self.sharpness.get())

        # PIL RGB → OpenCV BGR 역변환 후 저장
        result_bgr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        self.adjusted_image = result_bgr

        # 결과 캔버스 갱신
        self._show_on_canvas(result_bgr, self.canvas_result)
        self.update_status(
            f"🎨  효과 적용 완료  |"
            f"  밝기: {self.brightness.get():.2f}"
            f"  대비: {self.contrast.get():.2f}"
            f"  선명도: {self.sharpness.get():.2f}"
        )

    def reset_adjustments(self, silent=False):
        """
        밝기·대비·선명도 슬라이더를 모두 기본값(1.0)으로 초기화한다.

        Args:
            silent (bool): True이면 상태 메시지를 출력하지 않음.
                           apply_transform() 내부에서 자동 초기화 시 사용.
        """
        self.brightness.set(1.0)
        self.contrast.set(1.0)
        self.sharpness.set(1.0)

        if not silent:
            self.update_status("↩  슬라이더가 기본값(1.0)으로 초기화되었습니다.")

    # 1-6) 점 초기화 / 저장 / 상태 메시지
    def reset_points(self):
        """
        선택된 4점과 캔버스 위 마커를 모두 삭제하고
        원본 이미지를 캔버스에 다시 표시한다.
        이미지를 새로 불러올 때도 내부적으로 호출된다.
        """
        self.points.clear()   # 좌표 리스트 비우기

        # 캔버스에 그려진 모든 마커(원·텍스트·선) 삭제
        for item_id in self.point_markers:
            self.canvas_orig.delete(item_id)
        self.point_markers.clear()

        # 사이드바 좌표 텍스트박스 초기화
        self._refresh_points_info()

        # 원본 이미지가 있으면 캔버스에 다시 표시하고 scale_factor 재계산
        if self.original_image is not None:
            self._show_on_canvas(
                self.original_image, self.canvas_orig,
                store_scale=True   # 반드시 True: 클릭 좌표 역변환 파라미터 갱신
            )
            self.update_status("🔄  점이 초기화되었습니다. 4개의 점을 순서대로 클릭해주세요.")

    def save_result(self):
        """
        최종 이미지를 파일로 저장한다.
        슬라이더 효과가 적용된 adjusted_image 를 우선 저장하고,
        효과가 없다면 투시변환 결과(transformed_image)를 저장한다.
        """
        # 저장할 이미지 선택 (효과 적용본 → 변환본 순서로 우선순위)
        img_to_save = (
            self.adjusted_image
            if self.adjusted_image is not None
            else self.transformed_image
        )

        if img_to_save is None:
            messagebox.showwarning(
                "경고", "저장할 이미지가 없습니다.\n투시변환을 먼저 실행하세요."
            )
            return

        # 저장 경로 선택 다이얼로그
        path = filedialog.asksaveasfilename(
            title="결과 이미지 저장",
            defaultextension=".png",
            filetypes=[
                ("PNG  (무손실)",        "*.png"),
                ("JPEG (손실 압축)",     "*.jpg"),
                ("BMP  (무압축 비트맵)", "*.bmp"),
                ("모든 파일",            "*.*"),
            ]
        )
        if not path:
            return   # 저장 취소

        # OpenCV로 이미지 파일 저장 (BGR 포맷 그대로 저장 — cv2.imwrite 가 처리)
        success = cv2.imwrite(path, img_to_save)
        if success:
            self.update_status(f"💾  저장 완료: {os.path.basename(path)}")
            messagebox.showinfo(
                "저장 완료",
                f"이미지가 성공적으로 저장되었습니다!\n\n경로: {path}"
            )
        else:
            messagebox.showerror("저장 실패", "이미지 저장 중 오류가 발생했습니다.")

    def update_status(self, msg: str):
        
        """
        툴바의 상태 레이블 텍스트를 업데이트한다.

        Args:
            msg (str): 표시할 상태 메시지
        """
        self.status_label.config(text=msg)

""" 프로그램 진입점 """
if __name__ == "__main__":
    root = tk.Tk()
    root.title("🖼️  투시변환 이미지 처리기")
    root.geometry("1250x720")         # 초기 윈도우 크기 (너비 × 높이)
    root.minsize(900, 550)            # 최소 윈도우 크기 제한
    root.configure(bg="#1a1a2e")      # 배경색: 진한 남색

    app = PerspectiveTransformApp(root)
    root.mainloop()   # tkinter 이벤트 루프 시작 (윈도우가 닫힐 때까지 실행 유지)