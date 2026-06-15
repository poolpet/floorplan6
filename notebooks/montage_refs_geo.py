"""Skleja parter+poddasze danego domu w jeden PNG (galeria weryfikacyjna)."""
import sys
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

SRC = Path("rzuty/refs_geo")
OUT = Path("rzuty/refs_geo/_galeria"); OUT.mkdir(parents=True, exist_ok=True)

names = sys.argv[1:] or ["tropie", "kudowe", "ligasy", "modlnica", "osobie", "rogoznik"]
for name in names:
    storeys = [p for p in [SRC / f"{name}_parter.png", SRC / f"{name}_poddasze.png"] if p.exists()]
    if not storeys:
        print(f"BRAK PNG dla {name}"); continue
    fig, axes = plt.subplots(1, len(storeys), figsize=(7.0 * len(storeys), 5.0))
    if len(storeys) == 1:
        axes = [axes]
    for ax, p in zip(axes, storeys):
        ax.imshow(plt.imread(p)); ax.axis("off")
    fig.suptitle(f"{name.upper()}  — wzorzec vs odczyt (parter | poddasze)", fontsize=13)
    fig.tight_layout()
    out = OUT / f"{name}_galeria.png"
    fig.savefig(out, dpi=130, bbox_inches="tight"); plt.close(fig)
    print("ZAPISANO", out)
