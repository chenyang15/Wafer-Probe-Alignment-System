from machine import Pin
import time
import rp2

M2_DIR = Pin(5, Pin.OUT)
M2_STEP = 6
M2_EN = Pin(7, Pin.OUT)
M2_EN.low()

@rp2.asm_pio(set_init=rp2.PIO.OUT_LOW)
def step_pulse():
    pull(block)
    mov(x, osr)
    label("loop")
    set(pins, 1) [10]
    set(pins, 0) [10]
    jmp(x_dec, "loop")

M2_DIR.value(0)  # try direction 0 first
sm = rp2.StateMachine(1, step_pulse, freq=100000, set_base=Pin(M2_STEP))
sm.active(1)
sm.put(3199)  # 0.5mm
time.sleep(0.5)
sm.active(0)