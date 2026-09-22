"""
Wafer Stage Controller UI v6
"""

SAVE_DEBUG_IMAGES = True   # set False to skip writing scan_debug/ images
import sys
import json
import serial
import serial.tools.list_ports
import threading
import time
from pathlib import Path
from pico_controller import PicoController
from device_detector import load_model, detect_bond_pads, pixels_per_mm, assign_stage_coords, find_devices
from wafer_scanner import WaferScanner, DeviceRegistry

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QPushButton, QLabel, QFrame, QStackedWidget,
    QComboBox, QDoubleSpinBox, QSpinBox, QLineEdit,
    QSizePolicy, QScrollArea, QFileDialog, QAbstractSpinBox, QMenu
)
from PySide6.QtCore import Qt, QPointF, QRectF, QSize, QTimer, Signal, QObject
from PySide6.QtGui import (
    QFont, QColor, QPainter, QPen, QBrush, QPolygonF, QFontMetrics
)

C = {
    "bg0":"#090E17","bg1":"#0D1117","bg2":"#151B25","bg3":"#1A2233",
    "bg4":"#1F2A3D","bg_input":"#0B1018",
    "navy":"#1B3A6B","navy_light":"#245299","navy_bright":"#2E6BC6",
    "navy_glow":"#4A90E2","navy_subtle":"#142240",
    "text1":"#E2E8F0","text2":"#7B8A9E","text3":"#3D4A5C",
    "green":"#1A7F37","amber":"#C69026","red":"#CF3333","blue":"#1A6FD4",
    "border":"#1C2536","border_light":"#283548","statusbar":"#0A1628",
}
F_MAIN="Segoe UI"; F_MONO="Cascadia Code"

def ss():
    return f"""
    QMainWindow{{background-color:{C['bg1']};color:{C['text1']};}}
    QWidget{{background-color:transparent;color:{C['text1']};font-family:{F_MAIN};font-size:12px;}}
    QFrame#rightPanel{{background-color:{C['bg2']};border-left:1px solid {C['border']};}}
    QFrame#statusBar{{background-color:{C['statusbar']};border-top:1px solid {C['border']};min-height:26px;max-height:26px;}}
    QPushButton#tabBtn{{background-color:transparent;color:{C['text2']};border:none;border-bottom:2px solid transparent;padding:7px 20px;font-size:12px;font-weight:500;}}
    QPushButton#tabBtn:hover{{color:{C['text1']};background-color:{C['bg4']};}}
    QPushButton#tabBtn[active="true"]{{color:{C['text1']};border-bottom:2px solid {C['navy_glow']};}}
    QPushButton{{background-color:{C['bg3']};color:{C['text1']};border:1px solid {C['border']};border-radius:5px;padding:6px 12px;font-size:12px;font-weight:500;}}
    QPushButton:hover{{background-color:{C['bg4']};border-color:{C['navy']};}}
    QPushButton:pressed{{background-color:{C['navy_subtle']};}}
    QPushButton#accentBtn{{background-color:{C['navy']};border:1px solid {C['navy_light']};color:white;}}
    QPushButton#accentBtn:hover{{background-color:{C['navy_light']};}}
    QPushButton#dangerBtn{{background-color:{C['red']};border:1px solid #E04040;color:white;}}
    QPushButton#dangerBtn:hover{{background-color:#E04040;}}
    QPushButton#jogBtn{{background-color:{C['bg3']};color:{C['text1']};border:1px solid {C['border']};border-radius:7px;font-size:14px;font-weight:600;}}
    QPushButton#jogBtn:hover{{background-color:{C['navy']};border-color:{C['navy_light']};}}
    QPushButton#jogBtn:pressed{{background-color:{C['navy_subtle']};}}
    QPushButton#stepBtn{{background-color:{C['bg3']};color:{C['text2']};border:1px solid {C['border']};border-radius:4px;padding:4px 6px;font-size:11px;min-width:38px;max-height:26px;}}
    QPushButton#stepBtn[active="true"]{{background-color:{C['navy']};color:white;border-color:{C['navy_light']};}}
    QPushButton#deviceBtn{{background-color:{C['bg3']};color:{C['text2']};border:1px solid {C['border']};border-radius:4px;padding:4px 8px;font-size:11px;}}
    QPushButton#deviceBtn[active="true"]{{background-color:{C['navy_subtle']};color:{C['navy_glow']};border-color:{C['navy']};}}
    QPushButton#waferTypeBtn{{background-color:{C['bg3']};color:{C['text2']};border:1px solid {C['border']};border-radius:4px;padding:4px 10px;font-size:11px;}}
    QPushButton#waferTypeBtn[active="true"]{{background-color:{C['navy_subtle']};color:{C['navy_glow']};border-color:{C['navy']};}}
    QDoubleSpinBox,QSpinBox{{background-color:{C['bg_input']};color:{C['text1']};border:1px solid {C['border']};border-radius:5px;padding:4px 8px;font-size:11px;font-family:{F_MONO};}}
    QDoubleSpinBox::up-button,QDoubleSpinBox::down-button,QSpinBox::up-button,QSpinBox::down-button{{width:0;height:0;border:none;}}
    QDoubleSpinBox:focus,QSpinBox:focus{{border-color:{C['navy']};}}
    QDoubleSpinBox:disabled,QSpinBox:disabled{{color:{C['text3']};background-color:{C['bg2']};}}
    QComboBox{{background-color:{C['bg_input']};color:{C['text1']};border:1px solid {C['border']};border-radius:5px;padding:4px 8px;font-size:11px;font-family:{F_MONO};}}
    QComboBox:focus{{border-color:{C['navy']};}}
    QComboBox::drop-down{{border:none;width:20px;}}
    QComboBox QAbstractItemView{{background-color:{C['bg3']};color:{C['text1']};border:1px solid {C['border']};selection-background-color:{C['navy']};}}
    QLineEdit{{background-color:{C['bg_input']};color:{C['text1']};border:1px solid {C['border']};border-radius:5px;padding:4px 8px;font-size:11px;font-family:{F_MONO};}}
    QLineEdit:focus{{border-color:{C['navy']};}}
    QLabel{{color:{C['text2']};font-size:11px;}}
    QLabel#sectionTitle{{color:{C['text1']};font-size:11px;font-weight:600;padding:1px 0;}}
    QLabel#readonlyVal{{color:{C['navy_glow']};font-size:11px;font-family:{F_MONO};padding:3px 6px;background-color:{C['bg3']};border:1px solid {C['border']};border-radius:5px;}}
    QLabel#staticVal{{color:{C['text3']};font-size:11px;font-family:{F_MONO};padding:3px 6px;background-color:{C['bg2']};border:1px solid {C['border']};border-radius:5px;}}
    QScrollBar:vertical{{background:transparent;width:5px;}}
    QScrollBar::handle:vertical{{background:{C['border_light']};border-radius:2px;min-height:20px;}}
    QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{{height:0;}}
    """

def stitle(t):
    l=QLabel(t); l.setObjectName("sectionTitle"); return l

def sep():
    s=QFrame(); s.setFrameShape(QFrame.HLine); s.setFixedHeight(1)
    s.setStyleSheet(f"background-color:{C['border']};border:none;"); return s

def badge(text,color):
    l=QLabel(text); l.setFixedHeight(18)
    l.setStyleSheet(f"background-color:{color}20;color:{color};border:1px solid {color}40;border-radius:3px;padding:1px 8px;font-size:10px;font-weight:600;")
    return l

def tog(active,group):
    for b in group:
        b.setProperty("active",b==active)
        b.style().unpolish(b); b.style().polish(b)

def cfg_row(layout, label_text, widget, label_width=110):
    """Consistent config row: label + widget on same line"""
    r=QHBoxLayout(); r.setSpacing(8)
    l=QLabel(label_text); l.setFixedWidth(label_width); r.addWidget(l)
    r.addWidget(widget); r.addStretch()
    layout.addLayout(r)


# ── Snap Speed Slider ───────────────────────────────────
class SnapSlider(QWidget):
    DIVISIONS=[("60%",0.60),("80%",0.80),("100%",1.00),("105%",1.05),("110%",1.10)]

    def __init__(self):
        super().__init__()
        self.current_idx=2
        self.setFixedHeight(44)
        self.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self,e): self._upd(e.position().x())
    def mouseMoveEvent(self,e):
        if e.buttons()&Qt.LeftButton: self._upd(e.position().x())

    def _upd(self,x):
        n=len(self.DIVISIONS); pad=20; w=self.width()-pad*2
        if n>1: idx=round((x-pad)/(w/(n-1)))
        else: idx=0
        idx=max(0,min(n-1,idx))
        if idx!=self.current_idx: self.current_idx=idx; self.update()

    def get_multiplier(self): return self.DIVISIONS[self.current_idx][1]

    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        n=len(self.DIVISIONS); pad=20; w=self.width()-pad*2; cy=18; step=w/(n-1) if n>1 else 1

        p.setPen(QPen(QColor(C["border_light"]),2))
        p.drawLine(pad,cy,pad+w,cy)

        for i,(lbl,_) in enumerate(self.DIVISIONS):
            x=pad+int(i*step); active=i==self.current_idx
            p.setPen(QPen(QColor(C["navy_glow"] if active else C["border_light"]),2))
            p.drawLine(x,cy-4,x,cy+4)
            p.setPen(QPen(QColor(C["text1"] if active else C["text3"]),1))
            p.setFont(QFont(F_MAIN,9,QFont.Bold if active else QFont.Normal))
            p.drawText(x-16,cy+7,32,14,Qt.AlignCenter,lbl)

        hx=pad+int(self.current_idx*step)
        p.setPen(Qt.NoPen); p.setBrush(QColor(C["navy_glow"]))
        p.drawEllipse(hx-7,cy-7,14,14)
        p.setBrush(QColor(C["bg0"])); p.drawEllipse(hx-3,cy-3,6,6)
        p.end()




# ── Live Feed ───────────────────────────────────────────
class LiveFeedWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
        self.setMinimumSize(400,300)
        self.pos_x=0.0; self.pos_y=0.0
        self.homed=False
        self.bond_pads=[]; self.scan_x=None; self.scan_y=None
        self.travel_x=20.0; self.travel_y=20.0
        self.devices=[]          # list of {cx_mm, cy_mm} for minimap
        self.yolo_boxes=[]       # list of (x1,y1,x2,y2) pixel boxes to overlay
        self._goto_cb=None       # callback(cx_mm, cy_mm) → move stage to device
        self._delete_cb=None     # callback(cx_mm, cy_mm) → remove device from registry
        self._pixmap=None        # current camera frame as QPixmap
        self._frame=None         # current camera frame as QImage (legacy)
        self._bgr_frame=None     # current camera frame as BGR numpy array (for detection)
        self._frame_w=0; self._frame_h=0   # original frame dimensions for box scaling
        self._display_ppm=200.0  # px/mm for scale bar (default 5 µm/px); updated after calibration

    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        w,h=self.width(),self.height(); cx,cy=w//2,h//2

        if self._pixmap:
            p.drawPixmap(self.rect(), self._pixmap)
        else:
            p.fillRect(self.rect(),QColor(C["bg0"]))
            p.setPen(QPen(QColor(C["border"]),0.3))
            for x in range(0,w,50): p.drawLine(x,0,x,h)
            for y in range(0,h,50): p.drawLine(0,y,w,y)

        # YOLO detection boxes — scale from original frame coords to widget coords
        if self.yolo_boxes and self._frame_w and self._frame_h:
            sx = w / self._frame_w; sy = h / self._frame_h
            p.setPen(QPen(QColor("#00FF88"),1.5))
            p.setBrush(Qt.NoBrush)
            for (x1,y1,x2,y2) in self.yolo_boxes:
                p.drawRect(int(x1*sx),int(y1*sy),int((x2-x1)*sx),int((y2-y1)*sy))

        # Crosshair with gap
        gap,arm=8,22
        p.setPen(QPen(QColor(C["navy_glow"]),1.5))
        p.drawLine(cx-arm,cy,cx-gap,cy); p.drawLine(cx+gap,cy,cx+arm,cy)
        p.drawLine(cx,cy-arm,cx,cy-gap); p.drawLine(cx,cy+gap,cx,cy+arm)

        # Not connected — bottom left (only when no live feed)
        if not self._pixmap:
            p.setPen(QPen(QColor(C["text3"]),1)); p.setFont(QFont(F_MAIN,10))
            p.drawText(14,h-12,"Camera feed — not connected")

        # Position overlay — bottom right
        p.setPen(QPen(QColor(C["navy_glow"]),1))
        fpos=QFont(F_MONO,11); fpos.setWeight(QFont.DemiBold); p.setFont(fpos)
        if self.homed:
            pt=f"X {self.pos_x:7.4f}   Y {self.pos_y:7.4f} mm"
        else:
            pt="X    —         Y    — mm"
        fm=QFontMetrics(fpos); tw=fm.horizontalAdvance(pt)
        p.drawText(w-tw-16, h-30, pt)

        # Scale bar — anchored right wall, BELOW coords, 10px gap.
        # Picks the largest round physical length whose pixel width falls in
        # [50, 160] px so the bar is always readable regardless of zoom level.
        ppm = max(self._display_ppm, 1.0)
        _candidates_mm = [0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0]
        bar_mm = _candidates_mm[0]
        for _c in _candidates_mm:
            _px = _c * ppm
            if 50 <= _px <= 160:
                bar_mm = _c
        bw = max(4, int(bar_mm * ppm))
        bx = w - bw - 16; by = h - 10
        p.setPen(QPen(QColor(C["text2"]),1.5))
        p.drawLine(bx,by,bx+bw,by)
        p.drawLine(bx,by-4,bx,by+4); p.drawLine(bx+bw,by-4,bx+bw,by+4)
        p.setFont(QFont(F_MAIN,9))
        _lbl = f"{bar_mm*1000:.0f} µm" if bar_mm < 1.0 else f"{bar_mm:.0f} mm"
        p.drawText(bx,by-13,bw,12,Qt.AlignCenter,_lbl)

        # Mini map — bottom left
        self._minimap(p,w,h)
        p.end()

    def _minimap_rect(self,w,h):
        mw,mh=120,120; mx,my=12,h-mh-36; pad=6
        sq=mw-pad*4; sx=mx+(mw-sq)//2; sy=my+18
        return mx,my,mw,mh,sq,sx,sy,pad

    def _minimap(self,p,w,h):
        mx,my,mw,mh,sq,sx,sy,pad = self._minimap_rect(w,h)
        p.setPen(QPen(QColor(C["border_light"]),1)); p.setBrush(QColor(C["bg1"]))
        p.drawRoundedRect(mx,my,mw,mh,5,5)
        p.setPen(QPen(QColor(C["text2"]),1)); p.setFont(QFont(F_MAIN,8))
        p.drawText(mx+pad,my+13,"Wafer map")
        p.setPen(QPen(QColor(C["navy"]),1)); p.setBrush(QColor(C["navy_subtle"]))
        p.drawRect(sx,sy,sq,sq)
        # Draw detected device centers as clickable dots
        for dev in self.devices:
            px=sx+int(dev["cx_mm"]/max(self.travel_x,0.01)*sq)
            py=sy+int(dev["cy_mm"]/max(self.travel_y,0.01)*sq)
            px=max(sx,min(sx+sq,px)); py=max(sy,min(sy+sq,py))
            p.setPen(QPen(QColor(C["navy_glow"]),1))
            p.setBrush(QColor(C["navy_bright"]))
            p.drawRect(px-4,py-4,8,8)
        # Current scan position
        if self.scan_x is not None:
            scx=sx+int(self.scan_x/max(self.travel_x,0.01)*sq)
            scy=sy+int(self.scan_y/max(self.travel_y,0.01)*sq)
            arm=6
            p.setPen(QPen(QColor(C["green"]),2))
            p.drawLine(scx-arm,scy,scx+arm,scy)
            p.drawLine(scx,scy-arm,scx,scy+arm)

    def mousePressEvent(self,event):
        """Handle clicks on device dots in the minimap — shows context menu."""
        if not self.devices:
            return
        w,h=self.width(),self.height()
        mx,my,mw,mh,sq,sx,sy,pad = self._minimap_rect(w,h)
        ex,ey = event.position().x(), event.position().y()
        # Find closest device dot within click radius
        best_dist=12; best_dev=None
        for dev in self.devices:
            px=sx+int(dev["cx_mm"]/max(self.travel_x,0.01)*sq)
            py=sy+int(dev["cy_mm"]/max(self.travel_y,0.01)*sq)
            dist=((ex-px)**2+(ey-py)**2)**0.5
            if dist<best_dist:
                best_dist=dist; best_dev=dev
        if best_dev:
            menu = QMenu(self)
            menu.setStyleSheet(
                f"QMenu{{background:{C['bg2']};color:{C['text1']};border:1px solid {C['border_light']};padding:4px;}}"
                f"QMenu::item{{padding:4px 18px;border-radius:3px;}}"
                f"QMenu::item:selected{{background:{C['navy']};color:{C['text1']};}}"
            )
            act_goto   = menu.addAction(f"Go to device  ({best_dev['cx_mm']:.3f}, {best_dev['cy_mm']:.3f})")
            act_delete = menu.addAction("Delete device")
            chosen = menu.exec(event.globalPosition().toPoint())
            if chosen == act_goto and self._goto_cb:
                self._goto_cb(best_dev["cx_mm"], best_dev["cy_mm"])
            elif chosen == act_delete and self._delete_cb:
                self._delete_cb(best_dev["cx_mm"], best_dev["cy_mm"])

    def set_frame(self, frame_bgr):
        """Update live feed with a new BGR frame from OpenCV."""
        import cv2
        from PySide6.QtGui import QImage, QPixmap
        self._bgr_frame = frame_bgr.copy()   # keep raw BGR for detection
        self._frame_h, self._frame_w = frame_bgr.shape[:2]
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        self._pixmap = QPixmap.fromImage(qimg)
        self._frame = qimg.copy()
        self.update()


# ── E-Stop ──────────────────────────────────────────────
class EStopButton(QPushButton):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(46); self.setCursor(Qt.PointingHandCursor)
        self.setText(""); self.setStyleSheet("background:transparent;border:none;")

    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        w,h=self.width(),self.height(); cx,cy=w/2,h/2
        hw=min(w-8,300); hh=h-6; indent=hh*0.35
        pts=QPolygonF([
            QPointF(cx-hw/2+indent,cy-hh/2),QPointF(cx+hw/2-indent,cy-hh/2),
            QPointF(cx+hw/2,cy),QPointF(cx+hw/2-indent,cy+hh/2),
            QPointF(cx-hw/2+indent,cy+hh/2),QPointF(cx-hw/2,cy),
        ])
        if self.underMouse():
            p.setBrush(QColor("#E04040")); p.setPen(QPen(QColor("#FF5555"),2))
        else:
            p.setBrush(QColor(C["red"])); p.setPen(QPen(QColor("#E04040"),1.5))
        p.drawPolygon(pts)
        p.setPen(QPen(QColor("white"),1))
        f=QFont(F_MAIN,13); f.setWeight(QFont.Bold); p.setFont(f)
        p.drawText(self.rect(),Qt.AlignCenter,"EMERGENCY STOP")
        p.end()


# ── Control Panel ───────────────────────────────────────
class ControlPanel(QWidget):
    def __init__(self, pico, main_window):
        super().__init__()
        self.pico = pico
        self.main_window = main_window
        # step size in mm (default 100μm = 0.1mm)
        self.step_mm = 0.1
        # speed index (default Normal = index 2)
        self.speed_idx = 2
        layout=QVBoxLayout(self)
        layout.setSpacing(5); layout.setContentsMargins(12,8,12,8)

        # Jog
        layout.addWidget(stitle("Jog"))

        # Outer: XY cross left, Z pills right (probe only)
        jog_outer=QWidget()
        jog_outer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        jo_lay=QHBoxLayout(jog_outer)
        jo_lay.setSpacing(5); jo_lay.setContentsMargins(0,0,0,0)

        # XY cross - fully flexible, shrinks to fit any screen
        xy_widget=QWidget()
        xy_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        xy_widget.setMaximumWidth(230)
        jg=QGridLayout(xy_widget)
        jg.setSpacing(3); jg.setContentsMargins(0,0,0,0)
        jg.setHorizontalSpacing(5)
        jg.setVerticalSpacing(3)
        jg.setColumnStretch(0,1); jg.setColumnStretch(1,1); jg.setColumnStretch(2,1)
        jg.setRowStretch(0,1); jg.setRowStretch(1,1); jg.setRowStretch(2,1)

        btn_yp=QPushButton("Y+"); btn_yp.setObjectName("jogBtn")
        btn_xm=QPushButton("X−"); btn_xm.setObjectName("jogBtn")
        btn_xp=QPushButton("X+"); btn_xp.setObjectName("jogBtn")
        btn_ym=QPushButton("Y−"); btn_ym.setObjectName("jogBtn")

        for b in [btn_yp,btn_xm,btn_xp,btn_ym]:
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            b.setMinimumSize(36,16)
            b.setMaximumWidth(72)

        center=QWidget()
        center.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        center.setMaximumWidth(72)

        jg.addWidget(btn_yp,0,1)
        jg.addWidget(btn_xm,1,0)
        jg.addWidget(center,1,1)
        jg.addWidget(btn_xp,1,2)
        jg.addWidget(btn_ym,2,1)

        # Connect jog buttons
        # Y is inverted relative to camera view, so Y+/Y- are swapped
        btn_yp.clicked.connect(lambda: self._jog("Y", -1))
        btn_ym.clicked.connect(lambda: self._jog("Y", +1))
        btn_xp.clicked.connect(lambda: self._jog("X", +1))
        btn_xm.clicked.connect(lambda: self._jog("X", -1))

        jo_lay.addWidget(xy_widget, stretch=1)

        jog_outer.setFixedHeight(155)
        layout.addWidget(jog_outer)

        # Step size
        layout.addWidget(stitle("Step size [μm]"))
        sr=QHBoxLayout(); sr.setSpacing(3)
        self.step_btns=[]
        # 16x microstepping: 0.15625 μm/step, 6400 steps/mm
        step_values = [1.0, 0.1, 0.01, 0.001, 0.00015625]  # mm equivalents
        for i,(s,v) in enumerate(zip(["1000","100","10","1","0.15"], step_values)):
            b=QPushButton(s); b.setObjectName("stepBtn"); b.setProperty("active",i==1)
            b.clicked.connect(lambda _,b=b,v=v: self._set_step(b,v))
            self.step_btns.append(b); sr.addWidget(b)
        layout.addLayout(sr)

        # Speed
        layout.addWidget(stitle("Speed"))
        self.speed_slider=SnapSlider()
        self.speed_slider.mousePressEvent = self._speed_press
        self.speed_slider.mouseMoveEvent  = self._speed_drag
        layout.addWidget(self.speed_slider)
        layout.addWidget(sep())

        # Actions
        layout.addWidget(stitle("Actions"))
        ar=QHBoxLayout(); ar.setSpacing(3)
        for t,cmd in [("Home X","X"),("Home Y","Y"),("Home All","ALL")]:
            b=QPushButton(t); b.setObjectName("accentBtn")
            b.clicked.connect(lambda _,c=cmd: self._home(c))
            ar.addWidget(b)
        layout.addLayout(ar)

        # Go to position
        gt_lbl=QLabel("Go to position")
        gt_lbl.setStyleSheet(f"color:{C['text2']};font-size:10px;padding:2px 0 0 0;")
        layout.addWidget(gt_lbl)
        gr=QHBoxLayout(); gr.setSpacing(5)
        xl=QLabel("X"); xl.setFixedWidth(10); xl.setStyleSheet(f"color:{C['text2']};")
        self.gx=QDoubleSpinBox(); self.gx.setRange(0,25); self.gx.setDecimals(3)
        self.gx.setSuffix(" mm"); self.gx.setButtonSymbols(QAbstractSpinBox.NoButtons)
        yl=QLabel("Y"); yl.setFixedWidth(10); yl.setStyleSheet(f"color:{C['text2']};")
        self.gy=QDoubleSpinBox(); self.gy.setRange(0,25); self.gy.setDecimals(3)
        self.gy.setSuffix(" mm"); self.gy.setButtonSymbols(QAbstractSpinBox.NoButtons)
        bg=QPushButton("Go"); bg.setObjectName("accentBtn"); bg.setFixedWidth(40)
        bg.clicked.connect(self._goto)
        gr.addWidget(xl); gr.addWidget(self.gx); gr.addWidget(yl); gr.addWidget(self.gy); gr.addWidget(bg)
        layout.addLayout(gr)
        layout.addWidget(sep())

        layout.addWidget(sep())

        # Wafer type
        layout.addWidget(stitle("Memristor Design Type"))
        wr=QHBoxLayout(); wr.setSpacing(3)
        self.bcp=QPushButton("Crosspoint"); self.bcp.setObjectName("waferTypeBtn"); self.bcp.setProperty("active",True)
        self.bcp.clicked.connect(lambda:self._wtype("cp"))
        self.bcb=QPushButton("Crossbar"); self.bcb.setObjectName("waferTypeBtn"); self.bcb.setProperty("active",False)
        self.bcb.clicked.connect(lambda:self._wtype("cb"))
        wr.addWidget(self.bcp); wr.addWidget(self.bcb)
        layout.addLayout(wr)
        layout.addWidget(sep())

        # Scan & Detection — Start Detection + Add Here on one row
        layout.addWidget(stitle("Scan & Detection"))
        det_row=QHBoxLayout(); det_row.setSpacing(3)
        self._b_det=QPushButton("▶  Scan  [Crosspoint]"); self._b_det.setObjectName("accentBtn"); self._b_det.setStyleSheet("font-size:12px;font-weight:600;")
        self._b_det.clicked.connect(self._start_detection)
        b_add=QPushButton("+ Add Device"); b_add.setObjectName("accentBtn"); b_add.setStyleSheet("font-size:12px;")
        b_add.clicked.connect(self._add_device_here)
        det_row.addWidget(self._b_det); det_row.addWidget(b_add)
        layout.addLayout(det_row)
        b_probe=QPushButton("Start Probing Sequence"); b_probe.setObjectName("accentBtn"); b_probe.setStyleSheet("font-size:12px;font-weight:600;")
        layout.addWidget(b_probe)
        ps_row=QHBoxLayout(); ps_row.setSpacing(3)
        b_pause=QPushButton("▏▏ Pause"); b_pause.setStyleSheet("font-size:12px;font-weight:600;")
        self._b_stop=QPushButton("■  Stop"); self._b_stop.setObjectName("dangerBtn"); self._b_stop.setStyleSheet("font-size:12px;font-weight:600;")
        self._b_stop.clicked.connect(self._stop_detection)
        ps_row.addWidget(b_pause); ps_row.addWidget(self._b_stop)
        layout.addLayout(ps_row)

        layout.addSpacing(4)
        layout.addWidget(EStopButton())

    # ── Control actions ────────────────────────────────
    def _run(self, fn):
        """Run fn() in a background thread, refresh position when done."""
        def _worker():
            fn()
            self.main_window._sig_refresh_pos.emit()
        threading.Thread(target=_worker, daemon=True).start()

    def _jog(self, axis, direction):
        if not self.pico.connected:
            return
        mm = self.step_mm * direction
        self._run(lambda: self.pico.move(axis, mm))

    def _home(self, target):
        if not self.pico.connected:
            return
        self._run(lambda: self.pico.home(target))

    def _goto(self):
        if not self.pico.connected:
            return
        x = self.gx.value()
        y = self.gy.value()
        def do_goto():
            if not self.pico.homed:
                self.pico.home("ALL")
            # Home is m2_min: positive spinbox Y = away from home = positive motor direction
            self.pico.goto(x, y)
        self._run(do_goto)

    def _set_step(self, btn, mm):
        self.step_mm = mm
        tog(btn, self.step_btns)

    def _speed_press(self, e):
        SnapSlider.mousePressEvent(self.speed_slider, e)
        self._apply_speed()

    def _speed_drag(self, e):
        SnapSlider.mouseMoveEvent(self.speed_slider, e)
        self._apply_speed()

    def _apply_speed(self):
        idx = self.speed_slider.current_idx
        self.speed_idx = idx
        if self.pico.connected:
            self.pico.set_speed(idx)


    def _wtype(self,t):
        self.bcp.setProperty("active",t=="cp"); self.bcb.setProperty("active",t!="cp")
        for b in [self.bcp,self.bcb]: b.style().unpolish(b); b.style().polish(b)
        label = "Crosspoint" if t=="cp" else "Crossbar"
        self._b_det.setText(f"▶  Scan  [{label}]")

    def _start_detection(self):
        """Start the wafer scan + YOLO detection sequence."""
        if not self.pico.connected:
            return
        mw = self.main_window
        wafer_type = "crosspoint" if self.bcp.property("active") else "crossbar"
        travel_x = mw.fp._travel_x_spin.value()
        travel_y = mw.fp._travel_y_spin.value()
        model_path = r"C:\Users\cy\Desktop\Monash_Engineering\FYP\firmware\src\yolo_model\runs_original\detect\train\weights\best.pt"
        conf = mw.fp._conf_spin.value() / 100.0

        # Use last estimated FOV as default; reset only on first launch (stays 2.0 until first detection)
        mw.live_feed.travel_x = travel_x
        mw.live_feed.travel_y = travel_y
        mw.registry.clear()
        mw.live_feed.devices = []
        mw.live_feed.scan_x = None
        mw.live_feed.scan_y = None
        mw.live_feed.update()

        original_speed_idx = self.speed_idx
        self.pico.set_speed(0)   # 60% speed — quieter, less ramping

        def _run():
            import os, time, cv2
            import numpy as np
            import copy
            import device_detector as dd
            dd.CONFIDENCE_THRESHOLD = conf
            model = dd.load_model(model_path)
            if model is None:
                print("[scan] Model failed to load")
                self.pico.set_speed(original_speed_idx)
                return
            mw._model = model   # store for fine-centering in _on_device_goto

            debug_dir = None
            if SAVE_DEBUG_IMAGES:
                debug_dir = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                    "scan_debug", time.strftime("%Y%m%d_%H%M%S"))
                os.makedirs(os.path.join(debug_dir, "raw"), exist_ok=True)
                os.makedirs(os.path.join(debug_dir, "annotated"), exist_ok=True)
                print(f"[scan] Debug images → {debug_dir}")

            # ── Always home first — resets pos tracking to zero ────────
            print("[scan] Homing stage …")
            self.pico.home("ALL")

            # ── Calibrate ppm via phase correlation ────────────────────
            def _grab_gray(settle=0.5):
                """Capture current frame as float32 greyscale. Returns (gray, bgr) or (None, None)."""
                time.sleep(settle)
                bgr = mw.live_feed._bgr_frame
                if bgr is None:
                    return None, None
                return cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32), bgr

            def _calibrate_ppm():
                """
                Measure pixel/mm calibration via phase correlation.
                Performs an X-axis AND a Y-axis move to build a 2×2
                pixel-to-stage matrix A such that:
                    [stage_dx, stage_dy] = A @ [pixel_dx_from_center, pixel_dy_from_center]
                Correctly handles camera rotation relative to stage axes.
                Returns (A, ppm_scalar) or (None, None) on failure.
                ppm_scalar is used for FOV size estimation only.
                Stage returns to calibration start position when done.
                """
                calib_d = 1.0   # 1 mm move in each axis
                MIN_VAR = 30.0
                # Always start from a safe interior position so that neither
                # the calibration moves nor the return moves can interact with
                # a limit switch.  After homing pos=(0,0) is right on the
                # limit switches — moving away 1 mm and then trying to return
                # to exactly 0 can cause the firmware's limit-switch logic to
                # stop the return move early and leave pos tracking wrong.
                SAFE = 2.0
                if self.pico.pos_x < SAFE or self.pico.pos_y < SAFE:
                    self.pico.goto(SAFE, SAFE)
                    time.sleep(0.5)

                start_x, start_y = self.pico.pos_x, self.pico.pos_y
                gray0, _ = _grab_gray(settle=0.8)

                # Sweep to find a position with visible texture if current is too uniform
                if gray0 is None or float(np.var(gray0)) < MIN_VAR:
                    found = False
                    for y_try in [2.0, 5.0, 8.0, 11.0]:
                        for x_try in [2.0, 5.0, 8.0, 11.0]:
                            self.pico.goto(x_try, y_try)
                            gray0, _ = _grab_gray()
                            if gray0 is not None and float(np.var(gray0)) > MIN_VAR:
                                start_x, start_y = x_try, y_try
                                found = True
                                break
                        if found:
                            break
                    if gray0 is None:
                        return None, None

                var0 = float(np.var(gray0))
                print(f"[calib] Phase correlation at ({self.pico.pos_x:.2f},{self.pico.pos_y:.2f})  var={var0:.1f}")

                fh, fw = gray0.shape
                win = np.outer(np.hanning(fh), np.hanning(fw)).astype(np.float32)
                gray0_w = gray0 * win

                # ── X-axis calibration ─────────────────────────────────────
                self.pico.move("X", calib_d)
                gray_x, _ = _grab_gray(settle=0.6)
                self.pico.goto(start_x, start_y)

                if gray_x is None:
                    return None, None

                shift_x, resp_x = cv2.phaseCorrelate(gray0_w, gray_x * win)
                dx_from_X = float(shift_x[0])
                dy_from_X = float(shift_x[1])
                print(f"[calib] X-move shift: px=({dx_from_X:.1f},{dy_from_X:.1f})  resp={resp_x:.4f}")

                if abs(dx_from_X) < 5.0 or resp_x < 0.005:
                    print(f"[calib] FAIL — X-shift too small ({dx_from_X:.1f}px) or low confidence ({resp_x:.4f})")
                    return None, None

                # ── Y-axis calibration ─────────────────────────────────────
                # Fresh reference frame after returning to start (stage settled)
                time.sleep(0.3)
                gray0_y, _ = _grab_gray(settle=0.4)
                if gray0_y is None:
                    gray0_y = gray0
                gray0_y_w = gray0_y * win

                self.pico.move("Y", calib_d)
                gray_y, _ = _grab_gray(settle=0.6)
                self.pico.goto(start_x, start_y)

                if gray_y is None:
                    return None, None

                shift_y, resp_y = cv2.phaseCorrelate(gray0_y_w, gray_y * win)
                dx_from_Y = float(shift_y[0])
                dy_from_Y = float(shift_y[1])
                print(f"[calib] Y-move shift: px=({dx_from_Y:.1f},{dy_from_Y:.1f})  resp={resp_y:.4f}")

                if abs(dy_from_Y) < 5.0 or resp_y < 0.005:
                    print(f"[calib] FAIL — Y-shift too small ({dy_from_Y:.1f}px) or low confidence ({resp_y:.4f})")
                    return None, None

                # ── Build pixel-to-stage matrix A ──────────────────────────
                # Camera-on-stage: a +d stage move causes image features to shift
                # by (dx_from_axis, dy_from_axis) pixels.  The stage-to-pixel
                # matrix is A_inv = -[[dx_from_X, dx_from_Y], [dy_from_X, dy_from_Y]] / d.
                # Inverting gives A: [stage_dx, stage_dy] = A @ [pixel_dx, pixel_dy].
                A_inv = np.array([
                    [-dx_from_X / calib_d, -dx_from_Y / calib_d],
                    [-dy_from_X / calib_d, -dy_from_Y / calib_d],
                ])
                try:
                    A = np.linalg.inv(A_inv)
                except np.linalg.LinAlgError:
                    print("[calib] FAIL — calibration matrix is singular")
                    return None, None

                ppm_scalar = abs(dx_from_X) / calib_d
                if not (50 < ppm_scalar < 2000):
                    print(f"[calib] FAIL — ppm={ppm_scalar:.1f} out of expected range [50,2000]")
                    return None, None

                import math
                rot_deg = math.degrees(math.atan2(-dy_from_X, -dx_from_X))
                print(f"[calib] ppm={ppm_scalar:.1f}  camera rotation={rot_deg:.2f}°")
                print(f"[calib] A=\n{A}")

                return A, ppm_scalar

            print("[scan] Calibrating pixels/mm (phase correlation) …")
            calib_matrix, fixed_ppm = _calibrate_ppm()
            mw._calib_matrix = calib_matrix  # store for fine-centering in _on_device_goto
            if fixed_ppm:
                fw_px = mw.live_feed._frame_w or 640
                fh_px = mw.live_feed._frame_h or 480
                mw._fov_w_mm = fw_px / fixed_ppm
                mw._fov_h_mm = fh_px / fixed_ppm
                mw.live_feed._display_ppm = fixed_ppm   # keep scale bar accurate
                print(f"[scan] ppm={fixed_ppm:.1f}  FOV={mw._fov_w_mm:.2f}×{mw._fov_h_mm:.2f} mm")
            else:
                print("[scan] Phase calibration failed — bounding-box ppm estimate will be used on first frame")

            fov_w = mw._fov_w_mm
            fov_h = mw._fov_h_mm
            scanner = WaferScanner(self.pico, mw.registry)
            mw.scanner = scanner

            # ── Pad accumulator — running average per unique pad ────────
            class _PadAccum:
                def __init__(self, thr=0.15):
                    self._pads, self._n = [], []
                    self._sx, self._sy = [], []
                    self._thr = thr
                def add(self, pad):
                    for i, ref in enumerate(self._pads):
                        if (abs(ref.stage_x - pad.stage_x) < self._thr and
                                abs(ref.stage_y - pad.stage_y) < self._thr):
                            self._n[i] += 1
                            self._sx[i] += pad.stage_x
                            self._sy[i] += pad.stage_y
                            ref.stage_x = self._sx[i] / self._n[i]
                            ref.stage_y = self._sy[i] / self._n[i]
                            return
                    p = copy.copy(pad)
                    self._pads.append(p);  self._n.append(1)
                    self._sx.append(pad.stage_x); self._sy.append(pad.stage_y)
                def pads(self):
                    return list(self._pads)
                def __len__(self):
                    return len(self._pads)

            accum = _PadAccum(thr=0.15)

            def on_frame(sx, sy, enc_abs=None):
                nonlocal fixed_ppm
                bgr = mw.live_feed._bgr_frame
                if bgr is None:
                    return []
                fh, fw = bgr.shape[:2]
                pads = dd.detect_bond_pads(model, bgr)
                # Discard pads whose bounding box clips the frame edge — partial
                # detections give wrong centroids and corrupt stage coordinate estimates.
                pads = [p for p in pads
                        if p.cx - p.w/2 >= 2 and p.cx + p.w/2 <= fw - 2
                        and p.cy - p.h/2 >= 2 and p.cy + p.h/2 <= fh - 2]
                ppm = fixed_ppm
                # Fallback: latch bounding-box ppm on first frame if phase calibration failed
                if ppm is None and pads:
                    ppm_bb = dd.pixels_per_mm(pads)
                    if ppm_bb and 50 < ppm_bb < 2000:
                        fixed_ppm = ppm_bb
                        ppm = fixed_ppm
                        mw._fov_w_mm = fw / ppm
                        mw._fov_h_mm = fh / ppm
                        print(f"[scan] Bounding-box ppm fallback locked: {ppm:.1f}  FOV={mw._fov_w_mm:.2f}×{mw._fov_h_mm:.2f}mm")

                # ── Absolute encoder position correction ──────────────────
                # enc_abs = (abs_x_mm, abs_y_mm) from firmware ENC_ABS? command.
                # Firmware derives this as: whole_revs × 0.5mm + encoder_sub_rev_mm.
                # This gives the TRUE physical frame centre, correcting the small
                # step-count drift that accumulates across X moves along each row.
                # Sanity check: if enc_abs differs from step count by > 0.24 mm,
                # the encoder or comms returned bad data — fall back to step count.
                sx_phys, sy_phys = sx, sy
                if enc_abs is not None:
                    try:
                        abs_x, abs_y = enc_abs
                        if abs(abs_x - sx) < 0.24 and abs(abs_y - sy) < 0.24:
                            sx_phys, sy_phys = abs_x, abs_y
                            if abs(abs_x - sx) > 0.002 or abs(abs_y - sy) > 0.002:
                                print(f"[scan] enc_abs  X={abs_x:.4f} (step {sx:.4f})  "
                                      f"Y={abs_y:.4f} (step {sy:.4f})  "
                                      f"Δ=({(abs_x-sx)*1000:+.1f}, {(abs_y-sy)*1000:+.1f}) µm")
                    except Exception:
                        pass

                # ── Per-frame scale correction from bond-pad pitch ──────────
                # Phase-correlation calibration (1 mm move, ~114 px) has ~1-2%
                # scale error.  Adjacent bond pads have a fixed 600 µm pitch —
                # measuring their pixel spacing per frame gives the true ppm
                # independently of the calibration move.  Scale errors in A[0,0]
                # and A[1,1] cause VARIABLE cx/cy errors (proportional to each pad's
                # pixel offset from frame centre) because the same pad appears at
                # very different pixel positions across scan frames.
                # Correcting A[0,0]/A[1,1] per frame eliminates this variable bias.
                _PAD_PITCH_MM = 0.600   # known bond-pad centre-to-centre pitch
                _ASPECT_T     = 1.1     # portrait/landscape aspect-ratio threshold
                frame_calib   = calib_matrix  # default: use calibration as-is

                if calib_matrix is not None and len(pads) >= 4:
                    north_px = sorted(
                        [p for p in pads if p.h > p.w * _ASPECT_T], key=lambda p: p.cx)
                    right_px = sorted(
                        [p for p in pads if p.w > p.h * _ASPECT_T], key=lambda p: p.cy)

                    exp_px_x = _PAD_PITCH_MM / abs(calib_matrix[0, 0])
                    exp_px_y = _PAD_PITCH_MM / abs(calib_matrix[1, 1])

                    # Adjacent-pad gaps within 40–160 % of expected spacing
                    x_gaps = [north_px[i+1].cx - north_px[i].cx
                               for i in range(len(north_px) - 1)
                               if 0.4 * exp_px_x
                               < north_px[i+1].cx - north_px[i].cx
                               < 1.6 * exp_px_x]
                    y_gaps = [right_px[i+1].cy - right_px[i].cy
                               for i in range(len(right_px) - 1)
                               if 0.4 * exp_px_y
                               < right_px[i+1].cy - right_px[i].cy
                               < 1.6 * exp_px_y]

                    if len(x_gaps) >= 2 or len(y_gaps) >= 2:
                        frame_calib = calib_matrix.copy()
                        if len(x_gaps) >= 2:
                            ppm_x = float(np.median(x_gaps)) / _PAD_PITCH_MM
                            if 50 < ppm_x < 500:
                                old_A00 = calib_matrix[0, 0]
                                frame_calib[0, 0] = 1.0 / ppm_x
                                corr = (frame_calib[0, 0] - old_A00) / old_A00 * 100
                                if abs(corr) > 0.3:
                                    print(f"[scan] X scale: "
                                          f"{1/old_A00:.1f}→{ppm_x:.1f} px/mm "
                                          f"({corr:+.1f}%)")
                        if len(y_gaps) >= 2:
                            ppm_y = float(np.median(y_gaps)) / _PAD_PITCH_MM
                            if 50 < ppm_y < 500:
                                old_A11 = calib_matrix[1, 1]
                                frame_calib[1, 1] = 1.0 / ppm_y
                                corr = (frame_calib[1, 1] - old_A11) / old_A11 * 100
                                if abs(corr) > 0.3:
                                    print(f"[scan] Y scale: "
                                          f"{1/old_A11:.1f}→{ppm_y:.1f} px/mm "
                                          f"({corr:+.1f}%)")

                if pads and (frame_calib is not None or (ppm and ppm > 0)):
                    if frame_calib is not None:
                        pads = dd.assign_stage_coords(pads, sx_phys, sy_phys, fw, fh,
                                                      calib_matrix=frame_calib)
                    else:
                        pads = dd.assign_stage_coords(pads, sx_phys, sy_phys, fw, fh, ppm)
                    for p in pads:
                        accum.add(p)
                boxes = [(int(p.cx-p.w/2), int(p.cy-p.h/2),
                          int(p.cx+p.w/2), int(p.cy+p.h/2)) for p in pads]
                mw._sig_update_boxes.emit(boxes)
                if SAVE_DEBUG_IMAGES and debug_dir:
                    fname = f"x{sx:.2f}_y{sy:.2f}.jpg"
                    cv2.imwrite(os.path.join(debug_dir, "raw", fname), bgr)
                    ann = bgr.copy()
                    for (x1,y1,x2,y2) in boxes:
                        cv2.rectangle(ann, (x1,y1), (x2,y2), (0,255,136), 2)
                    cv2.putText(ann, f"X={sx:.2f} Y={sy:.2f} n={len(pads)} ppm={int(ppm or 0)}",
                                (10,30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,136), 2)
                    cv2.imwrite(os.path.join(debug_dir, "annotated", fname), ann)
                return []

            def on_progress(cur, total, sx, sy):
                mw.live_feed.scan_x = sx
                mw.live_feed.scan_y = sy
                mw._sig_refresh_map.emit()
                print(f"[scan] frame {cur}/{total}  X={sx:.2f} Y={sy:.2f}  pads_accum={len(accum)}")

            def on_done():
                all_pads = accum.pads()
                if all_pads:
                    fw_ref = mw.live_feed._frame_w or 640
                    fh_ref = mw.live_feed._frame_h or 480
                    north_c, right_c = dd._split_by_orientation(all_pads)
                    print(f"[scan] Unique pads: {len(all_pads)}  "
                          f"north={len(north_c)}  right={len(right_c)}")
                    devices = dd.find_devices(all_pads, wafer_type, fw_ref, fh_ref)
                    mw.registry.add_devices(devices)
                mw._sig_refresh_map.emit()
                mw._sig_refresh_pos.emit()
                self.pico.set_speed(original_speed_idx)
                n = len(mw.registry.get_all())
                suffix = f"  Debug → {debug_dir}" if SAVE_DEBUG_IMAGES and debug_dir else ""
                print(f"[scan] Done ({wafer_type}). {n} devices.  "
                      f"ppm={int(fixed_ppm or 0)}{suffix}")

            scanner.start(travel_x, travel_y, fov_w, fov_h,
                          wafer_type, on_frame, on_progress, on_done)

        threading.Thread(target=_run, daemon=True).start()

    def _stop_detection(self):
        if hasattr(self.main_window, 'scanner'):
            self.main_window.scanner.stop()

    def _add_device_here(self):
        """Add a device at the current stage position (crosshair centre)."""
        if not self.pico.connected or not self.pico.homed:
            return
        mw = self.main_window
        from device_detector import Device
        d = Device(center_x_mm=self.pico.pos_x, center_y_mm=self.pico.pos_y)
        mw.registry.add_devices([d])
        mw._sig_refresh_map.emit()


# ── Probe Panel ─────────────────────────────────────────
class ProbePanel(QWidget):
    """
    Control panel for the left and right microprobes.
    Each probe has a traverse axis (T_L / T_R) and a Z axis (Z_L / Z_R).
    Commands are sent via pico.probe_* which the master Pico relays to the
    slave Pico over UART.

    Probe L traverse: Fwd = away from home (toward top of camera view)
    Probe R traverse: Fwd = away from home (toward left of camera view)
    Both Z axes:      Down = away from home (toward wafer); Up / Retract = toward home (safe)
    """

    _sig_refresh = None   # set to a Signal in __init__ if needed

    def __init__(self, pico, main_window):
        super().__init__()
        self.pico = pico
        self.mw   = main_window
        self._probe      = 'L'            # 'L' or 'R'
        self._wafer_type = 'crossbar'     # 'crosspoint' or 'crossbar'
        self._step_mm    = 0.01           # default 10 µm
        # Saved traverse positions per probe (mm from home); up to 3 for crossbar
        self._saved_trav = {'L': [None, None, None], 'R': [None, None, None]}
        self._saved_z    = None           # shared Z contact depth (mm from home)
        self._pad_btns   = []
        self._step_btns  = []
        self._build_ui()
        self._load_positions()

    # ── Position persistence ───────────────────────────

    _POS_FILE = Path(__file__).parent / "probe_positions.json"

    def _load_positions(self):
        if not self._POS_FILE.exists():
            return
        try:
            data = json.loads(self._POS_FILE.read_text())
            for side in ('L', 'R'):
                vals = data.get("saved_trav", {}).get(side, [None, None, None])
                self._saved_trav[side] = [(float(v) if v is not None else None) for v in vals]
            z = data.get("saved_z")
            self._saved_z = float(z) if z is not None else None
            if self._saved_z is not None:
                self._z_lbl.setText(f"Z contact depth: {self._saved_z:.4f} mm  ✓")
            wtype = data.get("wafer_type", "crossbar")
            self._wafer_type = wtype
            self._bcp.setProperty("active", wtype == 'crosspoint')
            self._bcb.setProperty("active", wtype == 'crossbar')
            for b in [self._bcp, self._bcb]:
                b.style().unpolish(b); b.style().polish(b)
            self._rebuild_pad_buttons()
        except Exception as e:
            print(f"[probe] Could not load positions: {e}")

    def _save_positions(self):
        try:
            data = {
                "saved_trav": self._saved_trav,
                "saved_z":    self._saved_z,
                "wafer_type": self._wafer_type,
            }
            self._POS_FILE.write_text(json.dumps(data, indent=2))
        except Exception as e:
            print(f"[probe] Could not save positions: {e}")

    # ── UI construction ────────────────────────────────

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(5); lay.setContentsMargins(12, 8, 12, 8)

        # ── Probe selector ─────────────────────────────
        lay.addWidget(stitle("Probe"))
        pr = QHBoxLayout(); pr.setSpacing(3)
        self._btn_pl = QPushButton("Probe L"); self._btn_pl.setObjectName("deviceBtn")
        self._btn_pr = QPushButton("Probe R"); self._btn_pr.setObjectName("deviceBtn")
        self._btn_pl.setProperty("active", True)
        self._btn_pl.clicked.connect(lambda: self._select_probe('L'))
        self._btn_pr.clicked.connect(lambda: self._select_probe('R'))
        pr.addWidget(self._btn_pl); pr.addWidget(self._btn_pr)
        lay.addLayout(pr)
        lay.addWidget(sep())

        # ── Jog ───────────────────────────────────────
        lay.addWidget(stitle("Jog"))
        jog_row = QHBoxLayout(); jog_row.setSpacing(8)

        # Traverse column
        tc  = QWidget(); tl = QVBoxLayout(tc)
        tl.setSpacing(3); tl.setContentsMargins(0, 0, 0, 0)
        tlbl = QLabel("Traverse"); tlbl.setAlignment(Qt.AlignCenter)
        tlbl.setStyleSheet(f"color:{C['text2']};font-size:10px;")
        tl.addWidget(tlbl)
        btn_fwd = QPushButton("Fwd ↑"); btn_fwd.setObjectName("jogBtn"); btn_fwd.setMinimumHeight(40)
        btn_bck = QPushButton("Back ↓"); btn_bck.setObjectName("jogBtn"); btn_bck.setMinimumHeight(40)
        btn_fwd.clicked.connect(lambda: self._jog_trav(+1))
        btn_bck.clicked.connect(lambda: self._jog_trav(-1))
        tl.addWidget(btn_fwd); tl.addWidget(btn_bck)

        # Z column
        zc  = QWidget(); zl = QVBoxLayout(zc)
        zl.setSpacing(3); zl.setContentsMargins(0, 0, 0, 0)
        zlbl = QLabel("Z-axis"); zlbl.setAlignment(Qt.AlignCenter)
        zlbl.setStyleSheet(f"color:{C['text2']};font-size:10px;")
        zl.addWidget(zlbl)
        btn_up = QPushButton("Up ↑");   btn_up.setObjectName("jogBtn"); btn_up.setMinimumHeight(40)
        btn_dn = QPushButton("Down ↓"); btn_dn.setObjectName("jogBtn"); btn_dn.setMinimumHeight(40)
        btn_up.clicked.connect(lambda: self._jog_z(-1))   # Up = toward home = negative mm
        btn_dn.clicked.connect(lambda: self._jog_z(+1))   # Down = away from home = positive mm
        zl.addWidget(btn_up); zl.addWidget(btn_dn)

        jog_row.addWidget(tc, stretch=1); jog_row.addWidget(zc, stretch=1)
        lay.addLayout(jog_row)

        # ── Step size ──────────────────────────────────
        lay.addWidget(stitle("Step Size [µm]"))
        sr = QHBoxLayout(); sr.setSpacing(3)
        for lbl, val in [("1", 0.001), ("10", 0.01), ("100", 0.1), ("1000", 1.0)]:
            b = QPushButton(lbl); b.setObjectName("stepBtn")
            b.setProperty("active", lbl == "10")
            b.clicked.connect(lambda _, b=b, v=val: self._set_step(b, v))
            self._step_btns.append(b); sr.addWidget(b)
        lay.addLayout(sr)
        lay.addWidget(sep())

        # ── Home ──────────────────────────────────────
        lay.addWidget(stitle("Home"))
        hr = QHBoxLayout(); hr.setSpacing(3)
        for lbl, tgt_fn in [
            ("All",      lambda p: "ALL"),
            ("Traverse", lambda p: f"T_{p}"),
            ("Z",        lambda p: f"Z_{p}"),
        ]:
            b = QPushButton(lbl); b.setObjectName("accentBtn")
            b.clicked.connect(lambda _, fn=tgt_fn: self._home(fn(self._probe)))
            hr.addWidget(b)
        lay.addLayout(hr)
        lay.addWidget(sep())

        # ── Device type ────────────────────────────────
        lay.addWidget(stitle("Device Type"))
        wr = QHBoxLayout(); wr.setSpacing(3)
        self._bcp = QPushButton("Crosspoint"); self._bcp.setObjectName("waferTypeBtn")
        self._bcb = QPushButton("Crossbar");   self._bcb.setObjectName("waferTypeBtn")
        self._bcp.setProperty("active", False)
        self._bcb.setProperty("active", True)
        self._bcp.clicked.connect(lambda: self._set_type('crosspoint'))
        self._bcb.clicked.connect(lambda: self._set_type('crossbar'))
        wr.addWidget(self._bcp); wr.addWidget(self._bcb)
        lay.addLayout(wr)
        lay.addWidget(sep())

        # ── Save pad positions ─────────────────────────
        # Title updates dynamically when probe or type changes
        self._pad_title = stitle("Pad Positions — Probe L (Right Pads)")
        lay.addWidget(self._pad_title)

        self._pad_container = QWidget()
        self._pad_lay = QVBoxLayout(self._pad_container)
        self._pad_lay.setSpacing(3); self._pad_lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._pad_container)

        # Z contact save
        self._btn_save_z = QPushButton("Save Z Contact Depth")
        self._btn_save_z.setObjectName("accentBtn")
        self._btn_save_z.clicked.connect(self._save_z)
        lay.addWidget(self._btn_save_z)
        self._z_lbl = QLabel("Z contact depth: not set")
        self._z_lbl.setStyleSheet(f"color:{C['text3']};font-size:9px;padding:1px 0;")
        lay.addWidget(self._z_lbl)
        lay.addWidget(sep())

        # ── Sequence controls ─────────────────────────
        lay.addWidget(stitle("Sequence"))
        self._btn_seq = QPushButton("▶  Run Traverse Sequence")
        self._btn_seq.setObjectName("accentBtn")
        self._btn_seq.setStyleSheet("font-size:12px;font-weight:600;")
        self._btn_seq.clicked.connect(self._run_sequence)
        lay.addWidget(self._btn_seq)
        btn_contact = QPushButton("▼  Z Contact")
        btn_contact.setObjectName("accentBtn")
        btn_contact.clicked.connect(self._contact)
        lay.addWidget(btn_contact)

        lay.addSpacing(4)
        lay.addWidget(EStopButton())
        lay.addStretch()

        # Build pad save buttons for initial state
        self._rebuild_pad_buttons()

    # ── Dynamic pad button rebuild ─────────────────────

    def _rebuild_pad_buttons(self):
        """Recreate pad-save buttons to match current probe and device type."""
        while self._pad_lay.count():
            item = self._pad_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._pad_btns.clear()

        # Update section title to show which probe and which pad orientation it saves
        pad_label = "Right Pads" if self._probe == 'L' else "North Pads"
        self._pad_title.setText(
            f"Pad Positions — Probe {self._probe} ({pad_label})")

        n_pads = 1 if self._wafer_type == 'crosspoint' else 3
        for i in range(n_pads):
            b = QPushButton(); b.setObjectName("accentBtn")
            self._refresh_pad_btn_label(b, i)
            b.clicked.connect(lambda _, idx=i: self._save_pad(idx))
            self._pad_btns.append(b)
            self._pad_lay.addWidget(b)

    def _refresh_pad_btn_label(self, btn, idx):
        saved = self._saved_trav[self._probe][idx]
        if saved is not None:
            btn.setText(f"Pad {idx+1}  ✓  {saved:.3f} mm  — re-save")
        else:
            btn.setText(f"Save Pad {idx+1} position")

    # ── Internal helpers ────────────────────────────────

    def _run(self, fn):
        threading.Thread(target=fn, daemon=True).start()

    def _trav_axis(self):
        return f"T_{self._probe}"

    def _z_axis(self):
        return f"Z_{self._probe}"

    # ── Slot implementations ────────────────────────────

    def _select_probe(self, p):
        self._probe = p
        self._btn_pl.setProperty("active", p == 'L')
        self._btn_pr.setProperty("active", p == 'R')
        for b in [self._btn_pl, self._btn_pr]:
            b.style().unpolish(b); b.style().polish(b)
        self._rebuild_pad_buttons()

    def _set_type(self, t):
        self._wafer_type = t
        self._bcp.setProperty("active", t == 'crosspoint')
        self._bcb.setProperty("active", t == 'crossbar')
        for b in [self._bcp, self._bcb]:
            b.style().unpolish(b); b.style().polish(b)
        self._rebuild_pad_buttons()
        self._save_positions()

    def _set_step(self, btn, mm):
        self._step_mm = mm
        tog(btn, self._step_btns)

    def _jog_trav(self, direction):
        if not self.pico.connected:
            return
        mm = self._step_mm * direction
        ax = self._trav_axis()
        self._run(lambda: self.pico.probe_move(ax, mm))

    def _jog_z(self, direction):
        if not self.pico.connected:
            return
        mm = self._step_mm * direction
        ax = self._z_axis()
        self._run(lambda: self.pico.probe_move(ax, mm))

    def _home(self, target):
        if not self.pico.connected:
            return
        self._run(lambda: self.pico.probe_home(target))

    def _save_pad(self, idx):
        """Save current traverse position as pad idx for the selected probe."""
        if not self.pico.connected:
            return
        pos = self.pico.probe_pos()
        if pos is None:
            return
        trav_val = pos[0] if self._probe == 'L' else pos[2]   # T_L=idx0, T_R=idx2
        self._saved_trav[self._probe][idx] = trav_val
        if idx < len(self._pad_btns):
            self._refresh_pad_btn_label(self._pad_btns[idx], idx)
        self._save_positions()
        print(f"[probe] Pad {idx+1} saved: Probe {self._probe} traverse = {trav_val:.4f} mm")

    def _save_z(self):
        """Save current Z position as contact depth (shared by all pads)."""
        if not self.pico.connected:
            return
        pos = self.pico.probe_pos()
        if pos is None:
            return
        z_val = pos[1] if self._probe == 'L' else pos[3]   # Z_L=idx1, Z_R=idx3
        self._saved_z = z_val
        self._z_lbl.setText(f"Z contact depth: {z_val:.4f} mm  ✓")
        self._save_positions()
        print(f"[probe] Z contact saved: {z_val:.4f} mm")

    def _run_sequence(self):
        """
        Step the selected probe through all saved pad positions.
        Pauses 0.75 s at each position.  Z axis is not moved.
        """
        if not self.pico.connected:
            return
        n_pads = 2 if self._wafer_type == 'crosspoint' else 3
        positions = [self._saved_trav[self._probe][i] for i in range(n_pads)]
        if any(p is None for p in positions):
            print(f"[probe] Sequence aborted — not all {n_pads} pad positions saved")
            return
        ax = self._trav_axis()

        def _seq():
            pos = self.pico.probe_pos()
            if pos is None:
                return
            current = pos[0] if self._probe == 'L' else pos[2]
            for target in positions:
                delta = target - current
                if abs(delta) > 0.0001:
                    self.pico.probe_move(ax, delta)
                time.sleep(0.75)
                # Update current from fresh query
                p = self.pico.probe_pos()
                if p:
                    current = p[0] if self._probe == 'L' else p[2]
            print(f"[probe] Traverse sequence complete (Probe {self._probe})")

        self._run(_seq)

    def _contact(self):
        """Move Z axis from current position down to the saved contact depth."""
        if not self.pico.connected:
            return
        if self._saved_z is None:
            print("[probe] Contact aborted — Z contact depth not saved yet")
            return
        ax = self._z_axis()

        def _go():
            pos = self.pico.probe_pos()
            if pos is None:
                return
            current_z = pos[1] if self._probe == 'L' else pos[3]
            delta = self._saved_z - current_z
            if abs(delta) > 0.0001:
                self.pico.probe_move(ax, delta)

        self._run(_go)

    def _retract(self):
        """Home the Z axis (fully retract probe — moves to safe top position)."""
        if not self.pico.connected:
            return
        ax = self._z_axis()
        self._run(lambda: self.pico.probe_home(ax))


# ── Config Panel ─────────────────────────────────────────
class ConfigPanel(QWidget):
    _sig_enc_result = Signal(str)

    def __init__(self, pico=None):
        super().__init__()
        self.pico = pico
        self.travel_x_lbl=None; self.travel_y_lbl=None
        layout=QVBoxLayout(self); layout.setSpacing(6); layout.setContentsMargins(12,8,12,8)

        # Connection — all on same column alignment, no separator between items
        layout.addWidget(stitle("Connection"))

        # Stage COM — label + dropdown on same row, no button
        r=QHBoxLayout(); r.setSpacing(8)
        l=QLabel("Stage COM"); l.setFixedWidth(130); r.addWidget(l)
        self.stage_com=QComboBox()
        self.stage_com.addItems(["Auto-detect"]+[f"COM{i}" for i in range(1,13)])
        self.stage_com.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
        r.addWidget(self.stage_com)
        layout.addLayout(r)

        # Camera source — Device (index 0) or USB (index 1)
        r2=QHBoxLayout(); r2.setSpacing(8)
        l2=QLabel("Camera source"); l2.setFixedWidth(130); r2.addWidget(l2)
        self._btn_cam_device=QPushButton("Device (0)"); self._btn_cam_device.setObjectName("waferTypeBtn"); self._btn_cam_device.setProperty("active",False)
        self._btn_cam_usb=QPushButton("USB (1)"); self._btn_cam_usb.setObjectName("waferTypeBtn"); self._btn_cam_usb.setProperty("active",True)
        self._btn_cam_device.clicked.connect(lambda: self._set_cam(0))
        self._btn_cam_usb.clicked.connect(lambda: self._set_cam(1))
        r2.addWidget(self._btn_cam_device); r2.addWidget(self._btn_cam_usb)
        layout.addLayout(r2)
        self._cam_idx = 1
        self._cam_changed_cb = None
        layout.addWidget(sep())

        # Stage
        layout.addWidget(stitle("Stage"))

        # Steps/mm static
        r3=QHBoxLayout(); r3.setSpacing(8)
        l3=QLabel("Steps/mm"); l3.setFixedWidth(130); r3.addWidget(l3)
        sv=QLabel("6400"); sv.setObjectName("staticVal")
        sv.setFixedWidth(120)
        r3.addWidget(sv); r3.addStretch()
        layout.addLayout(r3)
        note=QLabel("ℹ  200-step motor × 16x microstepping")
        note.setStyleSheet(f"color:{C['text3']};font-size:9px;padding:0 0 2px 0;")
        layout.addWidget(note)

        # Max speed — static, not user editable
        r_ms=QHBoxLayout(); r_ms.setSpacing(8)
        l_ms=QLabel("Max speed (steps/s)"); l_ms.setFixedWidth(130); r_ms.addWidget(l_ms)
        sv_ms=QLabel("10000"); sv_ms.setObjectName("staticVal"); sv_ms.setFixedWidth(120)
        r_ms.addWidget(sv_ms); r_ms.addStretch()
        layout.addLayout(r_ms)

        # Acceleration — static, not user editable
        r_ac=QHBoxLayout(); r_ac.setSpacing(8)
        l_ac=QLabel("Acceleration"); l_ac.setFixedWidth(130); r_ac.addWidget(l_ac)
        sv_ac=QLabel("30000"); sv_ac.setObjectName("staticVal"); sv_ac.setFixedWidth(120)
        r_ac.addWidget(sv_ac); r_ac.addStretch()
        layout.addLayout(r_ac)
        note_spd=QLabel("ℹ  Tuned for TMC2208/2209 + 17HS4401")
        note_spd.setStyleSheet(f"color:{C['text3']};font-size:9px;padding:0 0 2px 0;")
        layout.addWidget(note_spd)

        # Travel — read only after homing
        for axis,attr in [("X","travel_x_lbl"),("Y","travel_y_lbl")]:
            r=QHBoxLayout(); r.setSpacing(8)
            l=QLabel(f"Travel {axis} (mm)"); l.setFixedWidth(130); r.addWidget(l)
            lbl=QLabel("—"); lbl.setObjectName("readonlyVal")
            lbl.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
            r.addWidget(lbl)
            setattr(self,attr,lbl)
            layout.addLayout(r)

        note2=QLabel("ℹ  Measured automatically on homing")
        note2.setStyleSheet(f"color:{C['text3']};font-size:9px;padding:0 0 2px 0;")
        layout.addWidget(note2)
        layout.addWidget(sep())

        # Wafer
        layout.addWidget(stitle("Wafer"))
        # Scan area spinboxes — used by Start Detection
        rx=QHBoxLayout(); rx.setSpacing(8)
        lx=QLabel("Scan area X (mm)"); lx.setFixedWidth(130); rx.addWidget(lx)
        self._travel_x_spin=QDoubleSpinBox(); self._travel_x_spin.setRange(0.5,25.0)
        self._travel_x_spin.setDecimals(1); self._travel_x_spin.setValue(22.0)
        self._travel_x_spin.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self._travel_x_spin.setFixedWidth(120); rx.addWidget(self._travel_x_spin); rx.addStretch()
        layout.addLayout(rx)
        ry=QHBoxLayout(); ry.setSpacing(8)
        ly=QLabel("Scan area Y (mm)"); ly.setFixedWidth(130); ry.addWidget(ly)
        self._travel_y_spin=QDoubleSpinBox(); self._travel_y_spin.setRange(0.5,25.0)
        self._travel_y_spin.setDecimals(1); self._travel_y_spin.setValue(22.0)
        self._travel_y_spin.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self._travel_y_spin.setFixedWidth(120); ry.addWidget(self._travel_y_spin); ry.addStretch()
        layout.addLayout(ry)
        layout.addWidget(sep())

        # Detection
        layout.addWidget(stitle("Detection"))

        cr3=QHBoxLayout(); cr3.setSpacing(8); cr3.setContentsMargins(0,0,0,0)
        l2=QLabel("Confidence"); l2.setFixedWidth(130); cr3.addWidget(l2)
        self._conf_spin=QSpinBox(); self._conf_spin.setRange(1,100); self._conf_spin.setValue(70); self._conf_spin.setSuffix(" %")
        self._conf_spin.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self._conf_spin.setFixedWidth(120)
        cr3.addWidget(self._conf_spin); cr3.addStretch()
        layout.addLayout(cr3)
        layout.addWidget(sep())

        # Encoder Debug
        layout.addWidget(stitle("Encoder Debug"))
        b_enc = QPushButton("Query ENC?")
        b_enc.clicked.connect(self._query_enc)
        layout.addWidget(b_enc)

        self._enc_lbl = QLabel("—")
        self._enc_lbl.setObjectName("readonlyVal")
        self._enc_lbl.setWordWrap(True)
        self._enc_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._enc_lbl.setStyleSheet(
            f"color:{C['navy_glow']};font-size:10px;font-family:{F_MONO};"
            f"padding:5px 6px;background-color:{C['bg3']};"
            f"border:1px solid {C['border']};border-radius:5px;")
        layout.addWidget(self._enc_lbl)
        self._sig_enc_result.connect(self._enc_lbl.setText)

        layout.addStretch()

    def _query_enc(self):
        if not self.pico or not self.pico.connected:
            self._sig_enc_result.emit("Not connected")
            return
        def _worker():
            try:
                with self.pico.lock:
                    self.pico.serial.reset_input_buffer()
                    self.pico.serial.write(b"ENC?\n")
                    self.pico.serial.flush()
                    resp = self.pico.serial.readline().decode(errors="ignore").strip()
                # Parse into readable lines
                if resp.startswith("ENC:"):
                    parts = resp[4:].split(",")
                    lines = "\n".join(p.replace("=", " = ") for p in parts)
                    self._sig_enc_result.emit(lines)
                else:
                    self._sig_enc_result.emit(resp or "No response")
            except Exception as e:
                self._sig_enc_result.emit(f"Error: {e}")
        threading.Thread(target=_worker, daemon=True).start()

    def _set_cam(self, idx):
        self._cam_idx = idx
        self._btn_cam_device.setProperty("active", idx == 0)
        self._btn_cam_usb.setProperty("active", idx == 1)
        for b in [self._btn_cam_device, self._btn_cam_usb]:
            b.style().unpolish(b); b.style().polish(b)
        if self._cam_changed_cb:
            self._cam_changed_cb(idx)

    def set_travel(self,x_mm,y_mm):
        if self.travel_x_lbl: self.travel_x_lbl.setText(f"{x_mm:.2f}")
        if self.travel_y_lbl: self.travel_y_lbl.setText(f"{y_mm:.2f}")

    def _spin_row(self,layout,lbl,val,mn,mx,d):
        r=QHBoxLayout(); r.setSpacing(8)
        l=QLabel(lbl); l.setFixedWidth(130); r.addWidget(l)
        if d>0:
            s=QDoubleSpinBox(); s.setDecimals(d); s.setRange(mn,mx); s.setValue(val)
        else:
            s=QSpinBox(); s.setRange(int(mn),int(mx)); s.setValue(int(val))
        s.setButtonSymbols(QAbstractSpinBox.NoButtons)
        s.setFixedWidth(120)
        r.addWidget(s); r.addStretch()
        layout.addLayout(r)


# ── Main Window ─────────────────────────────────────────
class MainWindow(QMainWindow):
    _sig_refresh_pos  = Signal()
    _sig_refresh_map  = Signal()
    _sig_update_boxes = Signal(list)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Wafer Stage Controller")
        self.setMinimumSize(1000,620); self.resize(1380,840)

        # Create Pico controller
        self.pico = PicoController()

        central=QWidget(); self.setCentralWidget(central)
        ml=QVBoxLayout(central); ml.setSpacing(0); ml.setContentsMargins(0,0,0,0)

        content=QWidget()
        cl=QHBoxLayout(content); cl.setSpacing(0); cl.setContentsMargins(0,0,0,0)

        self.live_feed=LiveFeedWidget()
        cl.addWidget(self.live_feed,stretch=1)

        rp=QFrame(); rp.setObjectName("rightPanel"); rp.setFixedWidth(290)
        rl=QVBoxLayout(rp); rl.setSpacing(0); rl.setContentsMargins(0,0,0,0)

        tb=QWidget(); tb.setStyleSheet(f"background-color:{C['bg2']};border-bottom:1px solid {C['border']};")
        tl=QHBoxLayout(tb); tl.setSpacing(0); tl.setContentsMargins(0,0,0,0)
        self.tc=QPushButton("Stage");  self.tc.setObjectName("tabBtn"); self.tc.setProperty("active",True)
        self.tp=QPushButton("Probe");  self.tp.setObjectName("tabBtn"); self.tp.setProperty("active",False)
        self.tf=QPushButton("Config"); self.tf.setObjectName("tabBtn"); self.tf.setProperty("active",False)
        self.tc.clicked.connect(lambda:self._tab(0))
        self.tp.clicked.connect(lambda:self._tab(1))
        self.tf.clicked.connect(lambda:self._tab(2))
        tl.addWidget(self.tc); tl.addWidget(self.tp); tl.addWidget(self.tf); tl.addStretch()
        rl.addWidget(tb)

        self.ps=QStackedWidget()

        # Stage tab — no scroll
        self.cp=ControlPanel(self.pico, self)
        self.ps.addWidget(self.cp)

        # Probe tab — scrollable
        pbs=QScrollArea(); pbs.setWidgetResizable(True)
        pbs.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        pbs.setStyleSheet("QScrollArea{border:none;}")
        self.pp=ProbePanel(self.pico, self); pbs.setWidget(self.pp)
        self.ps.addWidget(pbs)

        # Config tab — scrollable
        fs=QScrollArea(); fs.setWidgetResizable(True)
        fs.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        fs.setStyleSheet("QScrollArea{border:none;}")
        self.fp=ConfigPanel(pico=self.pico); fs.setWidget(self.fp)
        self.ps.addWidget(fs)

        rl.addWidget(self.ps)
        cl.addWidget(rp)
        ml.addWidget(content,stretch=1)

        sb=QFrame(); sb.setObjectName("statusBar")
        sl=QHBoxLayout(sb); sl.setSpacing(12); sl.setContentsMargins(12,0,12,0)
        self.com_lbl=QLabel("⬡  —"); self.com_lbl.setStyleSheet(f"color:{C['text2']};font-size:10px;")
        sl.addWidget(self.com_lbl)
        self.badge_conn=badge("Disconnected",C["text3"])
        sl.addWidget(self.badge_conn)
        self.badge_state=badge("Idle",C["blue"])
        sl.addWidget(self.badge_state)
        sl.addStretch()
        au=QLabel("Automated Wafer Alignment Platform  ·  Ghui Chen Yang © 2026")
        au.setStyleSheet(f"color:{C['text3']};font-size:10px;")
        sl.addWidget(au)
        ml.addWidget(sb)

        self._sig_refresh_pos.connect(self.refresh_position)
        self._sig_refresh_map.connect(self._refresh_minimap)
        self._sig_update_boxes.connect(self._update_yolo_boxes)

        # Auto-connect after UI ready
        QTimer.singleShot(200, self._start)

    def _start(self):
        """Connect on launch and update badge."""
        self.registry = DeviceRegistry()
        self.registry.load()
        self.scanner      = None
        self._fov_w_mm    = 1.2   # conservative default — real FOV ~1.3mm, ensures overlap if calibration fails
        self._fov_h_mm    = 1.2
        self._cam         = None
        self._model       = None   # YOLO model — set after first scan
        self._calib_matrix = None  # pixel→stage calibration matrix — set after first scan
        self.pico.connect()
        self.update_status()
        self.live_feed._goto_cb   = self._on_device_goto
        self.live_feed._delete_cb = self._on_device_delete
        self._refresh_minimap()
        self.fp._cam_changed_cb = self._start_camera
        self._start_camera(self.fp._cam_idx)

    def _start_camera(self, index):
        """Open the selected camera and start the frame-grab timer."""
        import cv2
        self._stop_camera()
        self._cam = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        if not hasattr(self, '_cam_timer'):
            self._cam_timer = QTimer(self)
            self._cam_timer.timeout.connect(self._grab_frame)
        self._cam_timer.start(33)   # ~30 fps

    def _stop_camera(self):
        if hasattr(self, '_cam_timer'):
            self._cam_timer.stop()
        if self._cam is not None:
            self._cam.release()
            self._cam = None

    def _grab_frame(self):
        if self._cam is not None and self._cam.isOpened():
            ret, frame = self._cam.read()
            if ret:
                self.live_feed.set_frame(frame)

    def update_status(self):
        """Update badge — called on connect and after every button press."""
        if self.pico.connected:
            self.com_lbl.setText(f"⬡  {self.pico.port}")
            self.badge_conn.setText("Connected")
            self.badge_conn.setStyleSheet(
                f"background-color:{C['green']}20;color:{C['green']};"
                f"border:1px solid {C['green']}40;border-radius:3px;"
                f"padding:1px 8px;font-size:10px;font-weight:600;")
        else:
            self.com_lbl.setText("⬡  —")
            self.badge_conn.setText("Disconnected")
            self.badge_conn.setStyleSheet(
                f"background-color:{C['text3']}20;color:{C['text3']};"
                f"border:1px solid {C['text3']}40;border-radius:3px;"
                f"padding:1px 8px;font-size:10px;font-weight:600;")

    def refresh_position(self):
        """Update position display and connection status."""
        self.live_feed.pos_x = self.pico.pos_x
        self.live_feed.pos_y = self.pico.pos_y
        self.live_feed.homed  = self.pico.homed
        self.live_feed.update()
        self.update_status()

    def _tab(self,i):
        self.ps.setCurrentIndex(i)
        self.tc.setProperty("active",i==0)
        self.tp.setProperty("active",i==1)
        self.tf.setProperty("active",i==2)
        for b in [self.tc,self.tp,self.tf]: b.style().unpolish(b); b.style().polish(b)

    def _refresh_minimap(self):
        """Sync device dots on minimap from registry. Must be called from UI thread."""
        self.live_feed.devices = self.registry.get_all()
        self.live_feed.update()

    def _update_yolo_boxes(self, boxes):
        """Update YOLO detection overlay on live feed. Must be called from UI thread."""
        self.live_feed.yolo_boxes = boxes
        self.live_feed.update()

    def _fine_center_device(self):
        """
        Fine-center the stage on the device under the crosshair.

        Per-frame, pads are clustered into per-device groups by the gap between
        adjacent pad centroids (intra-device gap ~600 µm, inter-device ~3 mm).
        The cluster whose centroid is CLOSEST to the frame centre is selected —
        this always picks the intended device even if neighbouring devices are
        partially visible, fixing the "first pass lands on wrong device" issue.

        N_FRAMES independent frames are averaged to reduce YOLO bounding-box
        noise by √N before computing the correction.

        For each cluster the device-column X and device-row Y are estimated as
        the MEAN of all pads in the cluster (more stable than the middle-index
        pad; equivalent for evenly-spaced pads, better when one pad is missing).

        Uses plain goto() for the correction — no pre-approach sweep.
        Safety guard: skips if the implied correction exceeds 1.5 mm (coarse
        goto landed far off, e.g. bad scan coordinate for an edge device).
        """
        import numpy as np
        import device_detector as _dd

        model = getattr(self, '_model', None)
        cm    = getattr(self, '_calib_matrix', None)
        if model is None or cm is None:
            return

        bgr0 = self.live_feed._bgr_frame
        if bgr0 is None:
            return
        fh, fw = bgr0.shape[:2]
        cx_frame = fw / 2.0
        cy_frame = fh / 2.0

        _ASPECT_T  = 1.1
        pitch_x_px = 0.600 / abs(float(cm[0, 0]))   # 600 µm pad pitch in pixels
        pitch_y_px = 0.600 / abs(float(cm[1, 1]))
        # Cluster split gap: must be > intra-device pad spacing (~1× pitch)
        # and < inter-device separation (~5× pitch).  2.5× pitch is safe.
        SPLIT_X = pitch_x_px * 2.5
        SPLIT_Y = pitch_y_px * 2.5

        # ── Cluster helpers ───────────────────────────────────────────────────
        def _closest_cluster_x(pads_sorted):
            """
            Split north pads (sorted by cx) into per-device clusters, return
            the cluster whose mean cx is closest to the frame centre.
            """
            if not pads_sorted:
                return []
            clusters, cur = [], [pads_sorted[0]]
            for p in pads_sorted[1:]:
                if p.cx - cur[-1].cx > SPLIT_X:
                    clusters.append(cur); cur = [p]
                else:
                    cur.append(p)
            clusters.append(cur)
            return min(clusters,
                       key=lambda cl: abs(np.mean([p.cx for p in cl]) - cx_frame))

        def _closest_cluster_y(pads_sorted):
            """
            Split right pads (sorted by cy) into per-device clusters, return
            the cluster whose mean cy is closest to the frame centre.
            """
            if not pads_sorted:
                return []
            clusters, cur = [], [pads_sorted[0]]
            for p in pads_sorted[1:]:
                if p.cy - cur[-1].cy > SPLIT_Y:
                    clusters.append(cur); cur = [p]
                else:
                    cur.append(p)
            clusters.append(cur)
            return min(clusters,
                       key=lambda cl: abs(np.mean([p.cy for p in cl]) - cy_frame))

        def _center_x(cl):
            """
            Device column X from a north-pad cluster.
            3+ pads → mean cx (uses all detections, robust to outliers).
            2 pads, gap ≈ 2× pitch → middle pad missing, midpoint = mean. ✓
            2 pads, gap ≈ 1× pitch → side pad missing, use pad closer to centre.
            1 pad  → use it directly.
            """
            n = len(cl)
            if n >= 3:
                return float(np.mean([p.cx for p in cl]))
            if n == 2:
                gap = cl[1].cx - cl[0].cx
                if gap > 1.5 * pitch_x_px:
                    return (cl[0].cx + cl[1].cx) / 2.0   # middle absent → midpoint
                return min(cl, key=lambda p: abs(p.cx - cx_frame)).cx  # side absent
            return cl[0].cx

        def _center_y(cl):
            """Device row Y from a right-pad cluster — same logic as _center_x."""
            n = len(cl)
            if n >= 3:
                return float(np.mean([p.cy for p in cl]))
            if n == 2:
                gap = cl[1].cy - cl[0].cy
                if gap > 1.5 * pitch_y_px:
                    return (cl[0].cy + cl[1].cy) / 2.0
                return min(cl, key=lambda p: abs(p.cy - cy_frame)).cy
            return cl[0].cy

        # ── Multi-frame YOLO averaging ────────────────────────────────────────
        # N_FRAMES independent frames are captured and YOLO is run on each.
        # Averaging reduces per-frame bounding-box noise by √N_FRAMES.
        N_FRAMES  = 5
        FRAME_GAP = 0.07   # 70 ms ≈ 2 camera frames at 30 fps

        north_cx_samples = []
        right_cy_samples = []

        for fi in range(N_FRAMES):
            if fi > 0:
                time.sleep(FRAME_GAP)
            bgr_i = self.live_feed._bgr_frame
            if bgr_i is None:
                continue
            fh_i, fw_i = bgr_i.shape[:2]

            pads_i = _dd.detect_bond_pads(model, bgr_i)
            # Drop pads whose bounding box clips the frame edge
            pads_i = [p for p in pads_i
                      if p.cx - p.w / 2 >= 2 and p.cx + p.w / 2 <= fw_i - 2
                      and p.cy - p.h / 2 >= 2 and p.cy + p.h / 2 <= fh_i - 2]

            all_north = sorted([p for p in pads_i if p.h > p.w * _ASPECT_T],
                               key=lambda p: p.cx)
            all_right = sorted([p for p in pads_i if p.w > p.h * _ASPECT_T],
                               key=lambda p: p.cy)

            # Pick the per-device cluster closest to frame centre
            nc = _closest_cluster_x(all_north)
            rc = _closest_cluster_y(all_right)

            if nc:
                north_cx_samples.append(_center_x(nc))
            if rc:
                right_cy_samples.append(_center_y(rc))

        if not north_cx_samples or not right_cy_samples:
            print(f"[fine-center] SKIP — no pads found in any of {N_FRAMES} frames "
                  f"(north hits={len(north_cx_samples)} right hits={len(right_cy_samples)})")
            return

        # Mean across frames — reduces YOLO bounding-box noise
        mid_north_px = float(np.mean(north_cx_samples))
        mid_right_py = float(np.mean(right_cy_samples))

        dx_px = mid_north_px - cx_frame
        dy_px = mid_right_py  - cy_frame

        v     = cm @ np.array([dx_px, dy_px])
        dx_mm = float(v[0])
        dy_mm = float(v[1])

        print(f"[fine-center] {len(north_cx_samples)}/{N_FRAMES} frames  "
              f"residual ({dx_px:+.1f}, {dy_px:+.1f}) px  "
              f"→ ({dx_mm*1000:+.0f}, {dy_mm*1000:+.0f}) µm")

        # Safety guard — if correction is implausibly large the coarse goto
        # landed far from the target device; skip rather than chase the wrong one.
        # Guard set to 2.5 mm (= ~283 px at 113 px/mm) — just within the half-FOV
        # (~320 px).  1.5 mm was too tight: a scan coordinate error of only 1.5 mm
        # caused the guard to fire even though the pads were clearly visible in frame.
        if abs(dx_mm) > 2.5 or abs(dy_mm) > 2.5:
            print(f"[fine-center] SKIP — correction ({dx_mm*1000:+.0f}, {dy_mm*1000:+.0f}) µm "
                  f"exceeds 2.5 mm guard (wrong device or very bad scan coordinate)")
            return

        MIN_CORR_MM = 0.005   # skip if already within 5 µm
        if abs(dx_mm) < MIN_CORR_MM and abs(dy_mm) < MIN_CORR_MM:
            print("[fine-center] SKIP — already within 5 µm, no correction needed")
            return

        # Direct relative move — no pre-approach sweep.
        self.pico.goto(self.pico.pos_x + dx_mm, self.pico.pos_y + dy_mm)

    def _on_device_goto(self, cx_mm, cy_mm):
        """
        Move stage to a device dot selected from the minimap context menu.

        Two-phase:
          1. goto — plain MOVE XY to scan-detected (cx_mm, cy_mm).
             cx_mm is already enc-abs corrected during the scan, so a direct move
             lands within ~0.3 mm of the true device position.
             goto_verified's 0.5 mm pre-approach (move left, then right) caused a
             visible double-motion and is not needed — YOLO fine-centering handles
             the precise final positioning.
          2. _fine_center_device × 2 — YOLO snapshot of live frame, finds middle
             north/right pads in a central ROI, issues a small relative correction.
             Two passes eliminate any residual left by the first correction.
             Immune to calibration-scale errors: measures actual pixel offset in
             real time.

        Encoder role: the MT6835 encoder is still used during scanning (enc_abs
        corrects each frame's physical origin so cx_mm is physically accurate).
        The MOVETO-style encoder correction at goto time is superseded by YOLO.
        """
        if not self.pico.connected:
            return
        def _go():
            if not self.pico.homed:
                self.pico.home("ALL")
            prev = self.pico.speed_idx
            self.pico.set_speed(1)   # 70% — reduces vibration on approach
            # Single direct move — no pre-approach swing.
            self.pico.goto(cx_mm, cy_mm)
            # Settle before first fine-centering capture.
            # 1.1 s covers the initial coarse move (10–20 mm) and camera refresh.
            time.sleep(1.1)
            self._fine_center_device()
            # Second pass settle: fine corrections are < 0.3 mm so vibration dies
            # much faster than the initial move — 0.5 s is sufficient.
            time.sleep(0.5)
            self._fine_center_device()
            self.pico.set_speed(prev)
            self._sig_refresh_pos.emit()
        threading.Thread(target=_go, daemon=True).start()

    def _on_device_delete(self, cx_mm, cy_mm):
        """Remove a device from the registry and refresh the minimap."""
        with self.registry._lock:
            self.registry.devices = [
                d for d in self.registry.devices
                if not (abs(d["cx_mm"] - cx_mm) < 0.15 and abs(d["cy_mm"] - cy_mm) < 0.15)
            ]
            self.registry._save()
        self._refresh_minimap()


def main():
    app=QApplication(sys.argv); app.setStyleSheet(ss())
    w=MainWindow(); w.show(); sys.exit(app.exec())

if __name__=="__main__":
    main()