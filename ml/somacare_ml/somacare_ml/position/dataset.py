"""Load frames written by tools.record_and_label or tools.extract_frames.
Layout: <root>/<person>/<cover>/<label>/frame_XXXXXX.jpg plus <root>/background.png. Labels other than the five
positions (for example 'transition') are skipped. Returns [(image, label, person, cover), ...]."""
import os
import cv2

POSITIONS = ("back", "left", "right", "sitting", "out_of_bed")


def load_dataset(root, max_per_folder=None):
    ds = []
    for person in sorted(os.listdir(root)):
        pdir = os.path.join(root, person)
        if not os.path.isdir(pdir):
            continue
        for cover in sorted(os.listdir(pdir)):
            for label in sorted(os.listdir(os.path.join(pdir, cover))):
                if label not in POSITIONS:
                    continue
                d = os.path.join(pdir, cover, label)
                files = sorted(f for f in os.listdir(d) if f.lower().endswith((".jpg", ".png")))
                if max_per_folder:
                    files = files[:max_per_folder]
                for f in files:
                    img = cv2.imread(os.path.join(d, f), cv2.IMREAD_GRAYSCALE)
                    if img is not None:
                        ds.append((img, label, person, cover))
    return ds


def load_background(root):
    return cv2.imread(os.path.join(root, "background.png"), cv2.IMREAD_GRAYSCALE)
