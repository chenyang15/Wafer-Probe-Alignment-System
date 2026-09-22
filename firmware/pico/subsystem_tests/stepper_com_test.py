from machine import Pin
import time

# ── Constants ──────────────────────────────────────
MICROSTEPS       = 16
STEPS_PER_REV    = 200 * MICROSTEPS   # 3200
MM_PER_REV       = 0.5
STEPS_PER_MM     = STEPS_PER_REV / MM_PER_REV  # 6400 steps/mm
DEFAULT_DELAY    = 0.0001  # seconds between step pulses

# ── Motor 1 ────────────────────────────────────────
m1_dir  = Pin(2,  Pin.OUT)
m1_step = Pin(3,  Pin.OUT)
m1_en   = Pin(4,  Pin.OUT)
m1_min  = Pin(18, Pin.IN, Pin.PULL_UP)  # NC + GND = PULL_UP
m1_max  = Pin(19, Pin.IN, Pin.PULL_UP)

# ── Motor 2 ────────────────────────────────────────
m2_dir  = Pin(5,  Pin.OUT)
m2_step = Pin(6,  Pin.OUT)
m2_en   = Pin(7,  Pin.OUT)
m2_min  = Pin(20, Pin.IN, Pin.PULL_UP)
m2_max  = Pin(21, Pin.IN, Pin.PULL_UP)

# ── Position tracking ──────────────────────────────
position = {'x': 0.0, 'y': 0.0}  # in mm

# ── Enable motors ──────────────────────────────────
m1_en.low()
m2_en.low()

# ── Limit switch check ─────────────────────────────
def limit_hit(pin):
    # NC switch wired to GND: normally reads 0, opens to 1 when triggered
    return pin.value() == 1

# ── Core move function ─────────────────────────────
def move_steps(motor, steps, direction, delay=DEFAULT_DELAY):
    """
    motor     : 1 or 2
    steps     : number of microsteps
    direction : 0 or 1
    """
    if motor == 1:
        step_pin = m1_step
        dir_pin  = m1_dir
        min_sw   = m1_min
        max_sw   = m1_max
        axis     = 'x'
    else:
        step_pin = m2_step
        dir_pin  = m2_dir
        min_sw   = m2_min
        max_sw   = m2_max
        axis     = 'y'

    dir_pin.value(direction)

    for _ in range(steps):
        # check limits before each step
        if direction == 0 and limit_hit(min_sw):
            print(f"LIMIT:MIN_{axis.upper()}")
            return
        if direction == 1 and limit_hit(max_sw):
            print(f"LIMIT:MAX_{axis.upper()}")
            return

        step_pin.high()
        time.sleep(delay)
        step_pin.low()
        time.sleep(delay)

    # update position
    dist_mm = steps / STEPS_PER_MM
    if direction == 0:
        position[axis] -= dist_mm
    else:
        position[axis] += dist_mm

# ── Move in mm ─────────────────────────────────────
def move_mm(motor, mm, delay=DEFAULT_DELAY):
    steps = int(abs(mm) * STEPS_PER_MM)
    direction = 1 if mm > 0 else 0
    move_steps(motor, steps, direction, delay)

# ── Homing ─────────────────────────────────────────
def home(motor):
    axis = 'x' if motor == 1 else 'y'
    print(f"HOMING:{axis.upper()}")

    # move toward min until limit hit
    if motor == 1:
        step_pin, dir_pin, min_sw = m1_step, m1_dir, m1_min
    else:
        step_pin, dir_pin, min_sw = m2_step, m2_dir, m2_min

    dir_pin.value(0)  # toward min
    while not limit_hit(min_sw):
        step_pin.high()
        time.sleep(0.0002)
        step_pin.low()
        time.sleep(0.0002)

    position[axis] = 0.0
    print(f"HOMED:{axis.upper()}")

# ── USB Serial command handler ──────────────────────
def handle_command(cmd):
    cmd = cmd.strip()

    # MOVE X 1.5  or  MOVE Y -0.5
    if cmd.startswith("MOVE"):
        parts = cmd.split()
        axis  = parts[1].upper()
        mm    = float(parts[2])
        motor = 1 if axis == 'X' else 2
        move_mm(motor, mm)
        print(f"POS:{position['x']:.4f},{position['y']:.4f}")

    # HOME X  or  HOME Y  or  HOME ALL
    elif cmd.startswith("HOME"):
        parts = cmd.split()
        target = parts[1].upper() if len(parts) > 1 else "ALL"
        if target in ("X", "ALL"):
            home(1)
        if target in ("Y", "ALL"):
            home(2)
        print(f"POS:{position['x']:.4f},{position['y']:.4f}")

    # POS? — query current position
    elif cmd == "POS?":
        print(f"POS:{position['x']:.4f},{position['y']:.4f}")

    # STATUS?
    elif cmd == "STATUS?":
        print(f"STATUS:OK,X:{position['x']:.4f},Y:{position['y']:.4f}")

    else:
        print("ERR:UNKNOWN_CMD")

# ── Main loop ──────────────────────────────────────
print("READY")
import sys
buf = ""
while True:
    if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
        ch = sys.stdin.read(1)
        if ch == '\n':
            handle_command(buf)
            buf = ""
        else:
            buf += ch