"""Check that the website's JavaScript engine still matches this Python backend exactly.
  python tools/parity_check.py --js ../web/src/somacare --residents ../web/public/demo/residents.json
Runs one simulated night (turns, a shift, a caregiver in frame, a covered body, wet reports,
photo suggestion and nurse confirmation) through both and compares every frame and snapshot."""
import argparse, json, random, subprocess, sys, tempfile
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent)); sys.path.insert(0, str(HERE.parent / "tests")); sys.path.insert(0, str(HERE))
from test_live import fake_kp
from record_replay import record

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--js", required=True); ap.add_argument("--residents", required=True)
    a = ap.parse_args(); rng = random.Random(11); steps = []
    for i in range(1200):
        vt = i / 2
        k = "supine" if vt < 60 else "left30" if vt < 200 else "right30" if vt < 400 else "supine"
        if 40 <= vt < 41: k = "right30"
        people = [fake_kp(k, rng, 0.2 if 450 <= vt < 470 else 0.9)]
        if 190 <= vt < 197: people.append(fake_kp("supine", rng))
        steps.append(dict(vt=vt, people=[[list(p) for p in person] for person in people]))
    script = json.loads((HERE / "demo_script.json").read_text()) + [
        {"t": 300, "rid": 4, "action": "skin_suggestion", "site": "rhip", "finding": "stage2", "message": "photo"},
        {"t": 310, "rid": 4, "action": "skin_finding", "site": "rhip", "finding": "blanch"}]
    tmp = Path(tempfile.mkdtemp()); inp, py = tmp / "in.json", tmp / "py.json"
    record(((s["vt"], s["people"]) for s in steps), str(HERE.parent / "somacare_live" / "seed_residents.json"),
           py, time_scale=60, script=json.loads(json.dumps(script)))
    inp.write_text(json.dumps(dict(steps=steps, script=script)))
    r = subprocess.run(["node", "parity.mjs", str(inp), str(py), str(Path(a.residents).resolve())], cwd=a.js)
    sys.exit(r.returncode)

if __name__ == "__main__": main()
