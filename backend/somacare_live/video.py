"""Video -> keypoints -> posture -> Floor. Frames live only in memory and are dropped.
Source can be a file path, an RTSP URL (e.g. the Tapo camera) or a webcam index ("0").
Uses MediaPipe Pose Landmarker (Apache-2.0). First run downloads the model file."""
import os, threading, time, urllib.request
from pathlib import Path

MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
             "pose_landmarker_full/float16/latest/pose_landmarker_full.task")

def ensure_model(path="models/pose_landmarker_full.task"):
    p = Path(path)
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True); urllib.request.urlretrieve(MODEL_URL, p)
    return str(p)

class VideoWorker(threading.Thread):
    def __init__(self, floor, rid, source, classifier, sample_hz=2.0, loop=True, realtime=True):
        super().__init__(daemon=True)
        self.floor, self.rid, self.source, self.clf = floor, rid, source, classifier
        self.sample_hz, self.loop, self.realtime = sample_hz, loop, realtime
        self.stop_flag = False; self.calib_label = None; self.calib_samples = {}

    def run(self):
        import cv2, mediapipe as mp
        from mediapipe.tasks import python as mpt
        from mediapipe.tasks.python import vision
        opts = vision.PoseLandmarkerOptions(
            base_options=mpt.BaseOptions(model_asset_path=ensure_model()),
            running_mode=vision.RunningMode.VIDEO, num_poses=2,
            min_pose_detection_confidence=0.3, min_tracking_confidence=0.3)
        src = int(self.source) if str(self.source).isdigit() else self.source
        with vision.PoseLandmarker.create_from_options(opts) as lm:
            while not self.stop_flag:
                cap = cv2.VideoCapture(src)
                fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
                step = max(1, int(round(fps / self.sample_hz))); i = 0; ts = 0; t_wall = time.monotonic()
                while not self.stop_flag:
                    ok, frame = cap.read()
                    if not ok: break
                    i += 1
                    if i % step: continue
                    ts += int(1000 / self.sample_hz)
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    res = lm.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ts)
                    del frame, rgb                                   # nothing is kept
                    people = res.pose_landmarks or []
                    masked = len(people) > 1                         # caregiver in view
                    if people:
                        kp = [(p.x, p.y, p.z, p.visibility) for p in people[0]]
                        pred = self.clf.predict(kp)
                        if self.calib_label and not masked:
                            self.calib_samples.setdefault(self.calib_label, []).append(pred["feat"])
                        ui_kp = [[round(p[0], 3), round(p[1], 3), round(p[3], 2)] for p in kp]
                    else:
                        pred = dict(probs={"supine": 1/3, "left30": 1/3, "right30": 1/3}, best=None, conf=0.0,
                                    reason="no person found", feat=None); ui_kp = None
                    self.floor.sensor_update(self.rid, pred, masked, ui_kp)
                    if self.realtime:                                # keep video time and care clock in step
                        t_wall += 1 / self.sample_hz; time.sleep(max(0, t_wall - time.monotonic()))
                cap.release()
                if not self.loop: break
