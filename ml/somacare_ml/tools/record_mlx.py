"""Raspberry Pi + MLX90640 bench recorder.
pip install adafruit-circuitpython-mlx90640 ; enable I2C ; 800 kHz bus.
Writes ONLY ROI means + event markers to CSV. No frames are stored (privacy rule).
Keys while recording: v = void poured, t = turn, h = hands in, j = hands out, q = quit."""
import csv, sys, time, threading
import numpy as np
import board, busio, adafruit_mlx90640

PELVIS = (slice(9, 15), slice(12, 20))    # rows, cols in the 24x32 grid; adjust to your mount
CHEST  = (slice(3, 8),  slice(12, 20))

def main(out):
    i2c = busio.I2C(board.SCL, board.SDA, frequency=800000)
    mlx = adafruit_mlx90640.MLX90640(i2c)
    mlx.refresh_rate = adafruit_mlx90640.RefreshRate.REFRESH_2_HZ
    buf, marks = [0.0] * 768, []
    threading.Thread(target=lambda: [marks.append((time.time(), c)) for c in iter(lambda: sys.stdin.read(1), "q")],
                     daemon=True).start()
    with open(out, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["t", "pelvis", "chest", "marker"])
        t0 = time.time()
        while True:
            try: mlx.getFrame(buf)
            except ValueError: continue            # occasional I2C frame error, skip
            a = np.array(buf).reshape(24, 32)
            m = marks.pop(0)[1] if marks else ""
            w.writerow([round(time.time() - t0, 2), round(float(a[PELVIS].mean()), 3),
                        round(float(a[CHEST].mean()), 3), m]); f.flush()
            if m == "q": break

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "bench_night.csv")
