from machine import UART, Pin
import time

uart = UART(0, baudrate=115200, tx=Pin(16), rx=Pin(17), timeout=50)

beat = 0
last = time.ticks_ms()
while True:
    if time.ticks_diff(time.ticks_ms(), last) > 500:
        uart.write("BEAT:{}\n".format(beat).encode())
        beat += 1
        last = time.ticks_ms()
