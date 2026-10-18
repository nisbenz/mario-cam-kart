"""
Generates a QR code for the phone controller page, with the WebSocket
address baked into the URL (?ws=...) so scanning it skips typing the
address entirely.

Usage: .venv/bin/python tools/make_controller_qr.py [web_port] [ws_port]
"""

import socket
import sys

import qrcode


def local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()


def main() -> None:
    web_port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    ws_port = int(sys.argv[2]) if len(sys.argv) > 2 else 8765

    ip = local_ip()
    ws_addr = f"ws://{ip}:{ws_port}/player2"
    page_url = f"http://{ip}:{web_port}/controller.html?ws={ws_addr}"

    img = qrcode.make(page_url)
    out_path = "controller_qr.png"
    img.save(out_path)

    print(f"Page URL: {page_url}")
    print(f"Saved QR code to: {out_path}")


if __name__ == "__main__":
    main()
