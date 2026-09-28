"""FastAPI app. Run:  uvicorn somacare_live.api:app --host 0.0.0.0 --port 8000
Env: VIDEO_SOURCE (file, rtsp://..., or 0), VIDEO_BED (default 1), TIME_SCALE (default 1),
     PHOTO_AUTO_APPLY (default 1: photo suggestions tighten the plan until a nurse confirms),
     CORS_ORIGINS (comma list, default *), CALIB_PATH (default data/calibration_bed1.json)."""
import asyncio, json, os
from pathlib import Path
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from .state import Floor, CareClock
from .posture import PostureClassifier
from . import engine, skin

HERE = Path(__file__).parent
floor = Floor.from_file(os.environ.get("RESIDENTS", HERE / "seed_residents.json"),
                        clock=CareClock(float(os.environ.get("TIME_SCALE", "1"))))
clf = PostureClassifier(os.environ.get("CALIB_PATH", "data/calibration_bed1.json"))
worker = None
from contextlib import asynccontextmanager
@asynccontextmanager
async def lifespan(_app):
    start_video(); yield
app = FastAPI(title="SomaCare live", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
                   allow_methods=["*"], allow_headers=["*"])

def start_video():
    global worker
    src = os.environ.get("VIDEO_SOURCE")
    if src:
        from .video import VideoWorker
        worker = VideoWorker(floor, int(os.environ.get("VIDEO_BED", "1")), src, clf); worker.start()

def _rid(rid):
    if rid not in floor.R: raise HTTPException(404, "no such resident")
    return rid

@app.get("/api/health")
def health(): return dict(ok=True, video=bool(worker), calibrated=bool(clf.calib))

@app.get("/api/floor")
def get_floor(): return floor.snapshot()

@app.get("/api/stream")
async def stream():
    async def gen():
        last = -1
        while True:
            snap = floor.snapshot()
            yield f"data: {json.dumps(snap)}\n\n"
            for _ in range(10):                     # 1 s heartbeat, faster when something changed
                await asyncio.sleep(0.1)
                if floor.version != last: last = floor.version; break
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

class Inputs(BaseModel):
    braden: dict | None = None; cfs: int | None = None; mattress: str | None = None; nurse_max: int | None = None
@app.post("/api/residents/{rid}")
def set_inputs(rid: int, body: Inputs):
    floor.update_inputs(_rid(rid), body.model_dump(exclude_unset=True)); return floor.snapshot()

class PostureIn(BaseModel):
    posture: str; who: str = "caregiver"
@app.post("/api/residents/{rid}/posture")
def set_posture(rid: int, body: PostureIn):
    if body.posture not in engine.POSTURES: raise HTTPException(400, "posture must be supine, left30 or right30")
    floor.manual_posture(_rid(rid), body.posture, body.who); return floor.snapshot()

class WetIn(BaseModel):
    wet: bool; source: str = "caregiver"
@app.post("/api/residents/{rid}/wet")
def set_wet(rid: int, body: WetIn):
    floor.set_wet(_rid(rid), body.wet, body.source); return floor.snapshot()

@app.post("/api/residents/{rid}/skin-photo")
async def skin_photo(rid: int, site: str = Form(...), file: UploadFile = File(...)):
    if site not in engine.SITES: raise HTTPException(400, f"site must be one of {list(engine.SITES)}")
    data = await file.read()
    sug = skin.suggest(data); del data                    # photo is not written to disk here
    floor.skin_suggestion(_rid(rid), site, sug, os.environ.get("PHOTO_AUTO_APPLY", "1") == "1")
    return dict(suggestion=sug, floor=floor.snapshot())

class FindingIn(BaseModel):
    site: str; finding: str; nurse: str = "Nurse"
@app.post("/api/residents/{rid}/skin-finding")
def skin_finding(rid: int, body: FindingIn):
    if body.site not in engine.SITES or body.finding not in engine.FINDINGS: raise HTTPException(400, "bad site or finding")
    floor.skin_confirm(_rid(rid), body.site, body.finding, body.nurse); return floor.snapshot()

class DoneIn(BaseModel):
    caregiver: str
@app.post("/api/tasks/{rid}/done")
def task_done(rid: int, body: DoneIn):
    floor.task_done(_rid(rid), body.caregiver); return floor.snapshot()

class CalibIn(BaseModel):
    label: str | None = None     # supine | left30 | right30 to start collecting, null to stop
@app.post("/api/calibrate")
def calibrate(body: CalibIn):
    if not worker: raise HTTPException(400, "no video running")
    if body.label is None:
        worker.calib_label = None
        if set(worker.calib_samples) != {"supine", "left30", "right30"}:
            return dict(done=False, have={k: len(v) for k, v in worker.calib_samples.items()})
        return dict(done=True, calibration=clf.fit_calibration(worker.calib_samples))
    worker.calib_label = body.label; return dict(collecting=body.label)
