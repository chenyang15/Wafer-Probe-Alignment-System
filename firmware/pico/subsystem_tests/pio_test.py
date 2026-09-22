from machine import Pin
import rp2

# enable and set direction
en  = Pin(7, Pin.OUT)
dir = Pin(5, Pin.OUT)
en.low()    # enable driver
dir.value(1)  # set direction

@rp2.asm_pio(set_init=rp2.PIO.OUT_LOW)
def step_pulse():
    pull(block)
    mov(x, osr)
    label("loop")
    set(pins, 1) [10]
    set(pins, 0) [10]
    jmp(x_dec, "loop")

sm1 = rp2.StateMachine(1, step_pulse, freq=300000,
                       set_base=Pin(6))
sm1.active(1)
sm1.put(9599)  # one revolution
print("done")


