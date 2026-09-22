"""
Wafer Stage Controller UI v6
"""
import sys
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QPushButton, QLabel, QFrame, QStackedWidget,
    QComboBox, QDoubleSpinBox, QSpinBox, QLineEdit,
    QSizePolicy, QScrollArea, QFileDialog, QAbstractSpinBox
)
from PySide6.QtCore import Qt, QPointF, QRectF, QSize
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
        self.bond_pads=[]; self.scan_x=None; self.scan_y=None
        self.travel_x=25.0; self.travel_y=25.0

    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        w,h=self.width(),self.height(); cx,cy=w//2,h//2

        p.fillRect(self.rect(),QColor(C["bg0"]))
        p.setPen(QPen(QColor(C["border"]),0.3))
        for x in range(0,w,50): p.drawLine(x,0,x,h)
        for y in range(0,h,50): p.drawLine(0,y,w,y)

        # Crosshair with gap — unchanged, looks great
        gap,arm=8,22
        p.setPen(QPen(QColor(C["navy_glow"]),1.5))
        p.drawLine(cx-arm,cy,cx-gap,cy); p.drawLine(cx+gap,cy,cx+arm,cy)
        p.drawLine(cx,cy-arm,cx,cy-gap); p.drawLine(cx,cy+gap,cx,cy+arm)

        # Not connected — bottom left
        p.setPen(QPen(QColor(C["text3"]),1)); p.setFont(QFont(F_MAIN,10))
        p.drawText(14,h-12,"Camera feed — not connected")

        # Position overlay — bottom right
        p.setPen(QPen(QColor(C["navy_glow"]),1))
        fpos=QFont(F_MONO,11); fpos.setWeight(QFont.DemiBold); p.setFont(fpos)
        pt=f"X {self.pos_x:7.4f}   Y {self.pos_y:7.4f} mm"
        fm=QFontMetrics(fpos); tw=fm.horizontalAdvance(pt)
        p.drawText(w-tw-16, h-30, pt)

        # Scale bar — anchored right wall, BELOW coords, 10px gap
        bw=80; bx=w-bw-16; by=h-10
        p.setPen(QPen(QColor(C["text2"]),1.5))
        p.drawLine(bx,by,bx+bw,by)
        p.drawLine(bx,by-4,bx,by+4); p.drawLine(bx+bw,by-4,bx+bw,by+4)
        p.setFont(QFont(F_MAIN,9))
        p.drawText(bx,by-13,bw,12,Qt.AlignCenter,"100 mm")

        # Mini map — bottom left
        self._minimap(p,w,h)
        p.end()

    def _minimap(self,p,w,h):
        mw,mh=110,110; mx,my=12,h-mh-36; pad=6
        p.setPen(QPen(QColor(C["border_light"]),1)); p.setBrush(QColor(C["bg1"]))
        p.drawRoundedRect(mx,my,mw,mh,5,5)
        p.setPen(QPen(QColor(C["text2"]),1)); p.setFont(QFont(F_MAIN,8))
        p.drawText(mx+pad,my+13,"Wafer map")
        sq=mw-pad*4; sx=mx+(mw-sq)//2; sy=my+18
        p.setPen(QPen(QColor(C["navy"]),1)); p.setBrush(QColor(C["navy_subtle"]))
        p.drawRect(sx,sy,sq,sq)
        p.setPen(Qt.NoPen); p.setBrush(QColor(C["navy_glow"]))
        for bx_mm,by_mm in self.bond_pads:
            px=sx+int(bx_mm/self.travel_x*sq); py=sy+int(by_mm/self.travel_y*sq)
            p.drawRect(px-2,py-2,4,4)
        if self.scan_x is not None:
            scx=sx+int(self.scan_x/self.travel_x*sq); scy=sy+int(self.scan_y/self.travel_y*sq)
            p.setPen(QPen(QColor(C["navy_glow"]),1)); p.setBrush(QColor(C["navy_glow"]+"80"))
            p.drawEllipse(scx-3,scy-3,6,6)
        else:
            wcx=sx+sq//2; wcy=sy+sq//2
            p.setPen(Qt.NoPen); p.setBrush(QColor(C["navy_glow"]))
            p.drawEllipse(wcx-3,wcy-3,6,6)


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
    def __init__(self):
        super().__init__()
        self.dev_btns=[]
        layout=QVBoxLayout(self)
        layout.setSpacing(5); layout.setContentsMargins(12,8,12,8)

        # Device
        layout.addWidget(stitle("Device"))
        dr=QHBoxLayout(); dr.setSpacing(3)
        self.btn_stage=QPushButton("Stage (XY)"); self.btn_stage.setObjectName("deviceBtn"); self.btn_stage.setProperty("active",True)
        self.btn_pl=QPushButton("Probe L"); self.btn_pl.setObjectName("deviceBtn"); self.btn_pl.setProperty("active",False)
        self.btn_pr=QPushButton("Probe R"); self.btn_pr.setObjectName("deviceBtn"); self.btn_pr.setProperty("active",False)
        self.dev_btns=[self.btn_stage,self.btn_pl,self.btn_pr]
        self.btn_stage.clicked.connect(lambda:self._dev("stage"))
        self.btn_pl.clicked.connect(lambda:self._dev("probe_l"))
        self.btn_pr.clicked.connect(lambda:self._dev("probe_r"))
        dr.addWidget(self.btn_stage); dr.addWidget(self.btn_pl); dr.addWidget(self.btn_pr)
        layout.addLayout(dr); layout.addWidget(sep())

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

        jo_lay.addWidget(xy_widget, stretch=1)

        # Z pills - tall rounded rects stacked on right (probe only)
        self.zc=QWidget()
        self.zc.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.zc.setFixedWidth(40)
        zl=QVBoxLayout(self.zc)
        zl.setSpacing(3); zl.setContentsMargins(0,0,0,0)

        z_ss=(
            f"QPushButton{{"
            f"background-color:{C['bg3']};color:{C['text1']};"
            f"border:1px solid {C['border']};border-radius:10px;"
            f"font-size:13px;font-weight:600;}}"
            f"QPushButton:hover{{"
            f"background-color:{C['navy']};border-color:{C['navy_light']};}}"
            f"QPushButton:pressed{{background-color:{C['navy_subtle']};}}"
        )

        bzp=QPushButton("Z+"); bzp.setStyleSheet(z_ss)
        bzp.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        bzp.setMinimumHeight(16)
        bzm=QPushButton("Z−"); bzm.setStyleSheet(z_ss)
        bzm.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        bzm.setMinimumHeight(16)

        zlbl=QLabel("Z"); zlbl.setAlignment(Qt.AlignCenter)
        zlbl.setStyleSheet(f"color:{C['text3']};font-size:9px;")
        zlbl.setFixedHeight(10)

        zl.addWidget(bzp, stretch=1)
        zl.addWidget(zlbl)
        zl.addWidget(bzm, stretch=1)

        self.zc.hide()
        jo_lay.addWidget(self.zc)

        jog_outer.setFixedHeight(155)
        layout.addWidget(jog_outer)

        # Step size
        layout.addWidget(stitle("Step size [μm]"))
        sr=QHBoxLayout(); sr.setSpacing(3)
        self.step_btns=[]
        for i,s in enumerate(["1000","100","10","1","0.1"]):
            b=QPushButton(s); b.setObjectName("stepBtn"); b.setProperty("active",i==1)
            b.clicked.connect(lambda _,b=b:tog(b,self.step_btns))
            self.step_btns.append(b); sr.addWidget(b)
        layout.addLayout(sr)

        # Speed
        layout.addWidget(stitle("Speed"))
        self.speed_slider=SnapSlider()
        layout.addWidget(self.speed_slider)
        layout.addWidget(sep())

        # Actions
        layout.addWidget(stitle("Actions"))
        ar=QHBoxLayout(); ar.setSpacing(3)
        for t in ["Home X","Home Y","Home All"]:
            b=QPushButton(t); b.setObjectName("accentBtn"); ar.addWidget(b)
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
        gr.addWidget(xl); gr.addWidget(self.gx); gr.addWidget(yl); gr.addWidget(self.gy); gr.addWidget(bg)
        layout.addLayout(gr)
        layout.addWidget(sep())

        # Wafer type
        layout.addWidget(stitle("Wafer type"))
        wr=QHBoxLayout(); wr.setSpacing(3)
        self.bcp=QPushButton("Crosspoint"); self.bcp.setObjectName("waferTypeBtn"); self.bcp.setProperty("active",True)
        self.bcp.clicked.connect(lambda:self._wtype("cp"))
        self.bcb=QPushButton("Crossbar"); self.bcb.setObjectName("waferTypeBtn"); self.bcb.setProperty("active",False)
        self.bcb.clicked.connect(lambda:self._wtype("cb"))
        wr.addWidget(self.bcp); wr.addWidget(self.bcb)
        layout.addLayout(wr)
        layout.addWidget(sep())

        # Scan & Detection
        layout.addWidget(stitle("Scan & Detection"))
        b_det=QPushButton("Start Detection"); b_det.setObjectName("accentBtn"); b_det.setStyleSheet(f"font-size:13px;font-weight:600;")
        layout.addWidget(b_det)
        b_probe=QPushButton("Start Probing Sequence"); b_probe.setObjectName("accentBtn"); b_probe.setStyleSheet(f"font-size:13px;font-weight:600;")
        layout.addWidget(b_probe)
        ps_row=QHBoxLayout(); ps_row.setSpacing(3)
        b_pause=QPushButton("\u258f\u258f Pause"); b_pause.setStyleSheet(f"font-size:13px;font-weight:600;")
        b_stop=QPushButton("\u25a0  Stop"); b_stop.setObjectName("dangerBtn"); b_stop.setStyleSheet(f"font-size:13px;font-weight:600;")
        ps_row.addWidget(b_pause); ps_row.addWidget(b_stop)
        layout.addLayout(ps_row)

        layout.addSpacing(4)
        layout.addWidget(EStopButton())

    def _dev(self,dev):
        self.btn_stage.setProperty("active",dev=="stage")
        self.btn_pl.setProperty("active",dev=="probe_l")
        self.btn_pr.setProperty("active",dev=="probe_r")
        for b in self.dev_btns: b.style().unpolish(b); b.style().polish(b)
        self.zc.setVisible(dev!="stage")


    def _wtype(self,t):
        self.bcp.setProperty("active",t=="cp"); self.bcb.setProperty("active",t!="cp")
        for b in [self.bcp,self.bcb]: b.style().unpolish(b); b.style().polish(b)


# ── Config Panel ────────────────────────────────────────
class ConfigPanel(QWidget):
    def __init__(self):
        super().__init__()
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

        # Camera index — same column alignment
        r2=QHBoxLayout(); r2.setSpacing(8)
        l2=QLabel("Camera index"); l2.setFixedWidth(130); r2.addWidget(l2)
        ci=QSpinBox(); ci.setRange(0,10); ci.setValue(1)
        ci.setButtonSymbols(QAbstractSpinBox.NoButtons)
        ci.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
        r2.addWidget(ci)
        layout.addLayout(r2)
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
        self._spin_row(layout,"Width (mm)",25.0,1,300,1)
        self._spin_row(layout,"Height (mm)",25.0,1,300,1)
        self._spin_row(layout,"Scan step (mm)",0.5,0.01,5,2)
        self._spin_row(layout,"Overlap (%)",10,0,50,0)
        layout.addWidget(sep())

        # Detection
        layout.addWidget(stitle("Detection"))

        # YOLO model — label + input + browse, all aligned
        mr=QHBoxLayout(); mr.setSpacing(8); mr.setContentsMargins(0,0,0,0)
        l=QLabel("YOLO model"); l.setFixedWidth(130); mr.addWidget(l)
        self.mp=QLabel("model.pt"); self.mp.setObjectName("staticVal")
        self.mp.setFixedWidth(120)
        mr.addWidget(self.mp); mr.addStretch()
        layout.addLayout(mr)

        cr3=QHBoxLayout(); cr3.setSpacing(8); cr3.setContentsMargins(0,0,0,0)
        l2=QLabel("Confidence"); l2.setFixedWidth(130); cr3.addWidget(l2)
        conf=QSpinBox(); conf.setRange(1,100); conf.setValue(75); conf.setSuffix(" %")
        conf.setButtonSymbols(QAbstractSpinBox.NoButtons)
        conf.setFixedWidth(120)
        cr3.addWidget(conf); cr3.addStretch()
        layout.addLayout(cr3)
        layout.addStretch()

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
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Wafer Stage Controller")
        self.setMinimumSize(1000,620); self.resize(1380,840)

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
        self.tc=QPushButton("Control"); self.tc.setObjectName("tabBtn"); self.tc.setProperty("active",True)
        self.tc.clicked.connect(lambda:self._tab(0))
        self.tf=QPushButton("Config"); self.tf.setObjectName("tabBtn"); self.tf.setProperty("active",False)
        self.tf.clicked.connect(lambda:self._tab(1))
        tl.addWidget(self.tc); tl.addWidget(self.tf); tl.addStretch()
        rl.addWidget(tb)

        self.ps=QStackedWidget()

        # Control — no scroll
        self.cp=ControlPanel()
        self.ps.addWidget(self.cp)

        # Config — scrollable
        fs=QScrollArea(); fs.setWidgetResizable(True)
        fs.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        fs.setStyleSheet("QScrollArea{border:none;}")
        self.fp=ConfigPanel(); fs.setWidget(self.fp)
        self.ps.addWidget(fs)

        rl.addWidget(self.ps)
        cl.addWidget(rp)
        ml.addWidget(content,stretch=1)

        sb=QFrame(); sb.setObjectName("statusBar")
        sl=QHBoxLayout(sb); sl.setSpacing(12); sl.setContentsMargins(12,0,12,0)
        self.com_lbl=QLabel("⬡  —"); self.com_lbl.setStyleSheet(f"color:{C['text2']};font-size:10px;")
        sl.addWidget(self.com_lbl)
        self.badge_conn=badge("Disconnected",C["text3"]); sl.addWidget(self.badge_conn)
        self.badge_state=badge("Idle",C["blue"]); sl.addWidget(self.badge_state)
        sl.addStretch()
        au=QLabel("Automated Wafer Alignment Platform  ·  Ghui Chen Yang © 2026")
        au.setStyleSheet(f"color:{C['text3']};font-size:10px;")
        sl.addWidget(au)
        ml.addWidget(sb)

    def _tab(self,i):
        self.ps.setCurrentIndex(i)
        self.tc.setProperty("active",i==0); self.tf.setProperty("active",i==1)
        for b in [self.tc,self.tf]: b.style().unpolish(b); b.style().polish(b)


def main():
    app=QApplication(sys.argv); app.setStyleSheet(ss())
    w=MainWindow(); w.show(); sys.exit(app.exec())

if __name__=="__main__":
    main()