"""
FloorPlan4 — entry point.

Komendy:
  python main.py generate --type M2 --width 8 --height 6
  python main.py rebuild-stats
  python main.py validate --input plan.json
  python main.py show-data-plan --id PL_NL_01
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from shapely.geometry import Polygon


def cmd_generate(args):
    """Generuj warianty rzutu."""
    from core.variant_generator import generate_variants
    from viz.plan_renderer import render_floor_plan

    w, h = args.width, args.height

    # Zbuduj obrys — prostokąt lub L-kształt
    if args.notch:
        # L-kształt: --notch "nx,ny,nw,nh" (wycięcie w metrach, relative to bbox)
        parts = [float(x) for x in args.notch.split(",")]
        nx, ny, nw, nh = parts
        # L-shape: bounding box minus notch
        # Wycięcie w rogu — budujemy 6-wierzchołkowy polygon
        # Zakładamy wycięcie w prawym górnym rogu (nx,ny)-(nx+nw, ny+nh)
        polygon = Polygon([
            (0, 0), (w, 0),
            (w, ny), (nx, ny),
            (nx, ny + nh), (0, ny + nh),
        ])
        print(f"L-kształt: {w}×{h}m, wycięcie ({nx},{ny})-({nx+nw},{ny+nh})")
    else:
        polygon = Polygon([(0, 0), (w, 0), (w, h), (0, h)])

    entry = (args.entry_x, args.entry_y)

    print(f"Generuję warianty {args.type} dla obrysu {w}×{h}m...")
    print(f"Punkt wejścia: ({entry[0]}, {entry[1]})")
    print()

    variants = generate_variants(
        polygon=polygon,
        entry_point=entry,
        mtype=args.type,
        max_variants=args.max_variants,
    )

    if not variants:
        print("BŁĄD: Nie udało się wygenerować żadnego wariantu.")
        sys.exit(1)

    print(f"Wygenerowano {len(variants)} wariantów:\n")
    for i, plan in enumerate(variants):
        valid_str = "OK" if plan.is_valid else f"BŁĘDY: {len(plan.validation_errors)}"
        print(f"  Wariant {i + 1}: score={plan.score:.3f}  [{valid_str}]")

        for room in plan.rooms:
            print(f"    {room.spec.nazwa:30s}  {room.area:5.1f} m²  "
                  f"({room.width:.2f}×{room.depth:.2f}m, prop={room.proportion:.2f})")

        if plan.validation_errors:
            for err in plan.validation_errors:
                print(f"    ❌ {err}")
        if plan.validation_warnings:
            for warn in plan.validation_warnings:
                print(f"    ⚠️  {warn}")

        hub = plan.hub_room
        if hub:
            print(f"    Hub: {hub.area:.1f}m² ({plan.hub_percent * 100:.1f}%), "
                  f"proporcja={hub.proportion:.2f}")
        print()

    # Zapisz WSZYSTKIE warianty jako PNG
    for i, plan in enumerate(variants):
        suffix = "L" if args.notch else f"{w}x{h}"
        out_path = Path(f"output_{args.type}_{suffix}_v{i+1}.png")
        render_floor_plan(
            plan,
            title=f"{args.type} — wariant {i+1} (score: {plan.score:.3f})",
            save_path=out_path,
            show=(not args.no_show and i == 0),  # pokaż tylko pierwszy
        )
        print(f"Wariant {i+1} zapisany do {out_path}")


def cmd_rebuild_stats(args):
    """Przelicz statystyki z danych."""
    from data.dataset_loader import load_dataset
    from data.dataset_stats import compute_stats, save_stats

    ds = load_dataset()
    stats = compute_stats(ds)
    path = save_stats(stats)
    print(f"Statystyki przeliczone i zapisane do {path}")


def cmd_show_data_plan(args):
    """Wizualizuj obrysowany rzut z danych."""
    from data.dataset_loader import load_plans
    from core.models import Room, RoomSpec, Strefa, Boundary, FloorPlan, Template, AdjacencyRule
    from viz.plan_renderer import render_floor_plan
    from shapely.geometry import Polygon as SPoly

    plans = load_plans()
    plan_data = None
    for p in plans:
        if p.id == args.id:
            plan_data = p
            break

    if plan_data is None:
        print(f"Nie znaleziono rzutu {args.id}")
        print(f"Dostępne: {[p.id for p in plans]}")
        sys.exit(1)

    # Zbuduj FloorPlan z danych
    rooms = []
    for r in plan_data.rooms:
        if r.polygon:
            pts = [(p["x"], p["y"]) for p in r.polygon]
            poly = SPoly(pts)
            if poly.area < 0.1:
                continue
            strefa_map = {
                "hub": Strefa.KOMUNIKACJA,
                "salon_aneks": Strefa.DZIENNA,
                "sypialnia": Strefa.NOCNA,
                "lazienka": Strefa.USLUGOWA,
                "wc": Strefa.USLUGOWA,
                "garderoba": Strefa.USLUGOWA,
                "pralnia": Strefa.USLUGOWA,
            }
            spec = RoomSpec(
                id=r.category.value,
                nazwa=r.original_name,
                strefa=strefa_map.get(r.category.value, Strefa.KOMUNIKACJA),
                wymaga_okna=r.category.value in ("salon_aneks", "sypialnia"),
                priorytet_fasady=None,
            )
            room = Room(spec=spec, polygon=poly)
            room.update_metrics()
            rooms.append(room)

    # Obrys z bounding box
    boundary_poly = SPoly([
        (0, 0),
        (plan_data.width_m, 0),
        (plan_data.width_m, plan_data.height_m),
        (0, plan_data.height_m),
    ])
    from core.boundary_analyzer import analyze_boundary
    boundary = analyze_boundary(boundary_poly, (plan_data.width_m / 2, 0))

    template = Template(
        id="data", nazwa=f"Data: {plan_data.id}",
        typ_mieszkania=plan_data.apartment_type,
        pokoje=[r.spec for r in rooms],
        sasiedztwo=[],
    )

    fp = FloorPlan(boundary=boundary, template=template, rooms=rooms)
    from core.validator import validate
    from core.scorer import score
    validate(fp)
    score(fp)

    print(f"Rzut {plan_data.id} ({plan_data.apartment_type})")
    print(f"Score: {fp.score:.3f}")
    for r in fp.rooms:
        print(f"  {r.spec.nazwa:30s}  {r.area:.1f} m²")

    render_floor_plan(
        fp,
        title=f"Dane: {plan_data.id} ({plan_data.apartment_type}) — score: {fp.score:.3f}",
        save_path=Path(f"data_{plan_data.id}.png"),
        show=not args.no_show,
    )


def main():
    parser = argparse.ArgumentParser(description="FloorPlan4 — generator rzutów mieszkań")
    sub = parser.add_subparsers(dest="command")

    # generate
    gen = sub.add_parser("generate", help="Generuj warianty rzutu")
    gen.add_argument("--type", required=True, choices=["M1", "M2", "M3", "M4", "M5"])
    gen.add_argument("--width", type=float, default=8.0)
    gen.add_argument("--height", type=float, default=6.0)
    gen.add_argument("--entry-x", type=float, default=None)
    gen.add_argument("--entry-y", type=float, default=0.0)
    gen.add_argument("--max-variants", type=int, default=5)
    gen.add_argument("--notch", type=str, default=None,
                      help='L-kształt: "nx,ny,nw,nh" wycięcie w metrach')
    gen.add_argument("--no-show", action="store_true")

    # rebuild-stats
    sub.add_parser("rebuild-stats", help="Przelicz statystyki z danych")

    # show-data-plan
    show = sub.add_parser("show-data-plan", help="Wizualizuj rzut z danych")
    show.add_argument("--id", required=True)
    show.add_argument("--no-show", action="store_true")

    # gui
    sub.add_parser("gui", help="Uruchom interfejs graficzny")

    args = parser.parse_args()

    if args.command == "gui":
        from ui.main_window import run_gui
        run_gui()
    elif args.command == "generate":
        if args.entry_x is None:
            args.entry_x = args.width / 2
        cmd_generate(args)
    elif args.command == "rebuild-stats":
        cmd_rebuild_stats(args)
    elif args.command == "show-data-plan":
        cmd_show_data_plan(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
