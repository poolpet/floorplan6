# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Initial public release on GitHub under AGPL-3.0
- Stage 4 — apartment layout generator (CP-SAT, 7 templates M1–M5)
- Stage 3 — floor layout (deterministic geometry, walking-distance Dijkstra)
- ArchiCAD bridge via Tapir Add-On (read Wall/Slab/Zone, write Zones)
- PyQt5 desktop GUI with 4 tabs (Stages 1–4; Stages 1 & 2 are placeholders)
- Polish Building Code (WT 2002, amended 2024-08-01) hard rules:
  - F1 — 100 % outline coverage
  - F2 — bathroom max 5 m², WC max 3 m²
  - F4 — hub max 15 % of usable area
  - WT §237 — corridor min 1.4 m
  - WT §256 — walking distance ≤ 40 m for ZL IV
- 80+ unit tests, regression suite for F2 hard cap
- CI workflow (GitHub Actions) on Python 3.11/3.12/3.13
- Documentation in English: README, CONTRIBUTING, ARCHITECTURE,
  FUNDAMENTAL_RULES, LESSONS_LEARNED, OPEN_QUESTIONS, TEMPLATES_GUIDE,
  WT_PARAMETERS, FLOOR_LAYOUT_DESIGN, STATE
- Issue templates (bug, feature, design question) and PR template

### Known limitations
- Stage 3 floor layout currently supports rectangular floors only;
  L-shape / U-shape support is open for contributors
- Stages 1 (plot subdivision) and 2 (volumetric generator) are not
  implemented; UI placeholders describe what a contributor would build
- One flaky unit test (`tests/test_cpsat_solver.py::test_hub_adjacency_m3`)
  is a known issue; the underlying solver constraint is correct
