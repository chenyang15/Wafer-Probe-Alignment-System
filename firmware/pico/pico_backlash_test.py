"""
pico_backlash_test.py
=====================
Run directly on the Raspberry Pi Pico via Thonny.

HOW TO USE
──────────
1. In Thonny: press the red STOP button to interrupt main.py
2. Open this file in Thonny
3. Press F5 (Run)
4. Results print to the Thonny shell — select all, copy, paste into a .txt
   file, rename to .csv, open in Excel

WHAT IS TESTED
──────────────
TEST 1 — MECHANICAL BACKLASH  (always at slowest speed)
  Homes the axis to the limit switch (ground truth = position 0).
  Moves away by TRAVEL_STEPS, then moves back step-by-step
  counting how many steps until the switch re-triggers.
  Backlash = (return_steps − TRAVEL_STEPS).
  Positive = stage overshot home (limit switch engaged before all
             N return steps were taken) — typical for gear backlash.
  Negative = stage undershot (missed steps on the away move).

TEST 2 — SPEED ACCURACY  (away-move at each preset, slow return)
  Runs the same home→away→back cycle but uses each speed preset
  for the AWAY move. If higher speeds cause missed steps the
  return_steps measurement will deviate more from TRAVEL_STEPS.

TEST 3 — FULL-TRAVEL REPEATABILITY
  Moves home-to-max and back, N_REPEAT times at each speed.
  Counts total travel steps end-to-end to detect cumulative errors.

PIN ASSIGNMENTS (from hardware — do not change)
──────────────
M1 (X axis):  DIR=GP2  STEP=GP3  EN=GP4   MIN=GP18  MAX=GP19
M2 (Y axis):  DIR=GP5  STEP=GP6  EN=GP7   MIN=GP20  MAX=GP21

DIRECTION CONVENTIONS (confirmed via hardware testing)
──────────────
X home → m1_max   (M1_DIR=1 moves toward m1_max)
Y home → m2_max   (M2_DIR=0 moves toward m2_max)
After homing, positive step count = away from home switch.
"""

from machine import Pin
import utime
import sys

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION — edit these if needed
# ─────────────────────────────────────────────────────────────────────────────

# Which axes to test
TEST_X        = True
TEST_Y        = True

# Steps for backlash / speed-accuracy test (300 µm ≈ 1920 steps)
TRAVEL_STEPS  = 3200    # 0.5 mm — short stroke that fits anywhere on wafer

# Steps for full-travel repeatability test (≈ 25 mm travel)
FULL_TRAVEL_STEPS = 155_000   # ~24.2 mm — adjust if your travel is less

# How many cycles per test
BACKLASH_CYCLES      = 15   # pure backlash, slowest speed
SPEED_CYCLES_EACH    = 10   # per speed preset in speed-accuracy test
REPEATABILITY_CYCLES = 10   # full-travel repeatability cycles

# Speed presets  (index → steps/sec from firmware CLAUDE.md)
SPEED_PRESETS = {
    0:  7_826,
    1: 10_435,
    2: 13_043,
    3: 13_695,
    4: 14_348,
}

# Acceleration ramp: how many steps to linearly ramp up/down
ACCEL_STEPS = 800   # ramp over this many steps at start/end of each move

# Safety: max steps before declaring a move failed
TIMEOUT_STEPS = FULL_TRAVEL_STEPS + 10_000

# ─────────────────────────────────────────────────────────────────────────────
# PIN SETUP
# ─────────────────────────────────────────────────────────────────────────────

M1_DIR  = Pin(2,  Pin.OUT)
M1_STEP = Pin(3,  Pin.OUT)
M1_EN   = Pin(4,  Pin.OUT)
M2_DIR  = Pin(5,  Pin.OUT)
M2_STEP = Pin(6,  Pin.OUT)
M2_EN   = Pin(7,  Pin.OUT)

# Limit switches: PULL_UP, active HIGH (NC wired to GND → reads 1 when open, 0 when pressed)
# IMPORTANT: all switches confirmed active HIGH (NC→GND wiring)
M1_MIN  = Pin(18, Pin.IN, Pin.PULL_UP)
M1_MAX  = Pin(19, Pin.IN, Pin.PULL_UP)
M2_MIN  = Pin(20, Pin.IN, Pin.PULL_UP)
M2_MAX  = Pin(21, Pin.IN, Pin.PULL_UP)

# Axis descriptors — bundles all per-axis config
AXES = {
    "X": {
        "step": M1_STEP, "dir": M1_DIR, "en": M1_EN,
        "home_sw": M1_MAX,   # switch that triggers at home position
        "far_sw":  M1_MIN,   # switch at the far end of travel
        "home_dir": 1,       # M1_DIR value that moves TOWARD home switch
        "away_dir": 0,       # M1_DIR value that moves AWAY from home switch
    },
    "Y": {
        "step": M2_STEP, "dir": M2_DIR, "en": M2_EN,
        "home_sw": M2_MAX,
        "far_sw":  M2_MIN,
        "home_dir": 0,
        "away_dir": 1,
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# MOTOR CONTROL
# ─────────────────────────────────────────────────────────────────────────────

def enable(axis):
    AXES[axis]["en"].value(0)   # active-low enable

def disable(axis):
    AXES[axis]["en"].value(1)

def _half_period_us(steps_per_sec):
    """Half period in µs for a given step rate. Minimum 14 µs (MicroPython limit)."""
    return max(14, int(500_000 // steps_per_sec))

def move_steps(axis, n_steps, speed, direction, stop_sw=None, stop_on_active=True):
    """
    Move axis by exactly n_steps at speed (steps/sec) in direction.
    Applies a linear acceleration ramp at start and end.
    If stop_sw is given, stops early if that switch state == stop_on_active.
    Returns actual steps taken.
    """
    ax = AXES[axis]
    ax["dir"].value(direction)
    utime.sleep_us(5)

    slow_us   = _half_period_us(max(500, speed // 4))   # start speed = 25% of target
    fast_us   = _half_period_us(speed)
    ramp      = min(ACCEL_STEPS, n_steps // 4)           # don't ramp more than 25% of move

    def _pulse(half_us):
        ax["step"].value(1)
        utime.sleep_us(half_us)
        ax["step"].value(0)
        utime.sleep_us(half_us)

    for i in range(n_steps):
        # Linear ramp-up at start
        if i < ramp:
            t = slow_us + (fast_us - slow_us) * i // ramp
        # Linear ramp-down at end
        elif i >= n_steps - ramp:
            t = fast_us + (slow_us - fast_us) * (i - (n_steps - ramp)) // max(1, ramp)
        else:
            t = fast_us

        _pulse(t)

        # Early stop on limit switch
        if stop_sw is not None and stop_sw.value() == stop_on_active:
            return i + 1

    return n_steps


def home(axis, speed=None):
    """
    Drive to home limit switch.  Returns steps taken, or -1 on timeout.
    """
    if speed is None:
        speed = SPEED_PRESETS[0]   # always home at slowest speed
    ax = AXES[axis]
    ax["dir"].value(ax["home_dir"])
    utime.sleep_us(5)

    half_us = _half_period_us(speed)
    steps   = 0

    while ax["home_sw"].value() == 0:    # switch not yet active
        ax["step"].value(1)
        utime.sleep_us(half_us)
        ax["step"].value(0)
        utime.sleep_us(half_us)
        steps += 1
        if steps > TIMEOUT_STEPS:
            return -1

    # Tiny back-off so the switch is no longer mechanically loaded
    utime.sleep_ms(50)
    move_steps(axis, 50, SPEED_PRESETS[0], ax["away_dir"])
    utime.sleep_ms(20)
    # Creep back slowly to get a precise trigger point
    slow_half = _half_period_us(1000)
    creep = 0
    while ax["home_sw"].value() == 0 and creep < 500:
        ax["step"].value(1)
        utime.sleep_us(slow_half)
        ax["step"].value(0)
        utime.sleep_us(slow_half)
        creep += 1

    return steps + creep


def return_to_home_count(axis):
    """
    Move step-by-step toward home switch.
    Returns the number of steps taken until the switch triggers.
    Used to measure backlash precisely.
    """
    ax = AXES[axis]
    ax["dir"].value(ax["home_dir"])
    utime.sleep_us(5)

    # Return at slow creep speed for accurate switch-trigger counting
    half_us = _half_period_us(1500)
    steps   = 0

    while ax["home_sw"].value() == 0:
        ax["step"].value(1)
        utime.sleep_us(half_us)
        ax["step"].value(0)
        utime.sleep_us(half_us)
        steps += 1
        if steps > TRAVEL_STEPS * 3:   # safety: stop if way more steps than expected
            return steps

    return steps

# ─────────────────────────────────────────────────────────────────────────────
# CSV OUTPUT HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def csv_header(*cols):
    print(",".join(cols))

def csv_row(*vals):
    print(",".join(str(v) for v in vals))

def section(title):
    print()
    print("# " + "=" * 60)
    print("# " + title)
    print("# " + "=" * 60)

def stats(values):
    if not values:
        return 0, 0, 0
    n   = len(values)
    avg = sum(values) / n
    mx  = max(abs(v) for v in values)
    var = sum((v - avg) ** 2 for v in values) / max(1, n - 1)
    sd  = var ** 0.5
    return avg, mx, sd

# ─────────────────────────────────────────────────────────────────────────────
# TEST 1 — MECHANICAL BACKLASH  (slowest speed throughout)
# ─────────────────────────────────────────────────────────────────────────────

def test_backlash(axis):
    section(f"TEST 1: MECHANICAL BACKLASH  axis={axis}  speed=preset_0 ({SPEED_PRESETS[0]} steps/s)")
    print(f"# travel={TRAVEL_STEPS} steps ({TRAVEL_STEPS/6400*1000:.0f} µm)  cycles={BACKLASH_CYCLES}")
    print()
    csv_header("test","axis","cycle","travel_steps","return_steps",
               "backlash_steps","backlash_um","note")

    speed   = SPEED_PRESETS[0]
    results = []

    for cyc in range(1, BACKLASH_CYCLES + 1):
        # Home
        h = home(axis)
        if h < 0:
            csv_row("backlash", axis, cyc, TRAVEL_STEPS, "?", "?", "?", "HOME_TIMEOUT")
            continue

        # Move away from home
        moved = move_steps(axis, TRAVEL_STEPS, speed, AXES[axis]["away_dir"],
                           stop_sw=AXES[axis]["far_sw"], stop_on_active=1)
        utime.sleep_ms(100)

        # Move back step-by-step and count steps to re-trigger home switch
        ret = return_to_home_count(axis)
        utime.sleep_ms(100)

        backlash_steps = ret - moved
        backlash_um    = round(backlash_steps / 6400 * 1000, 1)
        note           = "short_travel" if moved < TRAVEL_STEPS else "ok"

        csv_row("backlash", axis, cyc, moved, ret, backlash_steps, backlash_um, note)
        results.append(backlash_steps)

    avg, mx, sd = stats(results)
    print(f"# SUMMARY  axis={axis}  avg={avg/6400*1000:+.1f}µm  "
          f"max={mx/6400*1000:.1f}µm  stdev={sd/6400*1000:.1f}µm  "
          f"avg_steps={avg:+.1f}  max_steps={mx:.1f}")
    return results


# ─────────────────────────────────────────────────────────────────────────────
# TEST 2 — SPEED ACCURACY  (vary away-move speed, slow return)
# ─────────────────────────────────────────────────────────────────────────────

def test_speed_accuracy(axis):
    section(f"TEST 2: SPEED ACCURACY  axis={axis}")
    print(f"# travel={TRAVEL_STEPS} steps ({TRAVEL_STEPS/6400*1000:.0f} µm)  "
          f"cycles_per_speed={SPEED_CYCLES_EACH}")
    print()
    csv_header("test","axis","speed_idx","steps_per_sec","cycle",
               "travel_steps","return_steps","error_steps","error_um","note")

    all_summaries = []

    for sidx, speed in SPEED_PRESETS.items():
        errors = []
        for cyc in range(1, SPEED_CYCLES_EACH + 1):
            h = home(axis)
            if h < 0:
                csv_row("speed", axis, sidx, speed, cyc,
                        TRAVEL_STEPS,"?","?","?","HOME_TIMEOUT")
                continue

            # Away move at test speed
            moved = move_steps(axis, TRAVEL_STEPS, speed, AXES[axis]["away_dir"],
                               stop_sw=AXES[axis]["far_sw"], stop_on_active=1)
            utime.sleep_ms(100)

            # Return at fixed slow speed
            ret = return_to_home_count(axis)
            utime.sleep_ms(100)

            err_steps = ret - moved
            err_um    = round(err_steps / 6400 * 1000, 1)
            note      = "short_travel" if moved < TRAVEL_STEPS else "ok"

            csv_row("speed", axis, sidx, speed, cyc,
                    moved, ret, err_steps, err_um, note)
            errors.append(err_steps)

        avg, mx, sd = stats(errors)
        all_summaries.append((sidx, speed, avg, mx, sd))
        print(f"# speed={sidx} ({speed} sps)  "
              f"avg={avg/6400*1000:+.1f}µm  max={mx/6400*1000:.1f}µm  "
              f"stdev={sd/6400*1000:.1f}µm")

    print()
    print("# SPEED SUMMARY  axis=" + axis)
    print("# speed_idx,steps_per_sec,avg_um,max_um,stdev_um,avg_steps,max_steps")
    for sidx, speed, avg, mx, sd in all_summaries:
        print(f"# {sidx},{speed},{avg/6400*1000:+.2f},{mx/6400*1000:.2f},"
              f"{sd/6400*1000:.2f},{avg:+.2f},{mx:.2f}")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 3 — FULL-TRAVEL REPEATABILITY
# (home → far end → home, count steps each way, check consistency)
# ─────────────────────────────────────────────────────────────────────────────

def test_full_travel(axis):
    section(f"TEST 3: FULL-TRAVEL REPEATABILITY  axis={axis}")
    print(f"# cycles={REPEATABILITY_CYCLES}  speed=preset_0")
    print()
    csv_header("test","axis","cycle","steps_fwd","steps_bwd",
               "total_steps","diff_from_first","note")

    speed    = SPEED_PRESETS[0]
    ax       = AXES[axis]
    results  = []
    first_total = None

    for cyc in range(1, REPEATABILITY_CYCLES + 1):
        # Start from home
        h = home(axis)
        if h < 0:
            csv_row("fulltravel", axis, cyc,"?","?","?","?","HOME_TIMEOUT")
            continue

        # Move toward far limit switch, count steps
        fwd_steps = 0
        ax["dir"].value(ax["away_dir"])
        utime.sleep_us(5)
        half_us = _half_period_us(speed)
        while ax["far_sw"].value() == 0 and fwd_steps < TIMEOUT_STEPS:
            ax["step"].value(1)
            utime.sleep_us(half_us)
            ax["step"].value(0)
            utime.sleep_us(half_us)
            fwd_steps += 1
        utime.sleep_ms(100)

        # Move back to home switch, count steps
        bwd_steps = return_to_home_count(axis)
        utime.sleep_ms(100)

        total = fwd_steps + bwd_steps
        if first_total is None:
            first_total = total
        diff  = total - first_total
        note  = "TIMEOUT" if fwd_steps >= TIMEOUT_STEPS else "ok"

        csv_row("fulltravel", axis, cyc, fwd_steps, bwd_steps, total, diff, note)
        results.append(total)

    avg, mx, sd = stats([r - results[0] for r in results])
    print(f"# SUMMARY  axis={axis}  first_total={results[0] if results else '?'}steps  "
          f"max_deviation={mx/6400*1000:.1f}µm  stdev={sd/6400*1000:.1f}µm")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("# pico_backlash_test.py")
    print("# Copy everything below this line into a .csv file")
    print("# Steps per mm = 6400   |   1 step = 0.15625 µm")
    print()

    axes = []
    if TEST_X:
        axes.append("X")
    if TEST_Y:
        axes.append("Y")

    if not axes:
        print("# No axes selected — set TEST_X or TEST_Y to True")
        return

    for axis in axes:
        enable(axis)
        utime.sleep_ms(200)

        try:
            # ── Verify home switch detects correctly ──────────────────────
            print(f"# Checking {axis} switches...")
            ax = AXES[axis]
            sw_home = ax["home_sw"].value()
            sw_far  = ax["far_sw"].value()
            print(f"# {axis}: home_sw={'ACTIVE' if sw_home else 'open'}  "
                  f"far_sw={'ACTIVE' if sw_far else 'open'}")
            if sw_home and sw_far:
                print(f"# WARNING: both {axis} switches active — check wiring")
            print()

            # ── Run the three tests ───────────────────────────────────────
            test_backlash(axis)
            utime.sleep_ms(500)

            test_speed_accuracy(axis)
            utime.sleep_ms(500)

            test_full_travel(axis)
            utime.sleep_ms(500)

        except KeyboardInterrupt:
            print(f"\n# Interrupted during {axis} test")
            break
        finally:
            disable(axis)

    print()
    print("# All tests complete.")
    print("# Paste above output into Excel — use Data > Text to Columns > Comma delimiter")
    print("# Filter column A for each test type (backlash / speed / fulltravel)")


main()
