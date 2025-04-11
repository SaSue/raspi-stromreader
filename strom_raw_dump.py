Strom-raw-dump-docker
1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
21
22
23
24
25
26
27
28
29
30
31
32
33
34
35
36
37
38
39
40
41
42
43
44
45
46
47
48
49
50
51
52
53
54
55
56
57
58
59
60
61
62
63
64
65
66
67
68
69
70
71
72
73
74
75
76
77
78
79
80
81
82
83
84
85
86
87
88
89
90
91
92
93
94
import serial
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("strom-dump")

START_SEQUENCE = b'\x1b\x1b\x1b\x1b'
END_SEQUENCE = b'\x1b\x1b\x1b\x1b\x1a'


def crc16_sml(data):
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return crc


def find_sml_blocks(buffer):
    blocks = []
    start = 0
    while True:
        start_index = buffer.find(START_SEQUENCE, start)
        if start_index == -1:
            break
        end_index = buffer.find(END_SEQUENCE, start_index + 4)
        if end_index == -1 or end_index + 5 > len(buffer):
            break
        block = buffer[start_index:end_index + 5]  # including END_SEQUENCE + padding + CRC
        blocks.append(block)
        start = end_index + 5
    return blocks


def decode_sml_block(block):
    if not block.startswith(START_SEQUENCE) or END_SEQUENCE not in block:
        return None, None, None

    try:
        end_index = block.index(END_SEQUENCE) + len(END_SEQUENCE)
        if end_index + 2 > len(block):
            return None, None, None

        crc_received = block[end_index:end_index + 2]
        data_for_crc = block[:end_index]
        calculated_crc = crc16_sml(data_for_crc).to_bytes(2, 'big')

        return block, calculated_crc, crc_received
    except Exception as e:
        logger.warning(f"Fehler bei der CRC-Berechnung: {e}")
        return None, None, None


def main():
    with serial.Serial("/dev/ttyUSB0", 9600, timeout=5) as ser:
        buffer = bytearray()
        while True:
            data = ser.read(512)
            if not data:
                continue
            buffer.extend(data)
            blocks = find_sml_blocks(buffer)

            for block in blocks:
                logger.info("\n")
                logger.info("[%s]", datetime.now().isoformat(timespec='seconds'))
                logger.info("📡 SML-Telegramm erkannt (Länge: %d Bytes)", len(block))
                logger.info("🔢 HEX: %s", block.hex())

                decoded_block, calculated_crc, received_crc = decode_sml_block(block)
                if decoded_block is None:
                    logger.warning("⚠️ Fehler beim Verarbeiten des Telegramms.")
                    continue

                expected = received_crc.hex().upper()
                calculated = calculated_crc.hex().upper()
                status = "✅ CRC: erwartet %s, berechnet %s → %s" % (
                    expected,
                    calculated,
                    "✔ gültig" if expected == calculated else "❌ ungültig"
                )
                logger.info(status)

            buffer.clear()


if __name__ == "__main__":
    main()
