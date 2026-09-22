from machine import Pin
import time

m1_min = Pin(18, Pin.IN, Pin.PULL_UP)
m1_max = Pin(19, Pin.IN, Pin.PULL_UP)
m2_min = Pin(20, Pin.IN, Pin.PULL_UP)
m2_max = Pin(21, Pin.IN, Pin.PULL_UP)

while True:
    print(f"M1_MIN:{m1_min.value()}  M1_MAX:{m1_max.value()}  M2_MIN:{m2_min.value()}  M2_MAX:{m2_max.value()}")
    time.sleep(0.5)