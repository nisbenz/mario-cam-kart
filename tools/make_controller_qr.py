"""
Generates one QR code per possible player slot (1-4), each encoding the
phone controller page URL with that player's own WebSocket port baked in
(?ws=...), so scanning skips typing the address entirely.

melonDS's native PhoneController listens directly on these ports (one
per EmuInstance in a multi-phone session) — no external bridge process
involved. Each instance's own QR overlay (see Window.cpp) loads its file
by a predictable path: /tmp/ds64_qr_p<N>.png.

Usage: .venv/bin/python tools/make_controller_qr.py [web_port] [base_ws_port]
"""

import socket
import sys

import qrcode

MAX_PLAYERS = 4


def local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()


def main() -> None:
    web_port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    base_ws_port = int(sys.argv[2]) if len(sys.argv) > 2 else 8765

    ip = local_ip()

    for i in range(MAX_PLAYERS):
        player_num = i + 1
        ws_port = base_ws_port + i
        ws_addr = f"ws://{ip}:{ws_port}"
        page_url = f"http://{ip}:{web_port}/controller.html?ws={ws_addr}"

        img = qrcode.make(page_url, border=2)
        out_path = f"/tmp/ds64_qr_p{player_num}.png"
        img.save(out_path)
        print(f"Player {player_num}: {page_url} -> {out_path}")

    # Keep a copy of player 1's QR in web/ for scan.html / manual sharing.
    qrcode.make(
        f"http://{ip}:{web_port}/controller.html?ws=ws://{ip}:{base_ws_port}",
        border=2,
    ).save("web/qr.png")
    print(f"Scan page: http://{ip}:{web_port}/scan.html")


if __name__ == "__main__":
    main()
