"""Optional keypoint path using MediaPipe Pose (Apache 2.0). Pose models are trained on upright people and can fail on
overhead lying poses, so treat this as a second opinion to test on your own recordings, not as the primary path.
Landmark order is MediaPipe's 33-point layout."""
import numpy as np

# (left, right) index pairs in the 33-landmark layout
PAIRS = [(1, 4), (2, 5), (3, 6), (7, 8), (9, 10), (11, 12), (13, 14), (15, 16), (17, 18), (19, 20),
         (21, 22), (23, 24), (25, 26), (27, 28), (29, 30), (31, 32)]


def mirror_landmarks(lm):
    """lm: (33, 3) array of x, y, visibility with x in [0, 1]. Mirrors left-right and swaps paired landmarks."""
    out = lm.copy()
    out[:, 0] = 1.0 - out[:, 0]
    for a, b in PAIRS:
        out[[a, b]] = out[[b, a]]
    return out


POSE_MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/"
                  "pose_landmarker_lite.task")    # verify this address on the MediaPipe site before relying on it
_LANDMARKER = {}


def landmarks(img_bgr, model_path=None):
    """Returns (33, 3) or None. Uses the MediaPipe Tasks API (needs a downloaded .task model file passed as model_path),
    or the older mp.solutions API if this MediaPipe version still has it. Returns None, never raises, when unavailable."""
    try:
        import cv2
        import mediapipe as mp
        rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB) if img_bgr.ndim == 3 else cv2.cvtColor(img_bgr, cv2.COLOR_GRAY2RGB)
        if hasattr(mp, "solutions"):
            with mp.solutions.pose.Pose(static_image_mode=True, model_complexity=1, min_detection_confidence=0.3) as pose:
                res = pose.process(rgb)
            if not res.pose_landmarks:
                return None
            return np.array([[p.x, p.y, p.visibility] for p in res.pose_landmarks.landmark], float)
        if not model_path:
            return None
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision
        if model_path not in _LANDMARKER:
            opts = vision.PoseLandmarkerOptions(
                base_options=mp_python.BaseOptions(model_asset_path=model_path),
                running_mode=vision.RunningMode.IMAGE, num_poses=1, min_pose_detection_confidence=0.3)
            _LANDMARKER[model_path] = vision.PoseLandmarker.create_from_options(opts)
        res = _LANDMARKER[model_path].detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
        if not res.pose_landmarks:
            return None
        return np.array([[p.x, p.y, getattr(p, "visibility", 1.0) or 0.0] for p in res.pose_landmarks[0]], float)
    except Exception:
        return None


def keypoint_features(lm):
    """Geometry that does not depend on where the person is in the frame."""
    if lm is None:
        return np.full(20, np.nan)
    ctr = (lm[11, :2] + lm[12, :2] + lm[23, :2] + lm[24, :2]) / 4
    torso = np.linalg.norm((lm[11, :2] + lm[12, :2]) / 2 - (lm[23, :2] + lm[24, :2]) / 2) + 1e-6
    rel = (lm[:, :2] - ctr) / torso

    def ang(a, b):
        d = lm[b, :2] - lm[a, :2]
        return np.arctan2(d[1], d[0])
    f = [np.cos(ang(11, 12)), np.sin(ang(11, 12)), np.cos(ang(23, 24)), np.sin(ang(23, 24)),
         torso, lm[:, 2].mean(),
         rel[0, 0], rel[0, 1],                  # nose
         rel[15, 0], rel[16, 0], rel[25, 0], rel[26, 0],   # wrists and knees, sideways
         rel[15, 1], rel[16, 1], rel[25, 1], rel[26, 1],
         lm[11, 2], lm[12, 2], lm[23, 2], lm[24, 2]]
    return np.array(f, float)
