"""
probe_uart_test.py — flash as main.py on slave to diagnose UART direction
Sends a heartbeat every second AND echoes back anything it receives.
"""
from machine import UART, Pin
import time

uart = UART(0, baudrate=115200, tx=Pin(16), rx=Pin(17), timeout=50)

count = 0
while True:
    # Send heartbeat every second so master can check slave→master direction
    uart.write("BEAT:{}\n".format(count).encode())
    count += 1

    # Echo back anything received so master can check master→slave direction
    data = uart.read(64)
    if data:
        uart.write(b"ECHO:" + data)

    time.sleep(1)
