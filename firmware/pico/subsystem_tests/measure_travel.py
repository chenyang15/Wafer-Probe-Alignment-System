# measure_travel.py
# Flash to Pico as main.py, open Thonny serial monitor, read output.
# Homes each axis to MAX switch, then drives to MIN switch,
# records steps taken, prints travel in mm.

import select
import sys
import time
from machine import Pin
import rp2

MICROSTEPS    = 16
STEPS_PER_REV = 200 * MICROSTEPS
MM_PER_REV    = 0.5
STEPS_PER_MM  = STEPS_PER_REV / MM_PER_REV   # 6400

MIN_SPEED  = 500
MEAS_SPEED = 8000    # steady speed for measurement (no need for max)
ACCEL      = 40000
PIO_CYC    = 23

M1_DIR=2; M1_STEP=3; M1_EN=4; M1_MIN=18; M1_MAX=19
M2_DIR=5; M2_STEP=6; M2_EN=7; M2_MIN=20; M2_MAX=21

m1_dir=Pin(M1_DIR,Pin.OUT); m1_en=Pin(M1_EN,Pin.OUT)
m1_min=Pin(M1_MIN,Pin.IN,Pin.PULL_UP)
m1_max=Pin(M1_MAX,Pin.IN,Pin.PULL_UP)
m2_dir=Pin(M2_DIR,Pin.OUT); m2_en=Pin(M2_EN,Pin.OUT)
m2_min=Pin(M2_MIN,Pin.IN,Pin.PULL_UP)
m2_max=Pin(M2_MAX,Pin.IN,Pin.PULL_UP)
m1_en.low(); m2_en.low()

def limit_hit(pin): return pin.value() == 1
def pio_freq(s): return max(2000, min(60000000, int(s * PIO_CYC)))

@rp2.asm_pio(set_init=rp2.PIO.OUT_LOW)
def step_pulse():
    pull(block)
    mov(x, osr)
    label("loop")
    set(pins, 1) [10]
    set(pins, 0) [10]
    jmp(x_dec, "loop")

def drive_to_switch(motor, direction, stop_pin, chunk=1000):
    """Drive motor in direction until stop_pin fires. Returns steps taken."""
    sid   = 0 if motor == 1 else 1
    sp    = M1_STEP if motor == 1 else M2_STEP
    dp    = m1_dir if motor == 1 else m2_dir

    dp.value(direction)
    time.sleep(0.001)

    cur = MEAS_SPEED
    accel_s = int((cur**2 - MIN_SPEED**2) / (2 * ACCEL))
    done = 0

    def run_chunk(steps, speed):
        sm = rp2.StateMachine(sid, step_pulse,
                              freq=pio_freq(speed), set_base=Pin(sp))
        sm.active(1)
        sm.put(steps - 1)
        time.sleep(steps / speed + 0.002)
        sm.active(0)

    # Accel
    while done < accel_s:
        if limit_hit(stop_pin): return done
        ch  = min(chunk, accel_s - done)
        prog = ((done + ch/2) / accel_s) ** 3
        run_chunk(ch, max(MIN_SPEED, MIN_SPEED + (cur - MIN_SPEED) * prog))
        done += ch

    # Cruise until switch fires
    while True:
        if limit_hit(stop_pin): return done
        run_chunk(chunk, cur)
        done += chunk

def measure_axis(motor, name):
    print(f"\n── {name} axis ──────────────────────")

    # Step 1: home to MAX
    print(f"Homing {name} to MAX switch...")
    if motor == 1:
        # X: direction=1 → X- → m1_max
        drive_to_switch(motor, direction=1, stop_pin=m1_max)
    else:
        # Y: direction=0 → Y+ → m2_max (motor flipped)
        drive_to_switch(motor, direction=0, stop_pin=m2_max)
    time.sleep(0.3)
    print(f"{name} at MAX (home). Now driving to MIN...")

    # Step 2: drive to MIN, count steps
    if motor == 1:
        # X: direction=0 → X+ → m1_min
        steps = drive_to_switch(motor, direction=0, stop_pin=m1_min)
    else:
        # Y: direction=1 → Y- → m2_min
        steps = drive_to_switch(motor, direction=1, stop_pin=m2_min)

    travel_mm = steps / STEPS_PER_MM
    print(f"{name} travel: {steps} steps = {travel_mm:.3f} mm")
    return travel_mm

print("=== Travel Range Measurement ===")
print("Measuring X axis...")
x_mm = measure_axis(1, "X")
time.sleep(0.5)
print("Measuring Y axis...")
y_mm = measure_axis(2, "Y")

print(f"\n=== RESULT ===")
print(f"X travel: {x_mm:.2f} mm")
print(f"Y travel: {y_mm:.2f} mm")
print(f"Copy these values into the UI config.")
print("DONE")
