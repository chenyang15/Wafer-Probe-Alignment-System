"""
probe_standalone.py — deploy as main.py on the probe slave Pico
Direct USB mode: connect this Pico to the PC directly (no master relay).

Run waferstage_ui.py normally — when it sends "PROBE MOVE T_L 1.0000" etc.,
this firmware strips the "PROBE " prefix and handles it locally.
All pico_controller.probe_* methods work without modification.
"""

import select
import sys
import time
from machine import Pin

# ── Motion constants ───────────────────────────────────────────────────────────
STEPS_PER_MM  = 6400
MOVE_SPEED_HZ = 3000
HALF_US       = 500_000 // MOVE_SPEED_HZ   # µs per half-step  (≈167 µs)

# ── Direction calibration ──────────────────────────────────────────────────────
DIR_TOWARD_HOME = {
    'T_L': 1,
    'Z_L': 1,
    'T_R': 1,
    'Z_R': 1,
}

# ── Pin definitions ────────────────────────────────────────────────────────────
_AXIS = {
    'T_L': (Pin(2,  Pin.OUT), Pin(3,  Pin.OUT), Pin(4,  Pin.OUT), Pin(21, Pin.IN, Pin.PULL_UP)),
    'Z_L': (Pin(5,  Pin.OUT), Pin(6,  Pin.OUT), Pin(7,  Pin.OUT), Pin(20, Pin.IN, Pin.PULL_UP)),
    'T_R': (Pin(8,  Pin.OUT), Pin(9,  Pin.OUT), Pin(10, Pin.OUT), Pin(19, Pin.IN, Pin.PULL_UP)),
    'Z_R': (Pin(11, Pin.OUT), Pin(12, Pin.OUT), Pin(13, Pin.OUT), Pin(18, Pin.IN, Pin.PULL_UP)),
}

for _pins in _AXIS.values():
    _pins[2].low()   # EN active LOW — enable all drivers on startup

_pos = {'T_L': 0.0, 'Z_L': 0.0, 'T_R': 0.0, 'Z_R': 0.0}

# ── Motion primitives ──────────────────────────────────────────────────────────

def _step(axis, steps):
    if steps == 0:
        return 0
    dir_pin, step_pin, _en, home_pin = _AXIS[axis]
    toward_home = steps < 0
    dir_val = DIR_TOWARD_HOME[axis] if toward_home else (1 - DIR_TOWARD_HOME[axis])
    dir_pin.value(dir_val)
    time.sleep_us(5)
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
    steps = int(mm * STEPS_PER_MM)
    if steps == 0:
        return
    done = _step(axis, steps)
    sign = 1 if mm >= 0 else -1
    _pos[axis] = round(_pos[axis] + sign * done / STEPS_PER_MM, 6)

def home_axis(axis):
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

# ── Command handler ────────────────────────────────────────────────────────────

def handle(cmd):
    # Strip optional "PROBE " prefix so pico_controller.probe_* works directly
    if cmd.upper().startswith("PROBE "):
        cmd = cmd[6:]

    parts = cmd.split()
    if not parts:
        return
    verb = parts[0].upper()

    if verb == "MOVE" and len(parts) == 3:
        axis = parts[1].upper()
        if axis not in _pos:
            print("ERR:AXIS"); return
        try:
            move_axis(axis, float(parts[2]))
            print(pos_line())
        except Exception as e:
            print("ERR:MOVE:{}".format(e))

    elif verb == "HOME":
        target = parts[1].upper() if len(parts) > 1 else "ALL"
        axes = list(_pos.keys()) if target == "ALL" else ([target] if target in _pos else [])
        if not axes:
            print("ERR:AXIS"); return
        for ax in axes:
            home_axis(ax)
            print("PROBE_HOMED:{}".format(ax))
        print(pos_line())

    elif verb == "POS?":
        print(pos_line())

    elif verb == "SPEED":
        print(pos_line())   # accepted, ignored

    elif verb == "SWITCHES?":
        # pico_controller.connect() sends this — respond so it doesn't hang
        print("SWITCHES:T_L={},Z_L={},T_R={},Z_R={}".format(
            _AXIS['T_L'][3].value(), _AXIS['Z_L'][3].value(),
            _AXIS['T_R'][3].value(), _AXIS['Z_R'][3].value()))

    else:
        print("ERR:UNKNOWN")

# ── Main loop ──────────────────────────────────────────────────────────────────
print("READY")
buf = ""
while True:
    if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
        ch = sys.stdin.read(1)
        if ch == '\n':
            handle(buf.strip())
            buf = ""
        else:
            buf += ch
