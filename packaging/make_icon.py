"""Generuje icon.icns z prostego renderu (kwadrat + 4 pokoje). Wymaga matplotlib + sips/iconutil (macOS)."""
import subprocess
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

HERE = Path(__file__).resolve().parent
png = HERE / "icon_1024.png"
fig = plt.figure(figsize=(10.24, 10.24), dpi=100)
ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 10); ax.set_ylim(0, 10); ax.axis("off")
ax.add_patch(Rectangle((0.8, 0.8), 8.4, 8.4, facecolor="#F4F1EA", edgecolor="#1F2937", linewidth=18))
for (x, y, w, h, c) in [(0.8, 0.8, 5.0, 4.2, "#F6C453"), (5.8, 0.8, 3.4, 4.2, "#7FB3D5"),
                        (0.8, 5.0, 3.0, 4.2, "#B39DDB"), (3.8, 5.0, 5.4, 4.2, "#A5D6A7")]:
    ax.add_patch(Rectangle((x, y), w, h, facecolor=c, edgecolor="#1F2937", linewidth=10))
fig.savefig(png, transparent=True)

iconset = HERE / "icon.iconset"; iconset.mkdir(exist_ok=True)
for s in (16, 32, 128, 256, 512):
    for scale in (1, 2):
        size = s * scale
        name = f"icon_{s}x{s}{'@2x' if scale == 2 else ''}.png"
        subprocess.run(["sips", "-z", str(size), str(size), str(png), "--out", str(iconset / name)],
                       check=True, capture_output=True)
subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(HERE / "icon.icns")], check=True)
print("OK", HERE / "icon.icns")
