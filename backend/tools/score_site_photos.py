"""Score the photos you want on the website with the real skin model, once, on your laptop.
The website then shows these real results when a visitor drops or picks a photo.

  python tools/score_site_photos.py            # reads ../demo_media/site_photos, writes ../web/public/demo/photos

Put 15-20 images in demo_media/site_photos/. Optional demo_media/site_photos/credits.csv with columns
file,credit,licence,source_url. Every photo is re-saved (max 1024 px, EXIF/location data removed)."""
import argparse, csv, io, json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageOps
from somacare_live import skin

EXT = {".jpg", ".jpeg", ".png", ".webp"}

def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", Path(name).stem.lower()).strip("-") or "photo"

def score(src, out, allow_missing_model=False):
    src, out = Path(src), Path(out); out.mkdir(parents=True, exist_ok=True)
    credits = {}
    if (src / "credits.csv").exists():
        with open(src / "credits.csv", newline="") as fh:
            for row in csv.DictReader(fh): credits[row["file"].strip()] = row
    files = sorted((p for p in src.iterdir() if p.suffix.lower() in EXT), key=lambda p: p.name.lower())
    if not files: raise SystemExit(f"No images in {src}")
    items, used = [], set()
    for p in files:
        img = ImageOps.exif_transpose(Image.open(p)).convert("RGB"); img.thumbnail((1024, 1024))
        buf = io.BytesIO(); img.save(buf, "JPEG", quality=88)          # re-encode: drops EXIF / GPS
        sug = skin.suggest(buf.getvalue())
        if sug["status"] == "model_not_loaded" and not allow_missing_model:
            raise SystemExit("Skin model not found. Run tools/get_skin_model.sh first "
                             "(results must come from the real model).")
        name = slug(p.name)
        while name in used: name += "-2"
        used.add(name); (out / f"{name}.jpg").write_bytes(buf.getvalue())
        c = credits.get(p.name, {})
        items.append(dict(file=f"{name}.jpg", original=p.name, **{k: sug.get(k) for k in
                          ("status", "label", "confidence", "finding", "message", "probs", "model")},
                          credit=c.get("credit"), licence=c.get("licence"), source_url=c.get("source_url")))
        print(f"{p.name:40s} -> {sug.get('label') or sug['status']:12s} {sug['message']}")
    manifest = dict(model=skin.SOURCE, note="Scored offline with the real model. Suggestions only; a nurse confirms.",
                    photos=items)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    missing = [i["original"] for i in items if not i["credit"]]
    print(f"\n{len(items)} photos -> {out}/manifest.json")
    if missing: print("No credit/licence recorded for:", ", ".join(missing))
    return manifest

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(Path(__file__).resolve().parents[2] / "demo_media" / "site_photos"))
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[2] / "web" / "public" / "demo" / "photos"))
    ap.add_argument("--allow-missing-model", action="store_true")
    a = ap.parse_args(); score(a.src, a.out, a.allow_missing_model)
