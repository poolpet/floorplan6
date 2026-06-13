"""NETTO/BRUTTO (S30, decyzja Dawida 2026-06-12): obrys wejściowy to BRUTTO,
liczby korpusowe (capy ARCHON, progi selektorów, tabele rzutów) to NETTO.

Spina je `NET_FACTOR ≈ 0.81` (kotwica: A01_120 — 97 m² NETTO przy ~120 brutto;
rekalibracja po pełnej ekstrakcji 36 PDF):
  - selektory pokoi parteru dostają NETTO (progi wyrażone w netto, te same
    punkty decyzji co dotąd: gabinet ≥93 ≈ 115 gross, garaż ≥97 = korpusowe
    97 netto ≈ 120 gross),
  - capy programu egzekwowane na brutto jako cap/NET_FACTOR (salon 35 netto
    ≈ 43.2 rysowanych m²; day-zone 45 netto ≈ 55.6),
  - pokoje MOKRE bez zmian: F2/WT to twarde capy prawne (łazienka 5/8, wc 3)
    — NIE wolno ich skalować (FUNDAMENTAL_RULES F2/B3).

Poddasze: bez netto-przelicznika w selektorach — powierzchnia EFEKTYWNA
(pełna − 0.5·stref niskich) już odpowiada normie PL (S29: 55 vs 53.8 ✓);
capy poddasza skalowane jak parteru (pełne pokrycie brutto).
"""
import pytest

from core.house_layout import NET_FACTOR, _gross_config, net_area, parter_room_ids, _template
from core.house_program import compute_house_targets, default_house_config


def test_net_factor_anchored_in_corpus_range():
    # ściany ~15-20% brutto; kotwica A01_120: 97/120 = 0.808
    assert 0.75 <= NET_FACTOR <= 0.85
    assert net_area(120.0) == pytest.approx(120.0 * NET_FACTOR)


def test_parter_selector_decisions_preserved_via_net():
    """Te same punkty decyzji co w S29 (gross 115/120), wyrażone w netto."""
    tpl = _template("house_parter")
    small = parter_room_ids(tpl.pokoje, net_area(63.0))    # 51 netto
    mid = parter_room_ids(tpl.pokoje, net_area(115.0))     # ~93 netto
    big = parter_room_ids(tpl.pokoje, net_area(120.0))     # ~97 netto (korpus A01_120)
    assert "gabinet" not in small and "garaz" not in small
    assert "gabinet" in mid and "garaz" not in mid
    assert "gabinet" in big and "garaz" in big


def test_gross_config_scales_dry_caps_only():
    cfg = _gross_config(default_house_config(storey="parter"))
    base = default_house_config(storey="parter")
    assert cfg.caps["salon"] == pytest.approx(base.caps["salon"] / NET_FACTOR)
    assert cfg.caps["garaz"] == pytest.approx(base.caps["garaz"] / NET_FACTOR)
    # F2/WT: mokre pokoje NIE skalowane
    assert cfg.caps["wc"] == base.caps["wc"]
    assert cfg.bathroom_parter_max == 5.0
    assert cfg.bathroom_poddasze_max == 8.0
    # day-zone: max skalowany, udział procentowy bez zmian
    assert cfg.day_zone_cap_max == pytest.approx(base.day_zone_cap_max / NET_FACTOR)
    assert cfg.day_zone_cap_pct == base.day_zone_cap_pct


def test_day_zone_targets_use_gross_cap():
    """Na 157 m² brutto strefa dzienna może urosnąć ponad stary netto-cap 45
    (45 netto ≈ 55.6 rysowanych), ale nie ponad przeliczony."""
    tpl = _template("house_parter")
    cfg = _gross_config(default_house_config(storey="parter"))
    targets = compute_house_targets(tpl.pokoje, 157.0, cfg)
    day = targets["salon"] + targets["kuchnia"]
    assert day <= 45.0 / NET_FACTOR + 1e-6
    assert day > 45.0, "gross-cap powinien puścić strefę dzienną ponad netto-owe 45"
