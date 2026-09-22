"""
encoder_test.py  —  run on Pico via Thonny BEFORE updating main.py
====================================================================
Verifies that both MT6835 encoders are wired and responding correctly.

MT6835 SPI PROTOCOL (corrected):
  Command byte 0: {CMD[3:0], ADDR[11:8]}
  Command byte 1: {ADDR[7:0]}
  CMD nibbles:  BURST=0xA  READ=0x3  WRITE=0x6
  Angle is 21-bit (2^21 = 2,097,152 counts/rev), read via BURST command.

BURST angle read (6 bytes):
  TX: [0xA0, 0x03, 0x00, 0x00, 0x00, 0x00]
  RX: [xx,   xx,   ANG[20:13], ANG[12:5], ANG[4:0]>>3, CRC]

PIN ASSIGNMENT
--------------
SPI1  SCK  → GP14
SPI1  MOSI → GP11
SPI1  MISO → GP12
CS X-axis  → GP9
CS Y-axis  → GP13
VCC        → 3.3V
GND        → GND
"""

from machine import SPI, Pin
import utime

# ── SPI setup ────────────────────────────────────────────────────────────────
spi = SPI(1, baudrate=1_000_000, polarity=1, phase=1,   # Mode 3: CPOL=1 CPHA=1
          sck=Pin(14), mosi=Pin(11), miso=Pin(12))

enc_cs_x = Pin(9,  Pin.OUT, value=1)   # X encoder chip select (active LOW)
enc_cs_y = Pin(13, Pin.OUT, value=1)   # Y encoder chip select (active LOW)

# ── SWAP TEST: uncomment these two lines to route X encoder through GP13 ──────
#enc_cs_x = Pin(13, Pin.OUT, value=1)
#enc_cs_y = Pin(9,  Pin.OUT, value=1)

# ── MT6835 constants ──────────────────────────────────────────────────────────
BURST_CMD      = 0xA          # burst angle read command nibble
READ_CMD       = 0x3          # single register read command nibble
COUNTS_PER_REV = 2_097_152    # 2^21

# ── MT6835 BURST angle read ───────────────────────────────────────────────────
def read_angle(cs):
    """
    Read 21-bit angle from MT6835 using BURST command.
    TX: [0xA0, 0x03, 0,0,0,0]  (6 bytes)
    RX: [xx, xx, ANG[20:13], ANG[12:5], ANG[4:0] in bits[7:3], CRC]
    Returns integer 0–2097151, or -1 on no response.
    """
    tx = bytearray([0xA0, 0x03, 0x00, 0x00, 0x00, 0x00])
    rx = bytearray(6)
    cs.value(0)
    utime.sleep_us(2)
    spi.write_readinto(tx, rx)
    utime.sleep_us(2)
    cs.value(1)
    # All-FF means MISO floating = no device
    if rx[2] == 0xFF and rx[3] == 0xFF and rx[4] == 0xFF:
        return -1
    raw = ((rx[2] << 13) | (rx[3] << 5) | (rx[4] >> 3)) & 0x1FFFFF
    return raw

def read_reg(cs, addr):
    """Read one MT6835 register at 12-bit address. Returns data byte."""
    b0 = (READ_CMD << 4) | ((addr >> 8) & 0x0F)   # e.g. addr=0x007 → 0x30
    b1 = addr & 0xFF
    tx = bytearray([b0, b1, 0x00])
    rx = bytearray(3)
    cs.value(0)
    utime.sleep_us(5)
    spi.write_readinto(tx, rx)
    utime.sleep_us(5)
    cs.value(1)
    utime.sleep_ms(1)
    return rx[2]   # data arrives in third byte

def angle_to_deg(raw):
    return raw / COUNTS_PER_REV * 360.0

# ── Protocol verification ─────────────────────────────────────────────────────
print("=" * 55)
print("MT6835 PROTOCOL CHECK")
print("Reading ABZ resolution registers 0x007 / 0x008")
print("(non-zero values = SPI comms confirmed working)")
print("=" * 55)
for label, cs in [("X", enc_cs_x), ("Y", enc_cs_y)]:
    r7  = read_reg(cs, 0x007)
    r8  = read_reg(cs, 0x008)
    abz = ((r7 << 6) | (r8 >> 2)) + 1
    print(f"  {label}: REG 0x007=0x{r7:02X}  REG 0x008=0x{r8:02X}  ABZ_RES={abz} PPR")
print()

# ── Raw burst read debug ──────────────────────────────────────────────────────
print("=" * 55)
print("RAW BURST READ (6 bytes, Mode 3)")
print("=" * 55)
for label, cs in [("X", enc_cs_x), ("Y", enc_cs_y)]:
    tx = bytearray([0xA0, 0x03, 0x00, 0x00, 0x00, 0x00])
    rx = bytearray(6)
    cs.value(0)
    utime.sleep_us(5)
    spi.write_readinto(tx, rx)
    utime.sleep_us(5)
    cs.value(1)
    raw = ((rx[2] << 13) | (rx[3] << 5) | (rx[4] >> 3)) & 0x1FFFFF
    print(f"  {label}: {' '.join(f'{b:02X}' for b in rx)}  raw={raw}  {raw/COUNTS_PER_REV*360:.2f}°")
print()

# ── Y-only isolation test ─────────────────────────────────────────────────────
print("=" * 55)
print("Y ENCODER ISOLATION TEST (X disabled, 100kHz)")
print("=" * 55)
spi_slow = SPI(1, baudrate=100_000, polarity=1, phase=1,
               sck=Pin(14), mosi=Pin(11), miso=Pin(12))
enc_cs_x.value(1)   # X CS held HIGH (disabled) for entire test
for i in range(10):
    tx = bytearray([0xA0, 0x03, 0x00, 0x00, 0x00, 0x00])
    rx = bytearray(6)
    enc_cs_y.value(0)
    utime.sleep_us(20)
    spi_slow.write_readinto(tx, rx)
    utime.sleep_us(20)
    enc_cs_y.value(1)
    raw = ((rx[2] << 13) | (rx[3] << 5) | (rx[4] >> 3)) & 0x1FFFFF
    print(f"  Y raw={raw:7d}  bytes: {' '.join(f'{b:02X}' for b in rx)}")
    utime.sleep_ms(200)
print()
# Reset SPI to 1MHz for main loop
spi = SPI(1, baudrate=1_000_000, polarity=1, phase=1,
          sck=Pin(14), mosi=Pin(11), miso=Pin(12))

# ── Main test loop ────────────────────────────────────────────────────────────
print("=" * 55)
print("MT6835 Encoder Test (21-bit, 2,097,152 counts/rev)")
print("Rotate knobs slowly — values should change smoothly")
print("Ctrl+C to stop")
print("=" * 55)
print()

prev_x = read_angle(enc_cs_x)
prev_y = read_angle(enc_cs_y)

x_revs = 0
y_revs = 0
HALF = COUNTS_PER_REV // 2   # 1,048,576

loop = 0
while True:
    try:
        raw_x = read_angle(enc_cs_x)
        raw_y = read_angle(enc_cs_y)
        utime.sleep_ms(50)

        # Track full revolutions for multi-turn display
        if raw_x >= 0 and prev_x >= 0:
            dx = raw_x - prev_x
            if dx > HALF:   x_revs -= 1
            elif dx < -HALF: x_revs += 1
            prev_x = raw_x

        if raw_y >= 0 and prev_y >= 0:
            dy = raw_y - prev_y
            if dy > HALF:   y_revs -= 1
            elif dy < -HALF: y_revs += 1
            prev_y = raw_y

        # Print every 5 loops (~250ms)
        if loop % 5 == 0:
            if raw_x < 0:
                x_str = "NO RESPONSE — check X wiring"
            else:
                x_deg = angle_to_deg(raw_x)
                x_mm  = (x_revs + raw_x / COUNTS_PER_REV) * 0.5
                x_str = f"raw={raw_x:7d}  {x_deg:6.2f}°  revs={x_revs:3d}  pos={x_mm:7.4f}mm"

            if raw_y < 0:
                y_str = "NO RESPONSE — check Y wiring"
            else:
                y_deg = angle_to_deg(raw_y)
                y_mm  = (y_revs + raw_y / COUNTS_PER_REV) * 0.5
                y_str = f"raw={raw_y:7d}  {y_deg:6.2f}°  revs={y_revs:3d}  pos={y_mm:7.4f}mm"

            print(f"X: {x_str}")
            print(f"Y: {y_str}")
            print()

        loop += 1

    except KeyboardInterrupt:
        print("Stopped.")
        break
