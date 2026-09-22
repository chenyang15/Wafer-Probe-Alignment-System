"""
probe_pico_main.py  — deploy as main.py on the probe slave Pico 2W
Microprobe motion controller: left probe (L) and right probe (R),
each with a traverse axis and a Z (vertical) axis.

Wiring
------
  UART from master Pico:  GP16 = TX, GP17 = RX  (UART0)
  Cross-connection: master GP16 → slave GP17, slave GP16 → master GP17

Axes
----
  T_L  left traverse   home = bottom of camera view   DIR GP2  STEP GP3  EN GP4   HOME GP21
  Z_L  left Z          home = top  (retracted/safe)   DIR GP5  STEP GP6  EN GP7   HOME GP20
  T_R  right traverse  home = right of camera view    DIR GP8  STEP GP9  EN GP10  HOME GP19
  Z_R  right Z         home = top  (retracted/safe)   DIR GP11 STEP GP12 EN GP13  HOME GP18

  All limit switches: NC switch to GND, PULL_UP, active HIGH (reads 1 when triggered).
  One switch per axis, at the home position only.

Direction calibration
---------------------
  DIR_TOWARD_HOME[axis] = the DIR pin value that drives the motor TOWARD its home switch.
  Default: 0 for all axes.  If a probe moves AWAY from its switch when HOME is issued,
  flip that axis from 0 → 1.

Commands (plain text, newline-terminated, received on UART)
-----------------------------------------------------------
  MOVE <axis> <mm>    relative move; returns PROBE_POS:t_l,z_l,t_r,z_r
  HOME ALL            home all four axes in sequence; returns PROBE_HOMED:* then PROBE_POS:
  HOME <axis>         home single axis; returns PROBE_HOMED:<axis> then PROBE_POS:
  POS?                returns PROBE_POS:t_l,z_l,t_r,z_r
  SPEED <idx>         accepted but ignored — fixed slow speed only
"""

from machine import Pin, UART
import time

# ── UART to master Pico ────────────────────────────────────────────────────────
uart = UART(0, baudrate=115200, tx=Pin(16), rx=Pin(17), timeout=50)

# ── Motion constants ───────────────────────────────────────────────────────────
STEPS_PER_MM  = 6400     # 16× microstepping, 0.5 mm/rev, same as master stage
MOVE_SPEED_HZ = 3000     # steps/sec — slow and safe for probe contact approach
HALF_US       = 500_000 // MOVE_SPEED_HZ   # µs per half-step period  (≈167 µs)

# ── Direction calibration ──────────────────────────────────────────────────────
# Set to the DIR pin logic level that drives the probe TOWARD its home switch.
# Flip any entry from 0→1 (or 1→0) if that axis moves the wrong way on HOME.
DIR_TOWARD_HOME = {
    'T_L': 0,   # verified: dir=1 moves toward home (bottom of camera view)
    'Z_L': 1,   # verified: dir=1 moves toward home (top / retracted)
    'T_R': 1,   # verified: dir=1 moves toward home (right of camera view)
    'Z_R': 1,   # verified: dir=1 moves toward home (top / retracted)
}

# ── Pin definitions ────────────────────────────────────────────────────────────
#                  (dir_pin,            step_pin,           en_pin,             home_pin)
try:
    _AXIS = {
        'T_L': (Pin(2,  Pin.OUT), Pin(3,  Pin.OUT), Pin(4,  Pin.OUT), Pin(21, Pin.IN, Pin.PULL_UP)),
        'Z_L': (Pin(5,  Pin.OUT), Pin(6,  Pin.OUT), Pin(7,  Pin.OUT), Pin(20, Pin.IN, Pin.PULL_UP)),
        'T_R': (Pin(8,  Pin.OUT), Pin(9,  Pin.OUT), Pin(10, Pin.OUT), Pin(19, Pin.IN, Pin.PULL_UP)),
        'Z_R': (Pin(11, Pin.OUT), Pin(12, Pin.OUT), Pin(13, Pin.OUT), Pin(18, Pin.IN, Pin.PULL_UP)),
    }
    # Enable all motors (EN active LOW on TMC2208)
    for _pins in _AXIS.values():
        _pins[2].low()
    uart.write(b"PINS_OK\n")
except Exception as e:
    uart.write(("CRASH:" + str(e) + "\n").encode())

# Tracked positions in mm (0 = at home / retracted)
_pos = {'T_L': 0.0, 'Z_L': 0.0, 'T_R': 0.0, 'Z_R': 0.0}

# ── Motion primitives ──────────────────────────────────────────────────────────

def _step(axis, steps):
    """
    Move axis by `steps` (signed: positive = away from home, negative = toward home).
    Only stops early on limit-switch trigger for toward-home moves (prevents grinding).
    Returns number of steps actually taken (always positive).
    """
    if steps == 0:
        return 0
    dir_pin, step_pin, _en, home_pin = _AXIS[axis]
    toward_home = steps < 0
    dir_val = DIR_TOWARD_HOME[axis] if toward_home else (1 - DIR_TOWARD_HOME[axis])
    dir_pin.value(dir_val)
    time.sleep_us(5)   # direction setup time

    # Block move toward home if already at the switch
    if toward_home and home_pin.value():
        return 0
    n = abs(steps)
    done = 0
    for _ in range(n):
        if toward_home and home_pin.value():
            break
        step_pin.value(1); time.sleep_us(HALF_US)
        step_pin.value(0); time.sleep_us(HALF_US)
        done += 1
    return done


def move_axis(axis, mm):
    """Relative move in mm. Positive = away from home. Updates tracked position."""
    steps = int(mm * STEPS_PER_MM)
    if steps == 0:
        return
    done  = _step(axis, steps)
    sign  = 1 if mm >= 0 else -1
    _pos[axis] = round(_pos[axis] + sign * done / STEPS_PER_MM, 6)


def home_axis(axis):
    """Drive axis toward home switch until triggered, then zero its position."""
    dir_pin, step_pin, _en, home_pin = _AXIS[axis]
    dir_pin.value(DIR_TOWARD_HOME[axis])
    time.sleep_us(5)
    while not home_pin.value():
        step_pin.value(1); time.sleep_us(HALF_US)
        step_pin.value(0); time.sleep_us(HALF_US)
    _pos[axis] = 0.0


def pos_line():
    return "PROBE_POS:{:.4f},{:.4f},{:.4f},{:.4f}".format(
        _pos['T_L'], _pos['Z_L'], _pos['T_R'], _pos['Z_R'])


def send(msg):
    uart.write((msg + "\n").encode())

# ── Command loop ───────────────────────────────────────────────────────────────
send("PROBE_READY")
_buf = b""
_beat = 0
_last_beat = time.ticks_ms()

while True:
    if time.ticks_diff(time.ticks_ms(), _last_beat) > 2000:
        send("BEAT:{}".format(_beat))
        _beat += 1
        _last_beat = time.ticks_ms()

    chunk = uart.read(64)
    if chunk:
        _buf += chunk

    while b"\n" in _buf:
        line_b, _buf = _buf.split(b"\n", 1)
        cmd = line_b.decode(errors="ignore").strip()
        if not cmd:
            continue
        try:
            parts = cmd.split()
            verb  = parts[0].upper() if parts else ""

            # MOVE <axis> <mm> ─────────────────────────────────────────────────────
            if verb == "MOVE" and len(parts) == 3:
            axis = parts[1].upper()
            if axis not in _pos:
                send("ERR:AXIS"); continue
            try:
                move_axis(axis, float(parts[2]))
                send(pos_line())
            except Exception as e:
                send("ERR:MOVE:{}".format(e))

        # HOME [axis|ALL] ──────────────────────────────────────────────────────
        elif verb == "HOME":
            target = parts[1].upper() if len(parts) > 1 else "ALL"
            axes   = list(_pos.keys()) if target == "ALL" else ([target] if target in _pos else [])
            if not axes:
                send("ERR:AXIS"); continue
            for ax in axes:
                home_axis(ax)
                send("PROBE_HOMED:{}".format(ax))
            send(pos_line())

        # POS? ─────────────────────────────────────────────────────────────────
        elif verb == "POS?":
            send(pos_line())

        # SPEED <idx>  (accepted, ignored — fixed slow speed) ─────────────────
        elif verb == "SPEED":
            send(pos_line())

            else:
                send("ERR:UNKNOWN")
        except Exception as e:
            send("ERR:CRASH:" + str(e))
