import select
import sys
import _thread
import time
from machine import Pin, SPI, UART
import rp2

# ── Probe slave UART ───────────────────────────────────────────────────────────
# GP16 = TX (master → slave GP17 RX)
# GP17 = RX (master ← slave GP16 TX)
# timeout=5 ms — relay loop reads in small chunks; not a blocking readline.
probe_uart = UART(0, baudrate=115200, tx=Pin(16), rx=Pin(17), timeout=5)

# ── Motion constants ───────────────────────────────────
MICROSTEPS    = 16
STEPS_PER_REV = 200 * MICROSTEPS
MM_PER_REV    = 0.5
STEPS_PER_MM  = STEPS_PER_REV / MM_PER_REV   # 6400 steps/mm

MIN_SPEED  = 2000    # steps/sec — above resonance zone (~31–80 full steps/sec for NEMA17)
MAX_SPEED  = 13043   # steps/sec (100% speed)
ACCEL      = 40000   # steps/sec²  — gentle enough for both motors to track reliably
HOME_SPEED = 13043   # always home at 100% regardless of UI setting

SPEED_PRESETS = {
    0: 7826,    # 60%
    1: 9130,    # 70% — used for scanning (reduces X vibration and lead-screw resonance)
    2: 10435,   # 80%
    3: 13043,   # 100%
    4: 14348,   # 110%
}

# ── Encoder constants ──────────────────────────────────
# ENC_DIR = +1  →  raw angle INCREASES when stage moves AWAY from home (positive direction).
# ENC_DIR = -1  →  raw angle DECREASES when stage moves away from home.
# Verified by manual test: moving away from home increases raw count on both axes.
ENC_DIR_X = 1
ENC_DIR_Y = 1

ENC_COUNTS_PER_REV = 2_097_152   # 2^21  (MT6835 21-bit)
ENC_HALF           = 1_048_576   # half revolution, used for wrap-safe arithmetic

# After a commanded move, correct if encoder error exceeds this threshold.
# Set to 0 to disable correction entirely.
CORR_THRESHOLD_MM = 0.050   # 50 µm threshold — active for MOVETO (device goto only)
MAX_CORR_MM       = 0.200   # never correct more than 200 µm in one shot

# ── Motor pins ─────────────────────────────────────────
M1_DIR=2; M1_STEP=3; M1_EN=4; M1_MIN=18; M1_MAX=19
M2_DIR=5; M2_STEP=6; M2_EN=7; M2_MIN=20; M2_MAX=21

m1_dir=Pin(M1_DIR,Pin.OUT); m1_en=Pin(M1_EN,Pin.OUT)
m1_min=Pin(M1_MIN,Pin.IN,Pin.PULL_UP)
m1_max=Pin(M1_MAX,Pin.IN,Pin.PULL_UP)
m2_dir=Pin(M2_DIR,Pin.OUT); m2_en=Pin(M2_EN,Pin.OUT)
m2_min=Pin(M2_MIN,Pin.IN,Pin.PULL_UP)
m2_max=Pin(M2_MAX,Pin.IN,Pin.PULL_UP)
m1_en.low(); m2_en.low()

# ── Encoder SPI ────────────────────────────────────────
# SCK=GP14  MOSI=GP11  MISO=GP12  CS_X=GP9  CS_Y=GP13
# MT6835 needs SPI Mode 3 (CPOL=1, CPHA=1).
spi = SPI(1, baudrate=1_000_000, polarity=1, phase=1,
          sck=Pin(14), mosi=Pin(11), miso=Pin(12))
enc_cs_x = Pin(9,  Pin.OUT, value=1)
enc_cs_y = Pin(13, Pin.OUT, value=1)

# Home-position encoder angles, recorded at the end of each HOME command.
enc_home_angle = {'x': 0, 'y': 0}
enc_calibrated = {'x': False, 'y': False}

# ── PIO step pulse ─────────────────────────────────────
PIO_CYC = 23

@rp2.asm_pio(set_init=rp2.PIO.OUT_LOW)
def step_pulse():
    pull(block)
    mov(x, osr)
    label("loop")
    set(pins, 1) [10]
    set(pins, 0) [10]
    jmp(x_dec, "loop")

def pio_freq(steps_per_sec):
    return max(MIN_SPEED * PIO_CYC, min(60_000_000, int(steps_per_sec * PIO_CYC)))

# ── Shared state ───────────────────────────────────────
position = {'x': 0.0, 'y': 0.0}

y_req = {'steps': 0, 'direction': 0, 'speed': 0,
         'stop_pin': None, 'active': False, 'done': True,
         'is_corr': False}   # True = correction move; y_thread skips position update

def limit_hit(pin):
    return pin.value() == 1

# ── MT6835 encoder read ────────────────────────────────
def read_angle(cs):
    """
    Burst-read 21-bit angle.  TX: [0xA0, 0x03, 0,0,0,0]
    Returns 0–2097151, or -1 if the encoder is not responding.
    Only call from Core 0.
    """
    tx = bytearray([0xA0, 0x03, 0x00, 0x00, 0x00, 0x00])
    rx = bytearray(6)
    cs.value(0)
    time.sleep_us(2)
    spi.write_readinto(tx, rx)
    time.sleep_us(2)
    cs.value(1)
    if rx[2] == 0xFF and rx[3] == 0xFF and rx[4] == 0xFF:
        return -1
    return ((rx[2] << 13) | (rx[3] << 5) | (rx[4] >> 3)) & 0x1FFFFF

def set_encoder_home(axis):
    """Record current encoder angle as the zero reference.  Call after homing."""
    cs = enc_cs_x if axis == 'x' else enc_cs_y
    raw = read_angle(cs)
    if raw >= 0:
        enc_home_angle[axis] = raw
        enc_calibrated[axis] = True
        print(f"ENC_HOME:{axis.upper()}={raw}")
    else:
        enc_calibrated[axis] = False
        print(f"ENC_WARN:{axis.upper()}_NO_RESPONSE")

def enc_angle_from_home(axis):
    """
    Read the current encoder angle relative to the home position.
    Returns an integer in [0, ENC_COUNTS_PER_REV), or -1 if not calibrated
    or encoder not responding.  Identical to the angle_from_home computation
    inside enc_error_mm — factored out so it can be called independently.
    """
    if not enc_calibrated[axis]:
        return -1
    cs      = enc_cs_x if axis == 'x' else enc_cs_y
    enc_dir = ENC_DIR_X if axis == 'x' else ENC_DIR_Y
    raw = read_angle(cs)
    if raw < 0:
        return -1
    return ((raw - enc_home_angle[axis]) * enc_dir) % ENC_COUNTS_PER_REV

def enc_abs_mm(axis):
    """
    Return the absolute encoder-measured position in mm.

    Strategy: use the step-count position to determine the correct whole-revolution
    number, then replace the sub-revolution part with the precise encoder reading.
    This gives true physical position accurate to encoder resolution (~0.24 nm)
    as long as step-count error is less than ±0.25 mm (half a revolution) — which
    is always the case for our system (typical slip < 50 µm per move).

    Formula:
        sub_rev_mm  = afh / ENC_COUNTS_PER_REV × MM_PER_REV   (0 … 0.5 mm)
        whole_revs  = round((position - sub_rev_mm) / MM_PER_REV)
        abs_pos_mm  = whole_revs × MM_PER_REV + sub_rev_mm

    Returns None if encoder is not calibrated or not responding.
    """
    afh = enc_angle_from_home(axis)
    if afh < 0:
        return None
    sub_rev_mm  = afh / ENC_COUNTS_PER_REV * MM_PER_REV
    whole_revs  = int(round((position[axis] - sub_rev_mm) / MM_PER_REV))
    return whole_revs * MM_PER_REV + sub_rev_mm

def enc_error_mm(axis):
    """
    Return the signed error between the encoder-measured position and the
    step-count position, in mm.

      Positive  → stage is physically AHEAD of step-count position.
      Negative  → stage is physically BEHIND step-count position.

    Because the MT6835 is single-turn absolute, we compare fractional
    revolution only (good to ±0.25 mm — far larger than any realistic slip).
    Returns 0.0 when not calibrated or encoder not responding.
    """
    angle_from_home = enc_angle_from_home(axis)
    if angle_from_home < 0:
        return 0.0

    # Where within the current revolution the step count says we should be.
    frac_rev       = (position[axis] / MM_PER_REV) % 1.0
    expected_angle = int(frac_rev * ENC_COUNTS_PER_REV) % ENC_COUNTS_PER_REV

    # Signed difference, wrapped to ±half-revolution.
    err = angle_from_home - expected_angle
    if err >  ENC_HALF: err -= ENC_COUNTS_PER_REV
    if err < -ENC_HALF: err += ENC_COUNTS_PER_REV

    err_mm = err / ENC_COUNTS_PER_REV * MM_PER_REV
    return err_mm

def encoder_correction(axis):
    """
    After a commanded move, check the encoder error once.
    If it exceeds CORR_THRESHOLD_MM, issue ONE correction move (capped at MAX_CORR_MM).

    CRITICAL — do NOT call update_position here.
    A correction physically moves the stage to match the existing step-count position.
    position[] is already where we want to be; updating it would over-count by the
    correction amount and flip the error sign on every move → zig-zag oscillation.
    """
    if CORR_THRESHOLD_MM == 0:
        return
    err = enc_error_mm(axis)
    if abs(err) <= CORR_THRESHOLD_MM:
        return
    corr = max(-MAX_CORR_MM, min(MAX_CORR_MM, -err))
    steps = int(abs(corr) * STEPS_PER_MM)
    if steps == 0:
        return
    print(f"CORR:{axis.upper()}={corr:.4f}mm err={err:.4f}mm")

    if axis == 'x':
        direction = 1 if corr > 0 else 0
        move_accel(1, steps, direction)
        # No update_position — physical stage now matches step count
    else:
        direction = 0 if corr > 0 else 1
        y_req['steps']    = steps
        y_req['direction']= direction
        y_req['speed']    = 0
        y_req['stop_pin'] = None
        y_req['is_corr']  = True   # tells y_thread to skip its position update
        y_req['done']     = False
        y_req['active']   = True
        while not y_req['done']:
            time.sleep(0.001)

def encoder_correction_ref(axis, afh_ref):
    """
    Encoder correction using a stored angle-from-home reference instead of the
    step-count derived expected angle used by encoder_correction().

    Why this is better for repeated 'Go To Device':
      encoder_correction() computes expected_angle from position[], which can be
      wrong if step-count drift accumulated during the scan.  If that error exceeds
      ±ENC_HALF (±0.25 mm), the direction wraps and the correction makes things worse.

      With a stored reference (recorded after a successful previous goto), we compare
      the current angle_from_home directly against the reference angle_from_home.
      Since MOVETO always lands within ±0.25 mm of the target, the difference is always
      within the detection range — direction is always correct.

    Does NOT call update_position — same reasoning as encoder_correction().
    Only fires if CORR_THRESHOLD_MM > 0 (respects global correction enable/disable).
    """
    if CORR_THRESHOLD_MM == 0:
        return
    afh = enc_angle_from_home(axis)
    if afh < 0:
        return   # encoder not calibrated or not responding

    err = afh - afh_ref
    if err >  ENC_HALF: err -= ENC_COUNTS_PER_REV
    if err < -ENC_HALF: err += ENC_COUNTS_PER_REV
    err_mm = err / ENC_COUNTS_PER_REV * MM_PER_REV

    print(f"CORR_REF:{axis.upper()} afh={afh} ref={afh_ref} err={err_mm:.4f}mm")

    if abs(err_mm) <= CORR_THRESHOLD_MM:
        return
    corr  = max(-MAX_CORR_MM, min(MAX_CORR_MM, -err_mm))
    steps = int(abs(corr) * STEPS_PER_MM)
    if steps == 0:
        return

    if axis == 'x':
        direction = 1 if corr > 0 else 0
        move_accel(1, steps, direction)
        # No update_position — physical stage snaps to match step-count reference
    else:
        direction = 0 if corr > 0 else 1
        y_req['steps']    = steps
        y_req['direction']= direction
        y_req['speed']    = 0
        y_req['stop_pin'] = None
        y_req['is_corr']  = True   # skip position update in y_thread
        y_req['done']     = False
        y_req['active']   = True
        while not y_req['done']:
            time.sleep(0.001)

# ── Accelerated move ───────────────────────────────────
def move_accel(motor, total_steps, direction, speed=0, stop_pin=None):
    """
    Trapezoidal + S-curve move.
    Returns actual steps executed.
    """
    if total_steps <= 0:
        return 0

    if motor == 1:
        dp=m1_dir; sp=M1_STEP; sid=0
        lim_fwd=m1_min; lim_bwd=m1_max
    else:
        dp=m2_dir; sp=M2_STEP; sid=1
        lim_fwd=m2_max; lim_bwd=m2_min

    if stop_pin is None:
        if direction == 0 and limit_hit(lim_fwd):
            return 0
        if direction == 1 and limit_hit(lim_bwd):
            return 0

    dp.value(direction)
    time.sleep(0.001)

    cur_max = speed if speed > 0 else MAX_SPEED

    if stop_pin is not None:
        CHUNK = 1000
    elif total_steps <= 64:
        CHUNK = 8
    elif total_steps <= 640:
        CHUNK = 64
    else:
        CHUNK = 500   # was 200 — fewer SM reinit gaps → less Core-0 USB jitter effect

    accel_s  = int((cur_max**2 - MIN_SPEED**2) / (2 * ACCEL))
    accel_s  = max(1, min(accel_s, total_steps // 2))
    decel_s  = accel_s
    cruise_s = total_steps - accel_s - decel_s
    done     = 0

    lim_fwd_at_start = limit_hit(lim_fwd)
    lim_bwd_at_start = limit_hit(lim_bwd)

    def should_stop():
        if stop_pin is not None:
            return limit_hit(stop_pin)
        if direction == 0:
            return limit_hit(lim_fwd) and not lim_fwd_at_start
        return limit_hit(lim_bwd) and not lim_bwd_at_start

    def run_chunk(steps, spd):
        sm = rp2.StateMachine(sid, step_pulse,
                              freq=pio_freq(spd), set_base=Pin(sp))
        sm.active(1)
        sm.put(steps - 1)
        time.sleep(steps / spd + 0.0005)
        sm.active(0)

    while done < accel_s:
        if should_stop(): return done
        ch   = min(CHUNK, accel_s - done)
        prog = ((done + ch / 2) / accel_s) ** 3
        spd  = MIN_SPEED + (cur_max - MIN_SPEED) * prog
        run_chunk(ch, max(MIN_SPEED, spd))
        done += ch

    while done < accel_s + cruise_s:
        if should_stop(): return done
        ch = min(CHUNK, accel_s + cruise_s - done)
        run_chunk(ch, cur_max)
        done += ch

    while done < total_steps:
        if should_stop(): return done
        ch   = min(CHUNK, total_steps - done)
        dd   = done - accel_s - cruise_s
        prog = 1 - (1 - (dd + ch / 2) / max(1, decel_s)) ** 3
        spd  = MIN_SPEED + (cur_max - MIN_SPEED) * (1 - prog)
        run_chunk(ch, max(MIN_SPEED, spd))
        done += ch

    return done

# ── Position tracking ──────────────────────────────────
def update_position(axis, steps_taken, mm_requested):
    dist = steps_taken / STEPS_PER_MM
    if mm_requested >= 0:
        position[axis] += dist
    else:
        position[axis] -= dist

# ── Y axis thread (Core 1) ─────────────────────────────
def y_thread():
    while True:
        try:
            if y_req['active']:
                steps = move_accel(
                    2,
                    y_req['steps'],
                    y_req['direction'],
                    speed=y_req['speed'],
                    stop_pin=y_req['stop_pin'],
                )
                if y_req['stop_pin'] is None and not y_req['is_corr']:
                    mm = y_req['steps'] / STEPS_PER_MM
                    if y_req['direction'] == 1:
                        mm = -mm
                    update_position('y', steps, mm)
                y_req['is_corr'] = False
                y_req['active']  = False
                y_req['done']    = True
        except Exception as e:
            print(f"CORE1_ERR:{e}")
            y_req['active'] = False
            y_req['done']   = True
        time.sleep(0.001)

_thread.start_new_thread(y_thread, ())

# ── Move helpers ───────────────────────────────────────
def move_axis(motor, mm):
    steps = int(abs(mm) * STEPS_PER_MM)
    if steps == 0:
        return
    if motor == 1:
        direction = 1 if mm > 0 else 0
        taken = move_accel(1, steps, direction)
        update_position('x', taken, mm)
    else:
        direction = 0 if mm > 0 else 1
        y_req['steps']    = steps
        y_req['direction']= direction
        y_req['speed']    = 0
        y_req['stop_pin'] = None
        y_req['done']     = False
        y_req['active']   = True
        while not y_req['done']:
            time.sleep(0.001)

# ── Homing ─────────────────────────────────────────────
def home_x():
    print("HOMING:X")
    move_accel(1, int(200 * STEPS_PER_MM), direction=0,
               speed=HOME_SPEED, stop_pin=m1_min)
    position['x'] = 0.0
    set_encoder_home('x')
    print("HOMED:X")

def home_y_on_core1():
    """Start Y homing on Core 1 (non-blocking)."""
    y_req['steps']    = int(200 * STEPS_PER_MM)
    y_req['direction']= 1
    y_req['speed']    = HOME_SPEED
    y_req['stop_pin'] = m2_min
    y_req['done']     = False
    y_req['active']   = True

def home_y_direct():
    print("HOMING:Y")
    move_accel(2, int(200 * STEPS_PER_MM), direction=1,
               speed=HOME_SPEED, stop_pin=m2_min)
    position['y'] = 0.0
    set_encoder_home('y')
    print("HOMED:Y")

# ── Command handler ────────────────────────────────────
def handle(cmd):
    cmd = cmd.strip()
    if not cmd:
        return

    # ── MOVETO_REF (device goto with stored encoder reference) ───────────
    # Must be checked BEFORE both MOVETO and MOVE since the name starts with "MOVETO".
    # Uses a stored angle-from-home reference for correction instead of the step-count
    # derived expected angle, eliminating the ±0.25 mm wrap issue on repeated gotos.
    if cmd.startswith("MOVETO_REF"):
        parts   = cmd.split()
        x_abs   = float(parts[1])
        y_abs   = float(parts[2])
        afh_ref_x = int(parts[3])
        afh_ref_y = int(parts[4])
        dx = x_abs - position['x']
        dy = y_abs - position['y']

        # Simultaneous XY move — identical to MOVETO
        if int(abs(dy) * STEPS_PER_MM) > 0:
            y_dir = 0 if dy > 0 else 1
            y_req['steps']    = int(abs(dy) * STEPS_PER_MM)
            y_req['direction']= y_dir
            y_req['speed']    = 0
            y_req['stop_pin'] = None
            y_req['is_corr']  = False
            y_req['done']     = False
            y_req['active']   = True

        if int(abs(dx) * STEPS_PER_MM) > 0:
            move_axis(1, dx)

        while not y_req['done']:
            time.sleep(0.001)

        # Reference-based correction — always reliable within ±0.25 mm
        encoder_correction_ref('x', afh_ref_x)
        encoder_correction_ref('y', afh_ref_y)

        # Read final encoder state — PC stores this as the updated reference
        final_afh_x = enc_angle_from_home('x')
        final_afh_y = enc_angle_from_home('y')
        if final_afh_x < 0: final_afh_x = afh_ref_x   # fallback if encoder not responding
        if final_afh_y < 0: final_afh_y = afh_ref_y
        print(f"POS_ENC:{position['x']:.4f},{position['y']:.4f},{final_afh_x},{final_afh_y}")

    # ── MOVETO (device positioning — absolute + single encoder correction) ─
    # Must be checked BEFORE "MOVE" since MOVETO starts with "MOVE".
    elif cmd.startswith("MOVETO"):
        parts = cmd.split()
        x_abs = float(parts[1])
        y_abs = float(parts[2])
        dx = x_abs - position['x']
        dy = y_abs - position['y']

        # Move both axes simultaneously (same as MOVE XY)
        if int(abs(dy) * STEPS_PER_MM) > 0:
            y_dir = 0 if dy > 0 else 1
            y_req['steps']    = int(abs(dy) * STEPS_PER_MM)
            y_req['direction']= y_dir
            y_req['speed']    = 0
            y_req['stop_pin'] = None
            y_req['is_corr']  = False
            y_req['done']     = False
            y_req['active']   = True

        if int(abs(dx) * STEPS_PER_MM) > 0:
            move_axis(1, dx)

        while not y_req['done']:
            time.sleep(0.001)

        # Single encoder correction pass — moves physical stage to match step count
        encoder_correction('x')
        encoder_correction('y')

        print(f"POS:{position['x']:.4f},{position['y']:.4f}")

    # ── MOVE (scan / jog — step count only, no encoder correction) ───────
    elif cmd.startswith("MOVE"):
        parts = cmd.split()

        if len(parts) == 4 and parts[1].upper() == "XY":
            x_mm = float(parts[2])
            y_mm = float(parts[3])

            if int(abs(y_mm) * STEPS_PER_MM) > 0:
                y_dir = 0 if y_mm > 0 else 1
                y_req['steps']    = int(abs(y_mm) * STEPS_PER_MM)
                y_req['direction']= y_dir
                y_req['speed']    = 0
                y_req['stop_pin'] = None
                y_req['is_corr']  = False
                y_req['done']     = False
                y_req['active']   = True

            if int(abs(x_mm) * STEPS_PER_MM) > 0:
                move_axis(1, x_mm)

            while not y_req['done']:
                time.sleep(0.001)

        elif len(parts) == 3:
            axis = parts[1].upper()
            mm   = float(parts[2])
            move_axis(1 if axis == 'X' else 2, mm)

        print(f"POS:{position['x']:.4f},{position['y']:.4f}")

    # ── HOME ──────────────────────────────────────────
    elif cmd.startswith("HOME"):
        parts = cmd.split()
        t = parts[1].upper() if len(parts) > 1 else "ALL"

        if t == "X":
            home_x()
            print(f"POS:{position['x']:.4f},{position['y']:.4f}")

        elif t == "Y":
            home_y_direct()
            print(f"POS:{position['x']:.4f},{position['y']:.4f}")

        elif t == "ALL":
            print("HOMING:Y")
            home_y_on_core1()          # Y on Core 1
            home_x()                   # X on Core 0 (simultaneous)
            while not y_req['done']:   # wait for Y to finish
                time.sleep(0.001)
            position['y'] = 0.0
            set_encoder_home('y')
            print("HOMED:Y")
            print(f"POS:{position['x']:.4f},{position['y']:.4f}")

    # ── SPEED ─────────────────────────────────────────
    elif cmd.startswith("SPEED"):
        try:
            idx = int(cmd.split()[1])
            global MAX_SPEED
            MAX_SPEED = SPEED_PRESETS.get(idx, 13043)
            print(f"SPEED_OK:{MAX_SPEED}")
        except Exception:
            print("ERR:SPEED")

    # ── Queries ───────────────────────────────────────
    elif cmd == "POS?":
        print(f"POS:{position['x']:.4f},{position['y']:.4f}")

    elif cmd == "STATUS?":
        print(f"STATUS:OK,X:{position['x']:.4f},Y:{position['y']:.4f},SPEED:{MAX_SPEED}")

    elif cmd == "SWITCHES?":
        print(f"SWITCHES:M1MIN={int(limit_hit(m1_min))},M2MIN={int(limit_hit(m2_min))}")

    elif cmd == "ENC?":
        raw_x = read_angle(enc_cs_x)
        raw_y = read_angle(enc_cs_y)
        err_x = enc_error_mm('x')
        err_y = enc_error_mm('y')
        print(f"ENC:X_RAW={raw_x},Y_RAW={raw_y},"
              f"X_ERR={err_x:.4f},Y_ERR={err_y:.4f},"
              f"X_CAL={int(enc_calibrated['x'])},Y_CAL={int(enc_calibrated['y'])},"
              f"X_DIR={ENC_DIR_X},Y_DIR={ENC_DIR_Y}")

    elif cmd == "ENC_AFH?":
        # Return current angle-from-home counts for both axes.
        # The PC stores these after each successful 'Go To Device' as the reference
        # for future MOVETO_REF corrections, bypassing the ±0.25 mm step-count wrap issue.
        afh_x = enc_angle_from_home('x')
        afh_y = enc_angle_from_home('y')
        print(f"ENC_AFH:{afh_x},{afh_y}")

    elif cmd == "ENC_ABS?":
        # Return absolute encoder position in mm for both axes.
        # Uses step count for revolution number + encoder sub-revolution for precision.
        # Accurate to encoder resolution as long as step-count error < ±0.25 mm.
        # The PC uses this during scanning to anchor pad coordinates to true physical
        # position instead of step-count position, eliminating drift accumulation.
        ax = enc_abs_mm('x')
        ay = enc_abs_mm('y')
        if ax is None: ax = -1.0
        if ay is None: ay = -1.0
        print(f"ENC_ABS:{ax:.6f},{ay:.6f}")

    # ── PROBE relay — forward to slave Pico via UART ────────────────────
    elif cmd.startswith("PROBE "):
        slave_cmd = cmd[6:]   # strip "PROBE " prefix
        probe_uart.write((slave_cmd + "\n").encode())
        # Collect lines from slave and forward to USB until PROBE_POS: or ERR: received.
        # HOME ALL sends PROBE_HOMED:* lines before the final PROBE_POS: — forward all.
        start = time.ticks_ms()
        pbuf  = b""
        done  = False
        while not done and time.ticks_diff(time.ticks_ms(), start) < 15000:
            chunk = probe_uart.read(64)
            if chunk:
                pbuf += chunk
            while b"\n" in pbuf:
                line_b, pbuf = pbuf.split(b"\n", 1)
                resp = line_b.decode(errors="ignore").strip()
                if resp:
                    print(resp)   # forward to USB / laptop
                    if resp.startswith("PROBE_POS:") or resp.startswith("ERR:"):
                        done = True
                        break
            if not done:
                time.sleep_ms(1)
        if not done:
            print("ERR:PROBE_TIMEOUT")

    else:
        print("ERR:UNKNOWN")

# ── Main loop ──────────────────────────────────────────
print("READY")
buf = ""
while True:
    if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
        ch = sys.stdin.read(1)
        if ch == '\n':
            handle(buf)
            buf = ""
        else:
            buf += ch
