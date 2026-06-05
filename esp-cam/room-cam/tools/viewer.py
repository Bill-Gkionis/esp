#!/usr/bin/env python3
"""
viewer.py — receives JPEG frames from ESP32-CAM over serial and serves
            MJPEG on http://localhost:8080 for browser viewing from Windows.

Usage:
    python3 tools/viewer.py [--port /dev/ttyUSB0] [--baud 921600] [--http-port 8080]
"""
import argparse
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import serial

MARKER     = b'\xAA\xBB\xCC\xDD'
MAX_FRAME  = 150_000   # sanity cap — no real QVGA JPEG exceeds this

# Shared latest frame + lock
_frame      = None
_frame_lock = threading.Lock()


def _find_marker(ser: serial.Serial) -> bool:
    """Scan the byte stream until the 4-byte start marker is aligned."""
    buf = bytearray(ser.read(4))
    if len(buf) < 4:
        return False
    while bytes(buf) != MARKER:
        byte = ser.read(1)
        if not byte:
            return False
        buf = buf[1:] + bytearray(byte)
    return True


def serial_reader(port: str, baud: int) -> None:
    global _frame
    ser = serial.Serial(port, baud, timeout=3)
    print(f"[serial] {port} @ {baud} baud — waiting for frames…")

    while True:
        try:
            if not _find_marker(ser):
                continue

            raw = ser.read(4)
            if len(raw) < 4:
                continue
            length = struct.unpack('<I', raw)[0]

            if length == 0 or length > MAX_FRAME:
                continue  # corrupted header — re-sync

            jpeg = ser.read(length)
            if len(jpeg) != length:
                continue  # incomplete read — re-sync

            with _frame_lock:
                _frame = bytes(jpeg)

        except serial.SerialException as exc:
            print(f"[serial] error: {exc} — retrying in 2 s")
            time.sleep(2)
        except Exception as exc:
            print(f"[serial] unexpected: {exc}")


class MJPEGHandler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # silence per-request logs

    def do_GET(self):
        if self.path != '/':
            self.send_error(404)
            return

        self.send_response(200)
        self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()

        try:
            while True:
                with _frame_lock:
                    frame = _frame
                if frame:
                    header = (
                        f'--frame\r\n'
                        f'Content-Type: image/jpeg\r\n'
                        f'Content-Length: {len(frame)}\r\n\r\n'
                    ).encode()
                    self.wfile.write(header + frame + b'\r\n')
                    self.wfile.flush()
                time.sleep(0.05)   # poll at 20 Hz; actual rate limited by serial
        except (BrokenPipeError, ConnectionResetError):
            pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port',      default='/dev/ttyUSB0')
    parser.add_argument('--baud',      type=int, default=921600)
    parser.add_argument('--http-port', type=int, default=8080)
    args = parser.parse_args()

    t = threading.Thread(target=serial_reader, args=(args.port, args.baud), daemon=True)
    t.start()

    print(f"[http]   open http://localhost:{args.http_port} in your Windows browser")
    HTTPServer(('0.0.0.0', args.http_port), MJPEGHandler).serve_forever()


if __name__ == '__main__':
    main()
