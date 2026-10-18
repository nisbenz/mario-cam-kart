from dataclasses import dataclass

import cv2
import mediapipe as mp

from config import STEER_DEADZONE

mp_pose = mp.solutions.pose


@dataclass
class Intent:
    steer: float
    accel: bool
    brake: bool
    drift: bool


def _landmark_intent(landmarks) -> Intent:
    left_shoulder = landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER]
    right_shoulder = landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER]
    left_wrist = landmarks[mp_pose.PoseLandmark.LEFT_WRIST]
    right_wrist = landmarks[mp_pose.PoseLandmark.RIGHT_WRIST]
    nose = landmarks[mp_pose.PoseLandmark.NOSE]

    shoulder_mid_x = (left_shoulder.x + right_shoulder.x) / 2
    raw_steer = (nose.x - shoulder_mid_x) * 4.0
    steer = max(-1.0, min(1.0, raw_steer))
    if abs(steer) < STEER_DEADZONE:
        steer = 0.0

    left_hand_up = left_wrist.y < left_shoulder.y
    right_hand_up = right_wrist.y < right_shoulder.y
    both_hands_up = left_hand_up and right_hand_up
    one_hand_up = left_hand_up != right_hand_up

    return Intent(
        steer=steer,
        accel=not both_hands_up,
        brake=both_hands_up,
        drift=one_hand_up,
    )


class PoseTracker:
    def __init__(self, camera_index: int):
        self._capture = cv2.VideoCapture(camera_index)
        self._pose = mp_pose.Pose(
            min_detection_confidence=0.5, min_tracking_confidence=0.5
        )

    def read_intent(self) -> Intent | None:
        ok, frame = self._capture.read()
        if not ok:
            return None
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = self._pose.process(frame_rgb)
        if not result.pose_landmarks:
            return None
        return _landmark_intent(result.pose_landmarks.landmark)

    def close(self) -> None:
        self._capture.release()
        self._pose.close()
