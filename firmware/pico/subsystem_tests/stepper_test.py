from machine import Pin
import time

# ── Motor 1 pins ──
m1_dir  = Pin(2, Pin.OUT)
m1_step = Pin(3, Pin.OUT)
m1_en   = Pin(4, Pin.OUT)

# ── Motor 2 pins ──
m2_dir  = Pin(5, Pin.OUT)
m2_step = Pin(6, Pin.OUT)
m2_en   = Pin(7, Pin.OUT)

# ── ENUM ──
MICROSTEPS = 16
STEPS_PER_REV = 200 * MICROSTEPS


def move(step_pin, dir_pin, direction, steps, delay_ms=0.002):
    dir_pin.value(direction)  # 0 or 1 = CW or CCW
    for _ in range(steps):
        step_pin.high()
        time.sleep(delay_ms)
        step_pin.low()
        time.sleep(delay_ms)

# ── Enable both motors (LOW = enabled for TMC) ──
m1_en.low()
m2_en.low()

time.sleep(0.5)  # let drivers wake up

print("Moving Motor 1 forward...")
move(m1_step, m1_dir, direction=0, steps=STEPS_PER_REV)
time.sleep(0.5)

print("Moving Motor 1 backward...")
move(m1_step, m1_dir, direction=1, steps=STEPS_PER_REV)
time.sleep(0.5)

print("Moving Motor 2 forward...")
move(m2_step, m2_dir, direction=0, steps=STEPS_PER_REV)
time.sleep(0.5)

print("Moving Motor 2 backward...")
move(m2_step, m2_dir, direction=1, steps=STEPS_PER_REV)

print("Done!")