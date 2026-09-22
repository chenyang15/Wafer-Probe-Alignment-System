"""
pico_controller.py
Handles all serial communication with the Pico.
Simple rule: every public method acquires self.lock, sends a command,
reads lines until it gets the expected response or times out.
This is the same pattern that makes jog work reliably.
"""
import serial
import serial.tools.list_ports
import threading
import time


class PicoController:
    BAUD    = 115200
    TIMEOUT = 2.0   # serial readline timeout — short so we loop fast

    SPEED_PRESETS = {
        0: 7826,
        1: 9130,    # 70% — scan speed
        2: 10435,
        3: 13043,
        4: 14348,
    }

    def __init__(self):
        self.serial    = None
        self.connected = False
        self.port      = None
        self.lock      = threading.Lock()
        self.pos_x        = 0.0
        self.pos_y        = 0.0
        self.homed        = False   # True once a successful home has completed
        self.speed_idx    = 3       # default to 100% (index 3 = 13043 steps/sec)
        self.home_session = 0       # increments on every home — invalidates stored enc refs

    # ── Connection ─────────────────────────────────────

    def find_pico_port(self):
        for p in serial.tools.list_ports.comports():
            desc = (p.description or "").lower()
            mfr  = (p.manufacturer or "").lower()
            if any(k in desc or k in mfr for k in ["pico","micropython","raspberry","rp2"]):
                return p.device
            if (p.vid or 0) == 0x2E8A:
                return p.device
        for p in serial.tools.list_ports.comports():
            if "usb serial device" in (p.description or "").lower():
                return p.device
        return None

    def connect(self, port=None):
        try:
            target = port or self.find_pico_port()
            if not target:
                return False, "No Pico found"
            self.serial    = serial.Serial(target, self.BAUD, timeout=self.TIMEOUT)
            time.sleep(1.0)
            self.serial.reset_input_buffer()
            self.connected = True
            self.port      = target
            # Check if stage is already at home (both MAX switches active)
            resp = self._send("SWITCHES?", timeout=5.0)
            if resp and "M1MIN=1" in resp and "M2MIN=1" in resp:
                self.homed = True
                self.pos_x = 0.0
                self.pos_y = 0.0
            return True, target
        except Exception as e:
            self.connected = False
            return False, str(e)

    def disconnect(self):
        if self.serial and self.serial.is_open:
            self.serial.close()
        self.connected = False

    # ── Core send/receive ──────────────────────────────

    def _send(self, cmd, timeout=None):
        """Send a command, read lines until we get a recognised response.
        Returns the response line, or None on timeout/error.
        timeout defaults to self.TIMEOUT * 15 (30s) — enough for any move.
        """
        if not self.connected or not self.serial:
            return None
        if timeout is None:
            timeout = self.TIMEOUT * 15
        try:
            with self.lock:
                self.serial.reset_input_buffer()
                self.serial.write((cmd + "\n").encode())
                self.serial.flush()
                deadline = time.time() + timeout
                while time.time() < deadline:
                    line = self.serial.readline().decode(errors="ignore").strip()
                    if not line:
                        continue
                    if line.startswith(("POS:", "STATUS:", "SPEED_OK",
                                        "HOMED:", "SWITCHES:", "READY", "ERR:", "CORE1_ERR:",
                                        "ENC_AFH:", "POS_ENC:", "ENC_ABS:", "PROBE_POS:")):
                        return line
                return None
        except Exception:
            self.connected = False
            return None

    def _parse_pos(self, line):
        if line and line.startswith("POS:"):
            try:
                x, y = line[4:].split(",")
                self.pos_x = float(x)
                self.pos_y = float(y)
            except Exception:
                pass

    # ── Public API ─────────────────────────────────────

    def move(self, axis, mm):
        """Move axis by mm (relative). Blocks until done."""
        resp = self._send(f"MOVE {axis} {mm:.4f}")
        self._parse_pos(resp)
        return resp is not None

    def home(self, target="ALL"):
        """Home X, Y, or ALL. Blocks until done.
        Uses a long timeout since HOME ALL can take ~15s.
        HOME ALL sends HOMED:X, HOMED:Y, then POS:.
        HOME X / HOME Y send HOMED:X/Y then POS:.
        We wait for POS: as the single reliable terminator.
        """
        if not self.connected or not self.serial:
            return False
        try:
            with self.lock:
                self.serial.reset_input_buffer()
                self.serial.write((f"HOME {target}\n").encode())
                self.serial.flush()
                deadline = time.time() + 90.0   # 90s — plenty for simultaneous XY
                while time.time() < deadline:
                    line = self.serial.readline().decode(errors="ignore").strip()
                    if not line:
                        continue
                    if line.startswith("POS:"):
                        self._parse_pos(line)
                        self.homed        = True
                        self.home_session += 1   # all stored enc refs are now stale
                        return True
                return False
        except Exception:
            self.connected = False
            return False

    def set_speed(self, idx):
        self.speed_idx = idx
        self._send(f"SPEED {idx}", timeout=5.0)

    def goto(self, x_mm, y_mm):
        """Relative move to absolute position using step count only. Used for scanning."""
        dx = x_mm - self.pos_x
        dy = y_mm - self.pos_y
        if abs(dx) < 0.0001 and abs(dy) < 0.0001:
            return
        if abs(dx) > 0.0001 and abs(dy) > 0.0001:
            resp = self._send(f"MOVE XY {dx:.4f} {dy:.4f}")
            self._parse_pos(resp)
        elif abs(dx) > 0.0001:
            self.move("X", dx)
        else:
            self.move("Y", dy)

    def goto_verified(self, x_mm, y_mm):
        """
        Absolute move, always ensuring the final X approach is from the LEFT (rightward).
        Uses plain MOVE commands — no firmware encoder correction — so the lead-screw
        backlash state at the target matches the scan (which also always approached X
        rightward).  cx_mm values are enc_abs-corrected during the scan, so a plain MOVE
        to cx_mm delivers the correct physical position without a post-correction direction
        flip that would re-engage backlash from the wrong side.

        Two-phase:
          1. If pos_x > approach_x, move X left to approach_x (with Y) simultaneously.
          2. Final rightward MOVE to x_mm (with any remaining Y if Phase 1 was skipped).
        """
        X_APPROACH_MM = 0.5

        approach_x = max(0.0, x_mm - X_APPROACH_MM)

        # Phase 1: if we are to the right of the approach position, retreat left (and move Y).
        if self.pos_x > approach_x + 0.001:
            dx = approach_x - self.pos_x
            dy = y_mm - self.pos_y
            if abs(dx) > 0.0001 and abs(dy) > 0.0001:
                self._parse_pos(self._send(f"MOVE XY {dx:.4f} {dy:.4f}"))
            elif abs(dx) > 0.0001:
                self._parse_pos(self._send(f"MOVE X {dx:.4f}"))
            elif abs(dy) > 0.0001:
                self._parse_pos(self._send(f"MOVE Y {dy:.4f}"))

        # Phase 2: final rightward X move to target (and Y if not yet at target).
        dx = x_mm - self.pos_x
        dy = y_mm - self.pos_y
        if abs(dx) > 0.0001 and abs(dy) > 0.0001:
            self._parse_pos(self._send(f"MOVE XY {dx:.4f} {dy:.4f}"))
        elif abs(dx) > 0.0001:
            self._parse_pos(self._send(f"MOVE X {dx:.4f}"))
        elif abs(dy) > 0.0001:
            self._parse_pos(self._send(f"MOVE Y {dy:.4f}"))

    def query_enc_afh(self):
        """
        Query current encoder angle-from-home counts for both axes.
        Returns (afh_x, afh_y) as ints, or None if not calibrated / encoder error.
        Called after the first 'Go To Device' to capture the ground-truth encoder
        reference for that device — used by goto_verified_with_ref on subsequent visits.
        """
        resp = self._send("ENC_AFH?", timeout=5.0)
        if resp and resp.startswith("ENC_AFH:"):
            try:
                parts = resp[8:].split(",")
                afh_x, afh_y = int(parts[0]), int(parts[1])
                if afh_x < 0 or afh_y < 0:
                    return None   # encoder not calibrated
                return afh_x, afh_y
            except Exception:
                pass
        return None

    def query_enc_abs(self):
        """
        Query absolute encoder position in mm for both axes.
        Firmware computes: whole_revs (from step count) × 0.5mm + afh sub-revolution (encoder).
        Returns (abs_x_mm, abs_y_mm) as floats, or None if not calibrated / encoder error.
        Used during scanning so each frame has a physically-anchored origin for pad coordinates.
        """
        resp = self._send("ENC_ABS?", timeout=5.0)
        if resp and resp.startswith("ENC_ABS:"):
            try:
                parts = resp[8:].split(",")
                abs_x, abs_y = float(parts[0]), float(parts[1])
                if abs_x < 0 or abs_y < 0:
                    return None   # encoder not calibrated
                return abs_x, abs_y
            except Exception:
                pass
        return None

    def goto_verified_with_ref(self, x_mm, y_mm, afh_ref_x, afh_ref_y):
        """
        Absolute move + reference-based encoder correction.
        Sends MOVETO_REF which uses the stored angle-from-home reference instead of
        step-count expected angle — always gives the correct correction direction as
        long as MOVETO lands within ±0.25 mm of the reference (which it does).

        Returns updated (afh_x, afh_y) from the post-correction encoder read,
        or None on comms error.  The caller should store the returned values as
        the new reference so each goto self-improves.

        NOTE: does NOT skip when already at target — the correction is the point.
        """
        resp = self._send(
            f"MOVETO_REF {x_mm:.4f} {y_mm:.4f} {afh_ref_x} {afh_ref_y}"
        )
        if resp and resp.startswith("POS_ENC:"):
            try:
                parts = resp[8:].split(",")
                self.pos_x = float(parts[0])
                self.pos_y = float(parts[1])
                return int(parts[2]), int(parts[3])
            except Exception:
                pass
        return None

    def query_pos(self):
        resp = self._send("POS?", timeout=5.0)
        self._parse_pos(resp)

    # ── Probe relay API ────────────────────────────────────────────────
    # Commands are prefixed "PROBE " so the master Pico relays them to the
    # slave Pico via UART.  Responses from the slave arrive as "PROBE_POS:"
    # which is now in the recognised-prefix list for _send.

    def probe_move(self, axis, mm):
        """
        Relative move of one probe axis.
        axis: T_L, Z_L, T_R, Z_R
        Returns (t_l, z_l, t_r, z_r) tuple or None on error.
        """
        resp = self._send(f"PROBE MOVE {axis} {mm:.4f}", timeout=30.0)
        return self._parse_probe_pos(resp)

    def probe_home(self, target="ALL"):
        """
        Home probe axis or all axes.
        target: ALL | T_L | Z_L | T_R | Z_R
        Returns (t_l, z_l, t_r, z_r) tuple or None on error.
        HOME ALL sends PROBE_HOMED:* lines before the final PROBE_POS: — this
        method holds the lock and waits specifically for PROBE_POS: so those
        intermediate lines are drained correctly without confusing _send.
        """
        if not self.connected or not self.serial:
            return None
        timeout = 60.0 if target == "ALL" else 20.0
        try:
            with self.lock:
                self.serial.reset_input_buffer()
                self.serial.write(f"PROBE HOME {target}\n".encode())
                self.serial.flush()
                deadline = time.time() + timeout
                while time.time() < deadline:
                    line = self.serial.readline().decode(errors="ignore").strip()
                    if line.startswith("PROBE_POS:"):
                        return self._parse_probe_pos(line)
                    # PROBE_HOMED:* lines are drained and discarded here
                return None
        except Exception:
            self.connected = False
            return None

    def probe_pos(self):
        """Query current probe positions. Returns (t_l, z_l, t_r, z_r) or None."""
        resp = self._send("PROBE POS?", timeout=5.0)
        return self._parse_probe_pos(resp)

    def _parse_probe_pos(self, resp):
        """Parse PROBE_POS:t_l,z_l,t_r,z_r into a float tuple."""
        if resp and resp.startswith("PROBE_POS:"):
            try:
                parts = resp[10:].split(",")
                return tuple(float(p) for p in parts[:4])
            except Exception:
                pass
        return None