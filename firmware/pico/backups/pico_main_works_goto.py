import select
import sys
import _thread
import time
from machine import Pin
import rp2

# ── Constants ──────────────────────────────────────────
MICROSTEPS    = 16
STEPS_PER_REV = 200 * MICROSTEPS
MM_PER_REV    = 0.5
STEPS_PER_MM  = STEPS_PER_REV / MM_PER_REV  # 6400 steps/mm

MIN_SPEED  = 500     # steps/sec
MAX_SPEED  = 13043   # steps/sec (100% = 300kHz PIO / 23 cycles)
ACCEL      = 40000   # steps/sec²
HOME_SPEED = 13043   # always home at 100%

SPEED_PRESETS = {
    0: 7826,   # 60%
    1: 10435,  # 80%
    2: 13043,  # 100%
    3: 13695,  # 105%
    4: 14348,  # 110%
}

# ── Pins ───────────────────────────────────────────────
M1_DIR=2; M1_STEP=3; M1_EN=4; M1_MIN=18; M1_MAX=19
M2_DIR=5; M2_STEP=6; M2_EN=7; M2_MIN=20; M2_MAX=21

m1_dir=Pin(M1_DIR,Pin.OUT); m1_en=Pin(M1_EN,Pin.OUT)
m1_min=Pin(M1_MIN,Pin.IN,Pin.PULL_UP)
m1_max=Pin(M1_MAX,Pin.IN,Pin.PULL_UP)
m2_dir=Pin(M2_DIR,Pin.OUT); m2_en=Pin(M2_EN,Pin.OUT)
m2_min=Pin(M2_MIN,Pin.IN,Pin.PULL_UP)
m2_max=Pin(M2_MAX,Pin.IN,Pin.PULL_UP)
m1_en.low(); m2_en.low()

# ── PIO step pulse ─────────────────────────────────────
PIO_CYC = 23  # cycles per step pulse

@rp2.asm_pio(set_init=rp2.PIO.OUT_LOW)
def step_pulse():
    pull(block)
    mov(x, osr)
    label("loop")
    set(pins, 1) [10]
    set(pins, 0) [10]
    jmp(x_dec, "loop")

def pio_freq(steps_per_sec):
    # Minimum PIO freq must be above hardware limit (~2kHz)
    # MIN_SPEED * PIO_CYC = 500 * 23 = 11500 — safely above minimum
    return max(MIN_SPEED * PIO_CYC, min(60000000, int(steps_per_sec * PIO_CYC)))

# ── State ──────────────────────────────────────────────
position = {'x': 0.0, 'y': 0.0}

# y_req: how Core 0 sends work to Core 1 (Y axis)
y_req = {'steps': 0, 'direction': 0, 'speed': 0,
         'stop_pin': None, 'active': False, 'done': True}

def limit_hit(pin):
    return pin.value() == 1

# ── Accelerated move ───────────────────────────────────
def move_accel(motor, total_steps, direction, speed=0, stop_pin=None):
    """Move motor by total_steps in direction.
    speed: override MAX_SPEED if > 0 (used for homing)
    stop_pin: stop immediately when this pin fires (used for homing)
    Returns actual steps taken.
    """
    if total_steps <= 0:
        return 0

    if motor == 1:
        dp=m1_dir; sp=M1_STEP; sid=0
        lim_fwd=m1_min; lim_bwd=m1_max
        dp.value(direction)
    else:
        dp=m2_dir; sp=M2_STEP; sid=1
        lim_fwd=m2_max; lim_bwd=m2_min
        dp.value(direction)  # direction=1=pin HIGH=Y-, direction=0=pin LOW=Y+
    time.sleep(0.001)

    cur_max = speed if speed > 0 else MAX_SPEED

    # Chunk size: steps per SM burst
    if stop_pin is not None:
        CHUNK = 1000   # large chunks for homing = quieter
    elif total_steps <= 64:
        CHUNK = 1
    elif total_steps <= 640:
        CHUNK = 5
    else:
        CHUNK = 50

    accel_s = int((cur_max**2 - MIN_SPEED**2) / (2 * ACCEL))
    accel_s = max(1, min(accel_s, total_steps // 2))
    decel_s = accel_s
    cruise_s = total_steps - accel_s - decel_s
    done = 0

    def should_stop():
        if stop_pin is not None:
            return limit_hit(stop_pin)
        # Only stop if the relevant switch is active AND wasn't already
        # active when the move started (so we can move away from a switch)
        if direction == 0:
            return limit_hit(lim_fwd) and not lim_fwd_at_start
        return limit_hit(lim_bwd) and not lim_bwd_at_start

    # Record switch states at move start
    lim_fwd_at_start = limit_hit(lim_fwd)
    lim_bwd_at_start = limit_hit(lim_bwd)

    def run_chunk(steps, spd):
        sm = rp2.StateMachine(sid, step_pulse,
                              freq=pio_freq(spd), set_base=Pin(sp))
        sm.active(1)
        sm.put(steps - 1)
        time.sleep(steps / spd + 0.0005)
        sm.active(0)

    while done < accel_s:
        if should_stop(): return done
        ch = min(CHUNK, accel_s - done)
        prog = ((done + ch/2) / accel_s) ** 3
        spd = MIN_SPEED + (cur_max - MIN_SPEED) * prog
        run_chunk(ch, max(MIN_SPEED, spd))
        done += ch

    while done < accel_s + cruise_s:
        if should_stop(): return done
        ch = min(CHUNK, accel_s + cruise_s - done)
        run_chunk(ch, cur_max)
        done += ch

    while done < total_steps:
        if should_stop(): return done
        ch = min(CHUNK, total_steps - done)
        dd = done - accel_s - cruise_s
        prog = 1 - (1 - (dd + ch/2) / max(1, decel_s)) ** 3
        spd = MIN_SPEED + (cur_max - MIN_SPEED) * (1 - prog)
        run_chunk(ch, max(MIN_SPEED, spd))
        done += ch

    return done

# ── Position tracking ──────────────────────────────────
def update_position(axis, steps_taken, mm_requested):
    """Update position. Uses sign of mm_requested for direction."""
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
                # Update position only for regular moves, not homing
                if y_req['stop_pin'] is None:
                    mm = y_req['steps'] / STEPS_PER_MM
                    if y_req['direction'] == 1:
                        mm = -mm
                    update_position('y', steps, mm)
                y_req['active'] = False
                y_req['done']   = True
        except Exception as e:
            print(f"CORE1_ERR:{e}")
            y_req['active'] = False
            y_req['done']   = True
        time.sleep(0.001)

_thread.start_new_thread(y_thread, ())

# ── Move: Core 0 runs X, Core 1 runs Y ─────────────────
def move_axis(motor, mm):
    steps = int(abs(mm) * STEPS_PER_MM)
    if steps == 0:
        return
    if motor == 1:
        # X: direction=1 homes toward m1_max, so positive mm = direction=0 (away from home)
        direction = 0 if mm > 0 else 1
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
    """Home X to m1_max. direction=1 moves toward m1_max."""
    print("HOMING:X")
    move_accel(1, int(200*STEPS_PER_MM), direction=1,
               speed=HOME_SPEED, stop_pin=m1_max)
    position['x'] = 0.0
    print("HOMED:X")

def home_y_on_core1():
    """Start Y homing on Core 1. direction=1 → pin inverted → physical Y+ toward m2_max."""
    y_req['steps']    = int(200 * STEPS_PER_MM)
    y_req['direction']= 0
    y_req['speed']    = HOME_SPEED
    y_req['stop_pin'] = m2_max
    y_req['done']     = False
    y_req['active']   = True

def home_y_direct():
    """Home Y on Core 0 (for HOME Y command only)."""
    print("HOMING:Y")
    move_accel(2, int(200*STEPS_PER_MM), direction=0,
               speed=HOME_SPEED, stop_pin=m2_max)
    position['y'] = 0.0
    print("HOMED:Y")

# ── Command handler ────────────────────────────────────
def handle(cmd):
    cmd = cmd.strip()
    if not cmd:
        return

    if cmd.startswith("MOVE"):
        parts = cmd.split()
        if len(parts) == 4 and parts[1].upper() == "XY":
            # MOVE XY x_mm y_mm — move both axes simultaneously
            x_mm = float(parts[2])
            y_mm = float(parts[3])
            if int(abs(y_mm) * STEPS_PER_MM) > 0:
                # Kick Y on Core 1
                y_steps = int(abs(y_mm) * STEPS_PER_MM)
                y_dir = 0 if y_mm > 0 else 1  # same as move_axis for Y
                y_req['steps']    = y_steps
                y_req['direction']= y_dir
                y_req['speed']    = 0
                y_req['stop_pin'] = None
                y_req['done']     = False
                y_req['active']   = True
            if int(abs(x_mm) * STEPS_PER_MM) > 0:
                # Run X on Core 0 simultaneously
                move_axis(1, x_mm)
            # Wait for Y to finish
            while not y_req['done']:
                time.sleep(0.001)
        elif len(parts) == 3:
            # MOVE X 1.0  or  MOVE Y -0.5
            axis = parts[1].upper()
            mm   = float(parts[2])
            move_axis(1 if axis == 'X' else 2, mm)
        print(f"POS:{position['x']:.4f},{position['y']:.4f}")

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
            # Run X (Core 0) and Y (Core 1) simultaneously
            print("HOMING:Y")
            home_y_on_core1()
            home_x()                         # blocks until X limit fires
            while not y_req['done']:         # wait for Y to finish
                time.sleep(0.001)
            position['y'] = 0.0
            print("HOMED:Y")
            print(f"POS:{position['x']:.4f},{position['y']:.4f}")

    elif cmd.startswith("SPEED"):
        try:
            idx = int(cmd.split()[1])
            global MAX_SPEED
            MAX_SPEED = SPEED_PRESETS.get(idx, 13043)
            print(f"SPEED_OK:{MAX_SPEED}")
        except Exception:
            print("ERR:SPEED")

    elif cmd == "POS?":
        print(f"POS:{position['x']:.4f},{position['y']:.4f}")

    elif cmd == "STATUS?":
        print(f"STATUS:OK,X:{position['x']:.4f},Y:{position['y']:.4f},SPEED:{MAX_SPEED}")

    elif cmd == "SWITCHES?":
        # Report MAX limit switch states — both active means stage is at home
        print(f"SWITCHES:M1MAX={int(limit_hit(m1_max))},M2MAX={int(limit_hit(m2_max))}")

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