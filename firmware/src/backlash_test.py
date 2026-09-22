"""
backlash_test.py
Characterises stage backlash and speed accuracy.

TWO test modes
──────────────
1. BACKLASH TEST  (default)
   Homes the axis, then repeatedly moves +travel_mm and back.
   Each cycle records the POS after each leg.
   Ideal: pos_after_return == 0.000 every time.
   Any deviation = accumulated error (missed steps or backlash).

2. SPEED TEST
   Runs the backlash test at every speed preset (0–4).
   Lets you compare how many steps are lost per speed level.

Output
──────
CSV files written to the same directory as this script:
  backlash_<axis>_speed<N>.csv
  speed_summary.csv

Usage
─────
  python backlash_test.py               # backlash test, X axis, speed 2, 20 cycles
  python backlash_test.py --axis Y      # Y axis
  python backlash_test.py --speed 0     # specific speed preset
  python backlash_test.py --all-speeds  # test all speeds (writes summary CSV)
  python backlash_test.py --cycles 50   # more cycles for better statistics
  python backlash_test.py --travel 10   # 10 mm stroke instead of 5 mm
"""

import sys
import os
import time
import csv
import argparse
import statistics

# Add src to path so we can import pico_controller
sys.path.insert(0, os.path.dirname(__file__))
from pico_controller import PicoController

OUT_DIR = os.path.dirname(os.path.abspath(__file__))


# ── helpers ──────────────────────────────────────────────────────────────────

def connect(port=None):
    pico = PicoController()
    ok, msg = pico.connect(port)
    if not ok:
        print(f"[ERROR] Could not connect to Pico: {msg}")
        sys.exit(1)
    print(f"[OK] Connected on {pico.port}")
    return pico


def home_axis(pico, axis):
    print(f"  Homing {axis}…", end=" ", flush=True)
    ok = pico.home(axis)
    print("done" if ok else "FAILED")
    return ok


def run_backlash_test(pico, axis, speed_idx, travel_mm, cycles):
    """
    Move +travel_mm then -travel_mm (cycles) times.
    Returns list of dicts with per-leg position readings.
    """
    pico.set_speed(speed_idx)
    time.sleep(0.2)

    if not home_axis(pico, axis):
        return []

    rows = []
    print(f"\n  axis={axis}  speed={speed_idx}  travel={travel_mm}mm  cycles={cycles}")
    print(f"  {'cycle':>6}  {'pos_after_fwd':>14}  {'pos_after_bwd':>14}  {'error_mm':>10}")
    print(f"  {'-'*6}  {'-'*14}  {'-'*14}  {'-'*10}")

    for i in range(cycles):
        # Forward move
        pico.move(axis, travel_mm)
        pos_fwd = pico.pos_x if axis == "X" else pico.pos_y

        # Backward move (return to home)
        pico.move(axis, -travel_mm)
        pos_bwd = pico.pos_x if axis == "X" else pico.pos_y

        # Error = deviation from 0 after return
        error = pos_bwd   # should be 0.000

        print(f"  {i+1:>6}  {pos_fwd:>14.4f}  {pos_bwd:>14.4f}  {error:>+10.4f}")

        rows.append({
            "cycle":        i + 1,
            "axis":         axis,
            "speed_idx":    speed_idx,
            "travel_mm":    travel_mm,
            "pos_fwd_mm":   pos_fwd,
            "pos_bwd_mm":   pos_bwd,
            "error_mm":     error,
        })

        # Re-home every 10 cycles to prevent error accumulation masking backlash
        if (i + 1) % 10 == 0 and (i + 1) < cycles:
            home_axis(pico, axis)

    return rows


def summarise(rows, axis, speed_idx):
    errors = [r["error_mm"] for r in rows]
    if not errors:
        return {}
    return {
        "axis":         axis,
        "speed_idx":    speed_idx,
        "cycles":       len(errors),
        "mean_err_mm":  round(statistics.mean(errors), 5),
        "max_err_mm":   round(max(abs(e) for e in errors), 5),
        "stdev_mm":     round(statistics.stdev(errors) if len(errors) > 1 else 0, 5),
        "steps_per_mm": 6400,
        "max_err_steps": round(max(abs(e) for e in errors) * 6400, 2),
    }


def write_csv(rows, filename):
    if not rows:
        return
    path = os.path.join(OUT_DIR, filename)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"  → saved {path}")


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Stage backlash/speed characterisation")
    parser.add_argument("--axis",       default="X",  choices=["X", "Y", "ALL"])
    parser.add_argument("--speed",      default=2,    type=int, choices=range(5))
    parser.add_argument("--travel",     default=5.0,  type=float,
                        help="stroke length in mm (default 5)")
    parser.add_argument("--cycles",     default=20,   type=int,
                        help="repeat cycles per test (default 20)")
    parser.add_argument("--all-speeds", action="store_true",
                        help="sweep all speed presets (0–4) and write summary CSV")
    parser.add_argument("--port",       default=None)
    args = parser.parse_args()

    pico = connect(args.port)

    axes = ["X", "Y"] if args.axis == "ALL" else [args.axis]
    speeds = list(range(5)) if args.all_speeds else [args.speed]

    all_summaries = []

    for axis in axes:
        for speed_idx in speeds:
            print(f"\n{'='*60}")
            print(f"  BACKLASH TEST  axis={axis}  speed_preset={speed_idx}")
            print(f"{'='*60}")

            rows = run_backlash_test(pico, axis, speed_idx, args.travel, args.cycles)

            fname = f"backlash_{axis}_speed{speed_idx}.csv"
            write_csv(rows, fname)

            s = summarise(rows, axis, speed_idx)
            if s:
                all_summaries.append(s)
                print(f"\n  Summary:")
                print(f"    mean error  : {s['mean_err_mm']:+.5f} mm  ({s['mean_err_mm']*1000:+.2f} µm)")
                print(f"    max  error  : {s['max_err_mm']:.5f} mm  ({s['max_err_mm']*1000:.2f} µm)")
                print(f"    stdev       : {s['stdev_mm']:.5f} mm  ({s['stdev_mm']*1000:.2f} µm)")
                print(f"    max in steps: {s['max_err_steps']:.1f} steps  (1 step = 0.156 µm)")

    if len(all_summaries) > 1:
        write_csv(all_summaries, "speed_summary.csv")
        print(f"\n{'='*60}")
        print("  SPEED SUMMARY")
        print(f"  {'axis':>4}  {'speed':>5}  {'mean_err_um':>12}  {'max_err_um':>11}  {'stdev_um':>9}")
        for s in all_summaries:
            print(f"  {s['axis']:>4}  {s['speed_idx']:>5}  "
                  f"{s['mean_err_mm']*1000:>+12.2f}  "
                  f"{s['max_err_mm']*1000:>11.2f}  "
                  f"{s['stdev_mm']*1000:>9.2f}")

    pico.disconnect()
    print("\nDone.")


if __name__ == "__main__":
    main()
