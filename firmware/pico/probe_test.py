"""
probe_test.py — upload as main.py on the slave Pico for hardware testing
Prints limit switch states and lets you jog each motor from the REPL.

Usage after pressing Stop (>>>) in Thonny:
    switches()           # print all 4 switch states
    jog('T_L', 1)        # move left traverse AWAY from home (dir=1)
    jog('T_L', 0)        # move left traverse TOWARD home  (dir=0)
    jog('Z_L', 1)        # etc.
    jog('Z_R', 0)
    home('T_L')          # drive T_L until limit switch triggers
    home_all()           # home all 4 axes
"""

from machine import Pin
import time

# ── Pins ───────────────────────────────────────────────────────────────────────
AXES = {
    'T_L': {'dir': Pin(2,  Pin.OUT), 'step': Pin(3,  Pin.OUT),
            'en':  Pin(4,  Pin.OUT), 'home': Pin(21, Pin.IN, Pin.PULL_UP)},
    'Z_L': {'dir': Pin(5,  Pin.OUT), 'step': Pin(6,  Pin.OUT),
            'en':  Pin(7,  Pin.OUT), 'home': Pin(20, Pin.IN, Pin.PULL_UP)},
    'T_R': {'dir': Pin(8,  Pin.OUT), 'step': Pin(9,  Pin.OUT),
            'en':  Pin(10, Pin.OUT), 'home': Pin(19, Pin.IN, Pin.PULL_UP)},
    'Z_R': {'dir': Pin(11, Pin.OUT), 'step': Pin(12, Pin.OUT),
            'en':  Pin(13, Pin.OUT), 'home': Pin(18, Pin.IN, Pin.PULL_UP)},
}

SPEED_HZ  = 2000   # steps/sec — slow enough to be safe
HALF_US   = 500_000 // SPEED_HZ

# Enable all motors on startup
for a in AXES.values():
    a['en'].low()

# ── Functions ──────────────────────────────────────────────────────────────────

def switches():
    """Print the current state of all 4 limit switches."""
    for name, a in AXES.items():
        state = a['home'].value()
        label = "TRIGGERED (at home)" if state else "open"
        print(f"  {name} home switch: {state}  {label}")

def jog(axis, direction, steps=6000):
    """
    Move axis by `steps` in given direction.
    direction=1 → away from home
    direction=0 → toward home (stops early if switch triggers)
    Default 640 steps = 0.1 mm.
    """
    if axis not in AXES:
        print(f"Unknown axis '{axis}'. Choose from: {list(AXES.keys())}")
        return
    a = AXES[axis]
    a['dir'].value(direction)
    time.sleep_us(10)
    home_at_start = a['home'].value()
    done = 0
    for _ in range(steps):
        if direction == 0 and (not home_at_start) and a['home'].value():
            print(f"  {axis}: limit switch triggered after {done} steps")
            break
        a['step'].value(1); time.sleep_us(HALF_US)
        a['step'].value(0); time.sleep_us(HALF_US)
        done += 1
    print(f"  {axis}: moved {done} steps  dir={direction}  switch={a['home'].value()}")

def home(axis):
    """Drive axis toward home until limit switch triggers."""
    if axis not in AXES:
        print(f"Unknown axis '{axis}'")
        return
    a = AXES[axis]
    if a['home'].value():
        print(f"  {axis}: already at home switch")
        return
    a['dir'].value(1)   # verified: direction 1 = toward home on all axes
    time.sleep_us(10)
    count = 0
    while not a['home'].value():
        a['step'].value(1); time.sleep_us(HALF_US)
        a['step'].value(0); time.sleep_us(HALF_US)
        count += 1
        if count > 200 * 6400:   # 200 mm safety limit
            print(f"  {axis}: safety limit reached — switch never triggered")
            return
    print(f"  {axis}: homed after {count} steps")

def home_all():
    """Home all 4 axes one by one."""
    for name in AXES:
        print(f"Homing {name}...")
        home(name)

# ── Auto-run on startup ────────────────────────────────────────────────────────
print("\n=== Probe test ready ===")
print("Limit switch states on startup:")
switches()
print()
print("Commands available in REPL:")
print("  switches()           - read all limit switches")
print("  jog('T_L', 1)        - move left traverse away from home")
print("  jog('T_L', 0)        - move left traverse toward home")
print("  jog('Z_L', 1, 320)   - move left Z away from home, 320 steps")
print("  home('T_R')          - home right traverse")
print("  home_all()           - home all 4 axes")
print()
print("Axes: T_L  Z_L  T_R  Z_R")
print("dir=1 = away from home,  dir=0 = toward home (flip DIR_TOWARD_HOME in main firmware if wrong)")
