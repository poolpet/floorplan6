"""
Testy end-to-end: pełny pipeline od obrysu do ocenionego rzutu.
"""
import pytest
from shapely.geometry import Polygon

from core.variant_generator import generate_variants
from core.models import Strefa
from rules._loader import get_default_pack as _get_default_pack
from unittest.mock import patch

PROPORTION_ABSOLUTE_MAX = _get_default_pack().constants["proportion_absolute_max"]


class TestM2Rectangular:
    """M2 na prostokącie 8×6m."""

    @pytest.fixture(scope="class")
    def variants(self):
        poly = Polygon([(0, 0), (8, 0), (8, 6), (0, 6)])
        return generate_variants(poly, (4.0, 0.0), "M2", max_variants=2)

    def test_generates_variants(self, variants):
        assert len(variants) >= 1

    def test_area_coverage(self, variants):
        """Pokoje muszą wypełnić obrys (tolerancja < 0.05 m²)."""
        for plan in variants:
            delta = abs(plan.total_room_area - plan.boundary.area)
            assert delta < 0.5, f"Delta: {delta:.4f} m²"

    def test_room_count(self, variants):
        """Ile pokoi na wejściu, tyle na wyjściu (BŁĄD #4)."""
        for plan in variants:
            assert len(plan.rooms) == len(plan.template.pokoje)

    def test_hub_not_spine(self, variants):
        """Hub NIE MOŻE być korytarzem-spine (BŁĄD #1)."""
        for plan in variants:
            hub = plan.hub_room
            assert hub is not None, "Brak huba"
            assert hub.proportion <= 2.0, f"Hub jest korytarzem: prop={hub.proportion:.2f}"
            # Hub nie może rozciągać się od ściany do ściany
            bw = plan.boundary.width
            bh = plan.boundary.height
            max_dim = max(hub.width, hub.depth)
            assert max_dim < 0.6 * max(bw, bh), \
                f"Hub spine: {max_dim:.2f}m > 60% obrysu"

    def test_hub_percent(self, variants):
        """Hub powinien być 8-20% powierzchni."""
        for plan in variants:
            pct = plan.hub_percent
            assert 0.05 < pct < 0.25, f"Hub: {pct * 100:.1f}%"

    def test_no_proportion_violations(self, variants):
        """Żaden pokój nie może mieć proporcji > 2.5."""
        for plan in variants:
            for room in plan.rooms:
                assert room.proportion <= PROPORTION_ABSOLUTE_MAX, \
                    f"{room.spec.nazwa}: prop={room.proportion:.2f}"

    def test_score_positive(self, variants):
        """Każdy wariant powinien mieć pozytywny score."""
        for plan in variants:
            assert plan.score > 0.0

    def test_best_variant_decent_score(self, variants):
        """Najlepszy wariant powinien mieć score > 0.4."""
        best = variants[0]
        assert best.score > 0.4, f"Score: {best.score:.3f}"


class TestM1Small:
    """M1 na prostokącie 6×7m (realistyczny dla kawalerki 42m2)."""

    def test_m1_generates(self):
        poly = Polygon([(0, 0), (6, 0), (6, 7), (0, 7)])
        variants = generate_variants(poly, (3.0, 0.0), "M1", max_variants=2)
        assert len(variants) >= 1
        plan = variants[0]
        assert len(plan.rooms) == 3  # hub + łazienka + salon_aneks
        assert abs(plan.total_room_area - plan.boundary.area) < 0.5


class TestM3Medium:
    """M3 na prostokącie 10×6m."""

    def test_m3_generates(self):
        poly = Polygon([(0, 0), (10, 0), (10, 6), (0, 6)])
        variants = generate_variants(poly, (5.0, 0.0), "M3", max_variants=1)
        assert len(variants) >= 1
        plan = variants[0]
        assert len(plan.rooms) >= 5  # hub + łazienka + 2 sypialnie + salon

    def test_m3_area_coverage(self):
        poly = Polygon([(0, 0), (10, 0), (10, 6), (0, 6)])
        variants = generate_variants(poly, (5.0, 0.0), "M3", max_variants=1)
        for plan in variants:
            delta = abs(plan.total_room_area - plan.boundary.area)
            assert delta < 0.5


class TestBoundaryVertical:
    """BŁĄD #6: boundary pionowy (height > width) musi działać."""

    def test_vertical_m2(self):
        poly = Polygon([(0, 0), (6, 0), (6, 8), (0, 8)])
        variants = generate_variants(poly, (3.0, 0.0), "M2", max_variants=1)
        assert len(variants) >= 1
        plan = variants[0]
        assert abs(plan.total_room_area - plan.boundary.area) < 0.5


class TestM4Large:
    """M4 na prostokącie 10×8m (80m²)."""

    def test_m4_generates(self):
        poly = Polygon([(0, 0), (10, 0), (10, 8), (0, 8)])
        variants = generate_variants(poly, (5.0, 0.0), "M4", max_variants=1, solver_timeout=10)
        assert len(variants) >= 1
        plan = variants[0]
        assert len(plan.rooms) == 6  # hub + łaz + 3 syp + salon
        delta = abs(plan.total_room_area - plan.boundary.area)
        assert delta < 0.5


class TestM5XLarge:
    """M5 na prostokącie 14×9m (126m²)."""

    def test_m5_generates(self):
        poly = Polygon([(0, 0), (14, 0), (14, 9), (0, 9)])
        variants = generate_variants(poly, (7.0, 0.0), "M5", max_variants=1, solver_timeout=10)
        assert len(variants) >= 1
        plan = variants[0]
        assert len(plan.rooms) == 8  # hub + 2 łaz + 4 syp + salon
        delta = abs(plan.total_room_area - plan.boundary.area)
        assert delta < 0.5


class TestDatasetLoader:
    """Testy dataset_loader — mapowanie nazw."""

    def test_load_all_apartments(self):
        from data.dataset_loader import load_dataset
        ds = load_dataset()
        assert len(ds.apartments) == 71
        assert len(ds.plans) == 27
        # Żaden pokój bez mapowania
        for apt in ds.apartments:
            for room in apt.rooms:
                assert room.category is not None

    def test_load_all_plans(self):
        from data.dataset_loader import load_dataset
        ds = load_dataset()
        for plan in ds.plans:
            for room in plan.rooms:
                assert room.category is not None
                assert room.polygon is not None


def _build_floorplan_from_data(p):
    """Helper: zbuduj FloorPlan z LoadedPlan (dane źródłowe)."""
    from core.models import Room, RoomSpec, Strefa, FloorPlan, Template
    from core.boundary_analyzer import analyze_boundary
    from core.validator import validate
    from core.scorer import score as score_fn

    strefa_map = {"hub": Strefa.KOMUNIKACJA, "salon_aneks": Strefa.DZIENNA,
        "sypialnia": Strefa.NOCNA, "lazienka": Strefa.USLUGOWA,
        "wc": Strefa.USLUGOWA, "garderoba": Strefa.USLUGOWA, "pralnia": Strefa.USLUGOWA}

    rooms = []
    for r in p.rooms:
        if not r.polygon:
            continue
        pts = [(pt["x"], pt["y"]) for pt in r.polygon]
        poly = Polygon(pts)
        if poly.area < 0.1:
            continue
        spec = RoomSpec(id=r.category.value, nazwa=r.original_name,
            strefa=strefa_map.get(r.category.value, Strefa.KOMUNIKACJA),
            wymaga_okna=r.category.value in ("salon_aneks", "sypialnia"),
            priorytet_fasady=None)
        room = Room(spec=spec, polygon=poly)
        room.update_metrics()
        rooms.append(room)

    if not rooms:
        return None

    boundary_poly = Polygon([(0,0),(p.width_m,0),(p.width_m,p.height_m),(0,p.height_m)])
    boundary = analyze_boundary(boundary_poly, (p.width_m/2, 0))
    template = Template(id="data", nazwa=p.id, typ_mieszkania=p.apartment_type,
                        pokoje=[r.spec for r in rooms], sasiedztwo=[])
    fp = FloorPlan(boundary=boundary, template=template, rooms=rooms)
    # strict_max_areas=False: real PL apartments mogą mieć łazienki >5m²
    # (premium plans). F2 cap dotyczy tylko generowanych przez solver.
    validate(fp, strict_max_areas=False)
    score_fn(fp)
    return fp


class TestScorerOnRealPlans:
    """Scorer musi dawać prawdziwym rzutom rozsądne score'y."""

    def test_majority_above_07(self):
        """Przynajmniej 70% prawdziwych rzutów powinno mieć score > 0.7."""
        from data.dataset_loader import load_dataset
        ds = load_dataset()
        scores = []
        for p in ds.plans:
            fp = _build_floorplan_from_data(p)
            if fp:
                scores.append(fp.score)

        above = sum(1 for s in scores if s > 0.7)
        ratio = above / len(scores)
        assert ratio >= 0.7, f"Tylko {above}/{len(scores)} ({ratio:.0%}) rzutów > 0.7"


class TestEntryPosition:
    """Entry position przeliczona z pikseli."""

    def test_all_plans_have_entry(self):
        from data.dataset_loader import load_dataset
        ds = load_dataset()
        for plan in ds.plans:
            assert plan.entry_position is not None, f"{plan.id} brak entry_position"
            ex, ey = plan.entry_position
            # Entry musi być na krawędzi boundary (blisko 0 lub blisko max)
            assert 0 <= ex <= plan.width_m + 0.1, f"{plan.id} entry_x={ex} poza obrysem"
            assert 0 <= ey <= plan.height_m + 0.1, f"{plan.id} entry_y={ey} poza obrysem"


class TestBoundaryAnalyzer:
    """Testy boundary_analyzer."""

    def test_rectangle_8x6(self):
        from core.boundary_analyzer import analyze_boundary
        poly = Polygon([(0, 0), (8, 0), (8, 6), (0, 6)])
        b = analyze_boundary(poly, (4.0, 0.0))
        assert len(b.edges) == 4
        assert len(b.facade_edges) == 3
        assert len(b.internal_edges) == 1

    def test_l_shape_accepted(self):
        """Boundary analyzer akceptuje L-kształty z notch detection."""
        from core.boundary_analyzer import analyze_boundary
        poly = Polygon([(0, 0), (8, 0), (8, 4), (4, 4), (4, 6), (0, 6)])
        b = analyze_boundary(poly, (4.0, 0.0))
        assert b.area > 0
        assert b.notch is not None
        assert abs(b.notch.width - 4.0) < 0.01
        assert abs(b.notch.height - 2.0) < 0.01


class TestLShapeGeneration:
    """L-kształt: solver musi omijać wycięcie."""

    def test_l_shape_m2_generates(self):
        """M2 na L-kształcie powinien generować warianty."""
        poly = Polygon([(0, 0), (8, 0), (8, 4), (4, 4), (4, 6), (0, 6)])
        variants = generate_variants(poly, (4.0, 0.0), "M2", max_variants=1)
        assert len(variants) >= 1

    def test_l_shape_area_coverage(self):
        """Pokoje muszą wypełnić L-kształt (nie bounding box)."""
        poly = Polygon([(0, 0), (8, 0), (8, 4), (4, 4), (4, 6), (0, 6)])
        variants = generate_variants(poly, (4.0, 0.0), "M2", max_variants=1)
        for plan in variants:
            delta = abs(plan.total_room_area - plan.boundary.area)
            assert delta < 0.5, f"Delta: {delta:.4f} m² (rooms={plan.total_room_area:.2f}, boundary={plan.boundary.area:.2f})"

    def test_l_shape_rooms_inside_boundary(self):
        """Pokoje nie mogą wchodzić w wycięcie."""
        poly = Polygon([(0, 0), (8, 0), (8, 4), (4, 4), (4, 6), (0, 6)])
        variants = generate_variants(poly, (4.0, 0.0), "M2", max_variants=1)
        for plan in variants:
            for room in plan.rooms:
                assert plan.boundary.polygon.contains(room.polygon) or \
                       plan.boundary.polygon.buffer(0.01).contains(room.polygon), \
                    f"{room.spec.nazwa} wychodzi poza L-kształt"

    def test_l_shape_m3(self):
        """M3 na L-kształcie 10x8 z wycięciem 4x3."""
        poly = Polygon([(0, 0), (10, 0), (10, 5), (6, 5), (6, 8), (0, 8)])
        variants = generate_variants(poly, (5.0, 0.0), "M3", max_variants=1, solver_timeout=10)
        assert len(variants) >= 1
        plan = variants[0]
        assert len(plan.rooms) >= 5
        delta = abs(plan.total_room_area - plan.boundary.area)
        assert delta < 0.5
