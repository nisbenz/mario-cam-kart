"""
Single-window cockpit view: melonDS game capture with a small webcam
picture-in-picture overlay in the top-left corner. Steers by posting key
events directly to the melonDS process (CGEventPostToPid), so it works
regardless of which window has OS focus.

Requires (macOS):
  - Screen Recording permission for the terminal/app running this script
    (System Settings -> Privacy & Security -> Screen Recording)
  - Accessibility permission for the same app
    (System Settings -> Privacy & Security -> Accessibility)
  - melonDS already running with the ROM loaded
"""

import sys
import os
import time
import math
import platform

import cv2
import numpy as np
import mediapipe as mp
import Quartz
from Quartz import (
    CGEventCreateMouseEvent,
    CGEventPostToPid,
    CGEventSourceCreate,
    CGPointMake,
    kCGEventLeftMouseDown,
    kCGEventLeftMouseDragged,
    kCGEventLeftMouseUp,
    kCGEventSourceStateHIDSystemState,
    kCGMouseButtonLeft,
)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))
from input_backend import MacKeyboardBackend, find_pids_by_name  # noqa: E402

DEBUG               = True
CAMERA_INDEX        = 0
PROCESS_NAME        = "melonDS"
PIP_WIDTH_FRACTION  = 0.30
DEAD_ZONE_DEG       = 12
RELEASE_ZONE_DEG    = 6
SOFT_ZONE_DEG       = 25
FLIP_CAMERA         = True
SHOW_ANGLE          = True
MIN_DETECTION_CONF  = 0.7
MIN_TRACKING_CONF   = 0.5
GRACE_FRAMES        = 8
OPEN_FINGER_THRESH  = 3
PINCH_THRESH        = 0.055
CLR_CURSOR          = (0, 220, 255)
CLR_CURSOR_CLICK    = (0, 255, 0)

CLR_WHEEL   = (80, 200, 255)
CLR_LEFT    = (60, 120, 255)
CLR_RIGHT   = (50, 220, 140)
CLR_NEUTRAL = (200, 200, 200)
CLR_TEXT    = (255, 255, 255)
CLR_ACCENT  = (0, 180, 255)
CLR_HAND_L  = (255, 130, 60)
CLR_HAND_R  = (60, 230, 130)
CLR_ACCEL   = (50, 220, 100)
CLR_BRAKE   = (0, 60, 255)

mp_hands   = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils


def draw_steering_wheel(frame, center, angle_deg, direction, strength):
    h, w = frame.shape[:2]
    radius = int(min(w, h) * 0.10)
    cx, cy = center

    color = CLR_NEUTRAL
    if direction == "LEFT":
        color = CLR_LEFT
    elif direction == "RIGHT":
        color = CLR_RIGHT

    cv2.circle(frame, (cx + 3, cy + 3), radius, (0, 0, 0), 4)
    cv2.circle(frame, (cx, cy), radius, color, 3)

    for sa in [0, 120, 240]:
        rad = math.radians(sa - angle_deg)
        x1 = int(cx + radius * 0.4 * math.cos(rad))
        y1 = int(cy - radius * 0.4 * math.sin(rad))
        x2 = int(cx + radius * 0.95 * math.cos(rad))
        y2 = int(cy - radius * 0.95 * math.sin(rad))
        cv2.line(frame, (x1, y1), (x2, y2), color, 2)

    cv2.circle(frame, (cx, cy), 6, color, -1)

    if direction != "STRAIGHT":
        start_a = -30 if direction == "RIGHT" else 150
        end_a   =  30 if direction == "RIGHT" else 210
        cv2.ellipse(frame, (cx, cy), (radius, radius), 0, start_a, end_a, color, 5)


def draw_hud(frame, angle, direction, strength, throttle_mode, both_hands_visible, left_open, right_open, fps):
    h, w = frame.shape[:2]

    overlay = frame.copy()
    cv2.rectangle(overlay, (0, h - 160), (w, h), (10, 10, 20), -1)
    cv2.addWeighted(overlay, 0.65, frame, 0.35, 0, frame)

    bar_w = int(w * 0.5)
    bar_h = 14
    bar_x = (w - bar_w) // 2
    bar_y = h - 110
    cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h), (50, 50, 60), -1)

    mid = bar_x + bar_w // 2
    cv2.rectangle(frame, (mid - 2, bar_y - 4), (mid + 2, bar_y + bar_h + 4), (180, 180, 180), -1)

    fill_len = int((bar_w // 2) * strength)
    if direction == "LEFT" and fill_len > 0:
        cv2.rectangle(frame, (mid - fill_len, bar_y), (mid, bar_y + bar_h), CLR_LEFT, -1)
    elif direction == "RIGHT" and fill_len > 0:
        cv2.rectangle(frame, (mid, bar_y), (mid + fill_len, bar_y + bar_h), CLR_RIGHT, -1)

    font      = cv2.FONT_HERSHEY_SIMPLEX
    dir_color = CLR_LEFT if direction == "LEFT" else (CLR_RIGHT if direction == "RIGHT" else CLR_NEUTRAL)
    cv2.putText(frame, "<- LEFT",  (bar_x, bar_y - 10),               font, 0.45, CLR_LEFT,  1)
    cv2.putText(frame, "RIGHT ->", (bar_x + bar_w - 80, bar_y - 10),  font, 0.45, CLR_RIGHT, 1)
    cv2.putText(frame, direction,  (mid - 30, bar_y + bar_h + 28),    font, 0.8,  dir_color, 2)

    if SHOW_ANGLE:
        cv2.putText(frame, f"{angle:+.1f} deg", (bar_x, h - 80), font, 0.55, CLR_TEXT, 1)

    throttle_color = CLR_ACCEL if throttle_mode == "ACCEL" else (CLR_BRAKE if throttle_mode == "BRAKE" else CLR_NEUTRAL)
    throttle_label = {
        "ACCEL":   "ACCEL [UP]",
        "BRAKE":   "BRAKE [DOWN]",
        "NEUTRAL": "NEUTRAL",
    }[throttle_mode]

    cv2.rectangle(frame, (bar_x, h - 65), (bar_x + bar_w, h - 42), (30, 30, 40), -1)
    cv2.rectangle(frame, (bar_x, h - 65), (bar_x + bar_w, h - 42), throttle_color, 2)
    cv2.putText(frame, throttle_label, (bar_x + 10, h - 48), font, 0.65, throttle_color, 2)

    l_label = "OPEN" if left_open else "FIST"
    r_label = "OPEN" if right_open else "FIST"
    l_color = CLR_BRAKE if left_open else CLR_ACCEL
    r_color = CLR_BRAKE if right_open else CLR_ACCEL
    cv2.putText(frame, f"L:{l_label}", (bar_x + bar_w + 10, h - 100), font, 0.5, l_color, 1)
    cv2.putText(frame, f"R:{r_label}", (bar_x + bar_w + 10, h - 80),  font, 0.5, r_color, 1)

    cv2.putText(frame, f"FPS: {fps:.0f}", (w - 90, 30), font, 0.55, CLR_ACCENT, 1)

    status       = "BOTH HANDS DETECTED" if both_hands_visible else "SHOW BOTH HANDS"
    status_color = (60, 220, 60) if both_hands_visible else (0, 80, 255)
    cv2.putText(frame, status, (10, 30), font, 0.55, status_color, 1)

    draw_steering_wheel(frame, (w - 80, h - 80), angle, direction, strength)


def draw_hand_connection(frame, lw, rw):
    lx, ly = lw
    rx, ry = rw
    cv2.line(frame, (lx, ly), (rx, ry), (30, 100, 200), 8)
    cv2.line(frame, (lx, ly), (rx, ry), CLR_ACCENT, 2)
    cv2.circle(frame, (lx, ly), 10, CLR_HAND_L, -1)
    cv2.circle(frame, (rx, ry), 10, CLR_HAND_R, -1)
    cv2.circle(frame, (lx, ly), 13, CLR_HAND_L, 2)
    cv2.circle(frame, (rx, ry), 13, CLR_HAND_R, 2)
    mx = (lx + rx) // 2
    my = (ly + ry) // 2
    cv2.circle(frame, (mx, my), 7, CLR_WHEEL, -1)


def is_open_hand(hand_landmarks):
    FINGER_TIPS = [8, 12, 16, 20]
    FINGER_PIPS = [6, 10, 14, 18]
    extended = sum(
        1 for tip, pip in zip(FINGER_TIPS, FINGER_PIPS)
        if hand_landmarks.landmark[tip].y < hand_landmarks.landmark[pip].y
    )
    return extended >= OPEN_FINGER_THRESH


def find_window(pid):
    window_list = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionAll, Quartz.kCGNullWindowID
    )
    candidates = [
        w for w in window_list
        if w.get("kCGWindowOwnerPID") == pid
        and w.get("kCGWindowLayer") == 0
        and w.get("kCGWindowAlpha", 1) > 0
    ]
    if not candidates:
        return None
    best = max(
        candidates,
        key=lambda w: w["kCGWindowBounds"]["Width"] * w["kCGWindowBounds"]["Height"],
    )
    return best["kCGWindowNumber"], best["kCGWindowBounds"]


def capture_window(window_id, bounds):
    rect = Quartz.CGRectMake(bounds["X"], bounds["Y"], bounds["Width"], bounds["Height"])
    image = Quartz.CGWindowListCreateImage(
        rect,
        Quartz.kCGWindowListOptionIncludingWindow,
        window_id,
        Quartz.kCGWindowImageBoundsIgnoreFraming | Quartz.kCGWindowImageNominalResolution,
    )
    if image is None:
        return None
    width  = Quartz.CGImageGetWidth(image)
    height = Quartz.CGImageGetHeight(image)
    if width == 0 or height == 0:
        return None
    bytes_per_row = Quartz.CGImageGetBytesPerRow(image)
    provider      = Quartz.CGImageGetDataProvider(image)
    data          = Quartz.CGDataProviderCopyData(provider)
    buf = np.frombuffer(data, dtype=np.uint8)
    arr = buf.reshape((height, bytes_per_row // 4, 4))
    return np.ascontiguousarray(arr[:, :width, :3])  # BGRA -> drop alpha, already BGR order


def post_mouse(mouse_source, target_pid, event_type, x, y):
    point = CGPointMake(x, y)
    event = CGEventCreateMouseEvent(mouse_source, event_type, point, kCGMouseButtonLeft)
    CGEventPostToPid(target_pid, event)


class SteeringController:
    def __init__(self):
        self.held_left  = False
        self.held_right = False

    def update_steer(self, left_wrist, right_wrist):
        dx = right_wrist[0] - left_wrist[0]
        dy = right_wrist[1] - left_wrist[1]
        angle = math.degrees(math.atan2(dy, dx))

        direction = "STRAIGHT"
        if angle < -DEAD_ZONE_DEG:
            direction = "LEFT"
        elif angle > DEAD_ZONE_DEG:
            direction = "RIGHT"
        elif self.held_left and angle > -RELEASE_ZONE_DEG:
            direction = "STRAIGHT"
        elif self.held_right and angle < RELEASE_ZONE_DEG:
            direction = "STRAIGHT"

        self.held_left  = direction == "LEFT"
        self.held_right = direction == "RIGHT"

        strength = 0.0
        if direction in ("LEFT", "RIGHT"):
            strength = min(1.0, (abs(angle) - DEAD_ZONE_DEG) / (SOFT_ZONE_DEG - DEAD_ZONE_DEG))

        return angle, direction, strength


def main():
    pids = find_pids_by_name(PROCESS_NAME)
    if not pids:
        print(f"[ERROR] No running '{PROCESS_NAME}' process found. Launch melonDS first.")
        return
    target_pid = pids[0]
    print(f"[INFO] Targeting {PROCESS_NAME} pid={target_pid}")

    window_info = find_window(target_pid)
    if window_info is None:
        print("[ERROR] Could not find melonDS window (is it minimized, or is Screen")
        print("        Recording permission missing for this terminal/app?)")
        return
    window_id, bounds = window_info

    backend       = MacKeyboardBackend(target_pid)
    mouse_source  = CGEventSourceCreate(kCGEventSourceStateHIDSystemState)
    pinch_active  = False
    mouse_pressed = False

    cam_backend = cv2.CAP_AVFOUNDATION if platform.system() == "Darwin" else cv2.CAP_ANY
    cap = cv2.VideoCapture(CAMERA_INDEX, cam_backend)
    if not cap.isOpened():
        cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        print("[ERROR] Cannot open camera.")
        print("  -> macOS: System Settings > Privacy & Security > Camera")
        return
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    hands = mp_hands.Hands(
        static_image_mode=False,
        max_num_hands=2,
        model_complexity=0,
        min_detection_confidence=MIN_DETECTION_CONF,
        min_tracking_confidence=MIN_TRACKING_CONF,
    )

    controller    = SteeringController()
    lost_frames   = 0
    window_positioned = False
    prev_time     = time.time()
    angle         = 0.0
    direction     = "STRAIGHT"
    strength      = 0.0
    throttle_mode = "NEUTRAL"
    left_open     = False
    right_open    = False

    print("=" * 55)
    print("  Mario Kart Cockpit  |  Press Q to quit")
    print("  FIST = Accelerate   OPEN = Brake   Tilt hands = Steer")
    print("=" * 55)

    try:
        while True:
            fresh = find_window(target_pid)
            if fresh is None:
                print("[WARN] melonDS window not found. Retrying...")
                time.sleep(0.5)
                continue
            window_id, bounds = fresh

            game_frame = capture_window(window_id, bounds)
            if game_frame is None:
                print("[WARN] Lost window capture (closed/minimized/no permission). Retrying...")
                time.sleep(0.5)
                continue

            ret, cam_frame = cap.read()
            if not ret or cam_frame is None:
                time.sleep(0.01)
                continue
            if FLIP_CAMERA:
                cam_frame = cv2.flip(cam_frame, 1)

            rgb = cv2.cvtColor(cam_frame, cv2.COLOR_BGR2RGB)
            rgb.flags.writeable = False
            results = hands.process(rgb)
            rgb.flags.writeable = True

            h, w = cam_frame.shape[:2]
            both_visible = False
            keys_down = set()

            cursor_norm = None

            if results.multi_hand_landmarks and results.multi_handedness:
                hand_data = {}
                landmarks_by_label = {}
                for hand_landmarks, handedness in zip(results.multi_hand_landmarks, results.multi_handedness):
                    label = handedness.classification[0].label
                    landmarks_by_label[label] = hand_landmarks
                    mp_drawing.draw_landmarks(cam_frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)
                    wrist  = hand_landmarks.landmark[0]
                    wx, wy = int(wrist.x * w), int(wrist.y * h)
                    opened = is_open_hand(hand_landmarks)
                    hand_data[label] = (wrist.x, wrist.y, wx, wy, opened)

                cursor_label = "Right" if "Right" in landmarks_by_label else (
                    "Left" if "Left" in landmarks_by_label else None
                )
                if cursor_label:
                    lm        = landmarks_by_label[cursor_label]
                    index_tip = lm.landmark[8]
                    thumb_tip = lm.landmark[4]
                    cursor_norm = (index_tip.x, index_tip.y)
                    pinch_dist  = math.hypot(thumb_tip.x - index_tip.x, thumb_tip.y - index_tip.y)
                    pinching    = pinch_dist < PINCH_THRESH

                    screen_x = bounds["X"] + index_tip.x * bounds["Width"]
                    screen_y = bounds["Y"] + index_tip.y * bounds["Height"]

                    if pinching and not mouse_pressed:
                        post_mouse(mouse_source, target_pid, kCGEventLeftMouseDown, screen_x, screen_y)
                        mouse_pressed = True
                        if DEBUG:
                            print(f"[DEBUG] mouse down at ({screen_x:.0f}, {screen_y:.0f})")
                    elif pinching and mouse_pressed:
                        post_mouse(mouse_source, target_pid, kCGEventLeftMouseDragged, screen_x, screen_y)
                    elif not pinching and mouse_pressed:
                        post_mouse(mouse_source, target_pid, kCGEventLeftMouseUp, screen_x, screen_y)
                        mouse_pressed = False
                        if DEBUG:
                            print(f"[DEBUG] mouse up at ({screen_x:.0f}, {screen_y:.0f})")

                    pinch_active = pinching
                else:
                    if mouse_pressed:
                        post_mouse(mouse_source, target_pid, kCGEventLeftMouseUp,
                                   bounds["X"], bounds["Y"])
                        mouse_pressed = False
                    pinch_active = False

                if "Left" in hand_data and "Right" in hand_data:
                    both_visible = True
                    lost_frames  = 0
                    lx_n, ly_n, lx_px, ly_px, left_open  = hand_data["Left"]
                    rx_n, ry_n, rx_px, ry_px, right_open = hand_data["Right"]

                    draw_hand_connection(cam_frame, (lx_px, ly_px), (rx_px, ry_px))
                    angle, direction, strength = controller.update_steer((lx_n, ly_n), (rx_n, ry_n))

                    if direction == "LEFT":
                        keys_down.add("Left")
                    elif direction == "RIGHT":
                        keys_down.add("Right")

                    if left_open and right_open:
                        throttle_mode = "BRAKE"
                        keys_down.add("Down")
                    elif (not left_open) and (not right_open):
                        throttle_mode = "ACCEL"
                        keys_down.add("Up")
                    else:
                        throttle_mode = "NEUTRAL"
                else:
                    lost_frames += 1
                    if DEBUG:
                        print(f"[DEBUG] only {list(hand_data.keys())} detected "
                              f"(need both Left and Right)")
            else:
                lost_frames += 1
                pinch_active = False
                if mouse_pressed:
                    post_mouse(mouse_source, target_pid, kCGEventLeftMouseUp, bounds["X"], bounds["Y"])
                    mouse_pressed = False
                if DEBUG:
                    print("[DEBUG] no hands detected")

            if lost_frames >= GRACE_FRAMES:
                keys_down = set()
                angle, direction, strength = 0.0, "STRAIGHT", 0.0
                throttle_mode = "NEUTRAL"
                left_open = right_open = False

            backend.set_keys(keys_down)

            now       = time.time()
            fps       = 1.0 / max(now - prev_time, 1e-6)
            prev_time = now

            draw_hud(cam_frame, angle, direction, strength, throttle_mode,
                      both_visible, left_open, right_open, fps)

            gw = game_frame.shape[1]
            pip_w  = max(1, int(gw * PIP_WIDTH_FRACTION))
            pip_h  = max(1, int(pip_w * cam_frame.shape[0] / cam_frame.shape[1]))
            pip    = cv2.resize(cam_frame, (pip_w, pip_h))

            margin = 16
            composite = game_frame.copy()
            x0, y0 = margin, margin
            cv2.rectangle(
                composite, (x0 - 3, y0 - 3), (x0 + pip_w + 3, y0 + pip_h + 3),
                (255, 255, 255), 2,
            )
            composite[y0:y0 + pip_h, x0:x0 + pip_w] = pip

            if cursor_norm is not None:
                ch, cw = composite.shape[:2]
                cur_x = int(cursor_norm[0] * cw)
                cur_y = int(cursor_norm[1] * ch)
                color = CLR_CURSOR_CLICK if pinch_active else CLR_CURSOR
                cv2.circle(composite, (cur_x, cur_y), 16, color, 2)
                cv2.line(composite, (cur_x - 24, cur_y), (cur_x + 24, cur_y), color, 1)
                cv2.line(composite, (cur_x, cur_y - 24), (cur_x, cur_y + 24), color, 1)

            cv2.imshow("Mario Kart Cockpit", composite)
            if not window_positioned:
                cv2.moveWindow("Mario Kart Cockpit", int(bounds["X"]), int(bounds["Y"]))
                window_positioned = True
            key = cv2.waitKey(1) & 0xFF
            if key in (ord('q'), ord('Q'), 27):
                break

    finally:
        backend.release_all()
        if mouse_pressed:
            post_mouse(mouse_source, target_pid, kCGEventLeftMouseUp, bounds["X"], bounds["Y"])
        hands.close()
        cap.release()
        cv2.destroyAllWindows()
        print("\n[INFO] Stopped. All keys released.")


if __name__ == "__main__":
    main()
