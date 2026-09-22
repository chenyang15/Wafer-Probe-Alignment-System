"""
wafer_scanner.py
Scan sequence generation and session-level device registry.
Generates a boustrophedon (snake) scan path over the wafer,
stepping by FOV size with 10% overlap.
Writes detected devices to JSON for persistence within a session.
"""

import json
import os
import time
import threading
from typing import List, Callable, Optional
from dataclasses import dataclass, asdict

SESSION_FILE = os.path.join(os.path.dirname(__file__), "scan_session.json")
# Fixed absolute step sizes — decoupled from measured FOV so step never changes
# between scans regardless of what ppm calibration produces.
STEP_X_MM   = 2.45  # mm between scan columns.
                    # NOT a multiple of 0.5 mm (lead-screw pitch / encoder revolution) —
                    # this keeps scan positions mid-revolution rather than at the 0°/360°
                    # boundary, where encoder readings are most sensitive to vibration.
                    # FOV ≈ 5.6 mm wide → ~56% overlap; each device column seen in 2–3 frames.
STEP_Y_MM   = 2.45  # mm between scan rows — same reasoning as STEP_X_MM.
SETTLE_TIME     = 1.1   # seconds to wait after move before capture
                        # Raised from 0.9 → 1.1 to let X-axis vibration fully die down
                        # before capturing the frame (X resonance / lead-screw bounce).
SCAN_SPEED_IDX  = 1     # 70% of max (9130 steps/sec) — slower scan reduces X-axis vibration
                        # and prevents lead-screw resonance near full extension



@dataclass
class ScanFrame:
    stage_x: float
    stage_y: float
    row: int
    col: int


def generate_scan_path(travel_x_mm: float, travel_y_mm: float,
                       fov_w_mm: float = 0.0, fov_h_mm: float = 0.0) -> List[ScanFrame]:
    """
    Generate unidirectional scan path: every row scans left-to-right (X always positive).
    Between rows the scanner explicitly returns X to 0, then advances Y.
    This keeps X always approaching each scan position from the same direction,
    so lead-screw backlash is in a consistent state for every frame capture.
    """
    step_x = STEP_X_MM
    step_y = STEP_Y_MM

    cols = max(1, int(travel_x_mm / step_x) + 1)
    rows = max(1, int(travel_y_mm / step_y) + 1)

    frames = []
    for row in range(rows):
        y = row * step_y
        for col in range(cols):          # always left → right
            x = col * step_x
            frames.append(ScanFrame(stage_x=x, stage_y=y, row=row, col=col))

    return frames


class DeviceRegistry:
    """Stores all detected devices for the session."""

    def __init__(self):
        self.devices = []    # list of dicts with cx_mm, cy_mm
        self._lock = threading.Lock()

    def add_devices(self, new_devices):
        """Add devices, deduplicating by proximity (within 0.15mm = same device)."""
        with self._lock:
            for d in new_devices:
                if not self._is_duplicate(d.center_x_mm, d.center_y_mm):
                    self.devices.append({
                        "cx_mm":       round(d.center_x_mm, 4),
                        "cy_mm":       round(d.center_y_mm, 4),
                        "enc_session": None,   # home_session at time of enc reference capture
                        "enc_afh_x":   None,   # angle-from-home count for X at device centre
                        "enc_afh_y":   None,   # angle-from-home count for Y at device centre
                    })
            self._save()

    def _is_duplicate(self, cx, cy, threshold_mm=0.15):
        for d in self.devices:
            if abs(d["cx_mm"] - cx) < threshold_mm and abs(d["cy_mm"] - cy) < threshold_mm:
                return True
        return False

    def get_device_enc(self, cx_mm, cy_mm):
        """
        Return (session, afh_x, afh_y) for the device nearest to (cx_mm, cy_mm),
        or None if no encoder reference has been stored yet.
        Used by the UI to decide whether to use goto_verified_with_ref or goto_verified.
        Backward-compatible with JSON files that predate enc fields (uses .get()).
        """
        with self._lock:
            for d in self.devices:
                if abs(d["cx_mm"] - cx_mm) < 0.15 and abs(d["cy_mm"] - cy_mm) < 0.15:
                    session = d.get("enc_session")
                    if session is not None:
                        return session, d.get("enc_afh_x"), d.get("enc_afh_y")
        return None

    def update_device_enc(self, cx_mm, cy_mm, session, afh_x, afh_y):
        """
        Store the encoder angle-from-home reference for a device after a goto.
        session = pico.home_session at time of capture — lets the UI detect stale
        references after re-homing and fall back to step-count correction automatically.
        """
        with self._lock:
            for d in self.devices:
                if abs(d["cx_mm"] - cx_mm) < 0.15 and abs(d["cy_mm"] - cy_mm) < 0.15:
                    d["enc_session"] = session
                    d["enc_afh_x"]   = afh_x
                    d["enc_afh_y"]   = afh_y
                    self._save()
                    return True
        return False

    def get_all(self):
        with self._lock:
            return list(self.devices)

    def clear(self):
        with self._lock:
            self.devices = []
            self._save()

    def _save(self):
        try:
            with open(SESSION_FILE, "w") as f:
                json.dump(self.devices, f, indent=2)
        except Exception as e:
            print(f"[registry] Save failed: {e}")

    def load(self):
        try:
            if os.path.exists(SESSION_FILE):
                with open(SESSION_FILE) as f:
                    self.devices = json.load(f)
        except Exception:
            self.devices = []


class WaferScanner:
    """
    Orchestrates the full scan sequence.
    Runs in a background thread so the UI stays responsive.
    Calls back to the UI for frame capture and device updates.
    """

    def __init__(self, pico_controller, registry: DeviceRegistry):
        self.pico = pico_controller
        self.registry = registry
        self._thread = None
        self._stop_flag = False
        self.is_running = False

    def start(self, travel_x_mm: float, travel_y_mm: float,
              fov_w_mm: float, fov_h_mm: float,
              wafer_type: str,
              on_frame: Callable,       # fn(stage_x, stage_y) → (frame, pads, devices)
              on_progress: Callable,    # fn(current, total, stage_x, stage_y)
              on_done: Callable):       # fn()
        if self.is_running:
            return
        self._stop_flag = False
        self.is_running = True
        self._thread = threading.Thread(
            target=self._run,
            args=(travel_x_mm, travel_y_mm, fov_w_mm, fov_h_mm,
                  wafer_type, on_frame, on_progress, on_done),
            daemon=True
        )
        self._thread.start()

    def stop(self):
        self._stop_flag = True
        self.is_running = False

    def _run(self, travel_x_mm, travel_y_mm, fov_w_mm, fov_h_mm,
             wafer_type, on_frame, on_progress, on_done):
        prev_speed_idx = getattr(self.pico, 'speed_idx', 3)
        try:
            # Always home before every scan — this is mandatory, not optional.
            # After device gotos, wrong-direction encoder corrections can leave the
            # physical stage misaligned from the step count. Starting a scan from
            # that corrupted state causes MOVETO errors > ±0.25 mm at scan frames,
            # which triggers wrong-direction corrections during the scan, corrupting
            # pad coordinates and breaking device detection.
            # Re-homing resets step count AND enc_home_angle to match physical (0,0),
            # guaranteeing a clean state regardless of what happened before.
            self.pico.home("ALL")

            # Lock scan to 70% speed to reduce X-axis vibration and lead-screw resonance.
            # The user can still change the speed slider for jogging — we restore after scan.
            self.pico.set_speed(SCAN_SPEED_IDX)

            frames = generate_scan_path(travel_x_mm, travel_y_mm, fov_w_mm, fov_h_mm)
            total = len(frames)
            y_vals = sorted(set(f.stage_y for f in frames))
            x_vals = sorted(set(f.stage_x for f in frames))
            print(f"[scan] Path: {total} frames  {len(x_vals)} cols × {len(y_vals)} rows")
            print(f"[scan] X positions: {[f'{x:.2f}' for x in x_vals]}")
            print(f"[scan] Y positions: {[f'{y:.2f}' for y in y_vals]}")

            prev_row = -1
            for i, frame in enumerate(frames):
                if self._stop_flag:
                    break

                # Between rows: home X (return to limit switch), then advance Y.
                # Homing X gives every row the same physical X=0 starting reference —
                # identical to how Y is referenced from its own limit switch at the
                # start of the scan.  Same reference = same per-row X accuracy.
                # All accumulated X step-count error is cleared between rows.
                if frame.row != prev_row and prev_row >= 0:
                    self.pico.home("X")
                    dy = frame.stage_y - self.pico.pos_y
                    if abs(dy) > 0.0001:
                        self.pico.move("Y", dy)
                prev_row = frame.row

                # Move to frame position — plain MOVE, no encoder correction.
                self.pico.goto(frame.stage_x, frame.stage_y)

                # Settle — wait for vibration to die down before capture
                time.sleep(SETTLE_TIME)

                # Read absolute encoder position (mm) after stage has settled.
                # Firmware: whole_revs (from step count) × 0.5 mm + encoder sub-revolution.
                # This gives the true physical frame centre, correcting step-count drift
                # so pad coordinates are anchored to physical reality, not step count.
                enc_abs = self.pico.query_enc_abs()

                # Capture frame and run detection — callback returns detected devices
                devices = on_frame(frame.stage_x, frame.stage_y, enc_abs)
                if devices:
                    self.registry.add_devices(devices)

                on_progress(i + 1, total, frame.stage_x, frame.stage_y)

        except Exception as e:
            print(f"[scanner] Error: {e}")
        finally:
            # Restore speed to whatever the user had set before the scan
            self.pico.set_speed(prev_speed_idx)
            self.is_running = False
            on_done()