# Contributing to FloorPlan6

Thanks for your interest in this project. Please read this short guide before
opening a pull request — it will save us both time.

## TL;DR

1. **Open a GitHub Discussion or Issue first** for non-trivial changes. We
   want to agree on architecture before code is written.
2. **Read [`docs/FUNDAMENTAL_RULES.md`](docs/FUNDAMENTAL_RULES.md).** Rules
   F1–F10 (architectural) and B1–B10 (workflow) are **non-negotiable**.
3. **Add a regression test** when you fix a bug.
4. **Two failed attempts on the same module → rewrite, don't keep patching.**
   This is rule B1, learned the hard way (see `docs/LESSONS_LEARNED.md`).
5. Keep all new code, comments, and docs **in English**. The project author
   speaks Polish but the codebase is intentionally English-only so it can
   accept contributions from anywhere.

## Setting up the dev environment

```bash
git clone https://github.com/<your-username>/floorplan6.git
cd floorplan6
python3 -m venv venv
source venv/bin/activate    # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Verify everything works
PYTHONPATH=. pytest tests/ -q
PYTHONPATH=. python ui/main_window.py
```

## Development workflow

### 1. Pick or create an issue
- Browse [open issues](https://github.com/poolpet/floorplan6/issues) and
  [Discussions](https://github.com/poolpet/floorplan6/discussions).
- For new ideas: open a Discussion in *Ideas* category first.
- For bugs: open an Issue with steps to reproduce.

### 2. Fork and branch
```bash
git checkout -b feature/<short-name>     # or fix/<short-name>
```

### 3. Code with the rules in mind
- Architectural rules **F1–F10** are inviolable. Examples:
  - F1: 100 % coverage of the floor outline (`sum(rooms) == usable_area`)
  - F2: bathroom max 5 m², WC max 3 m²
  - F4: hub max 15 % of usable area, aspect ≤ 1.5
- Workflow rules **B1–B10** govern how we work:
  - B1: two failed attempts on the same area → rewrite the module from
    scratch with a different approach
  - B2: write a plain-language plan before changing code
  - B3: do **not** weaken a rule to make a solver feasible

### 4. Add tests
- Unit tests in `tests/`
- For solver changes: regression scenarios proving the new behaviour without
  breaking previous ones
- Run `PYTHONPATH=. pytest tests/ -v` before pushing

### 5. Commit and push
- Use clear commit messages explaining the *why*, not just the *what*
- Reference the issue: `Fixes #42`
- Push to your fork: `git push origin feature/<short-name>`

### 6. Open a Pull Request
- Fill in the PR template (checklist of tests, documentation, rules)
- Mark as **Draft** if you want early feedback
- Expect review comments — this is a small project, reviews focus on
  architectural fit more than style

## What we are looking for

### High-impact areas (open invitation)

- **Stage 1 — plot subdivision** (MPZP zoning analysis). See `Q1`–`Q5` in
  `docs/OPEN_QUESTIONS.md`. ~2–3 weeks for an MVP.
- **Stage 2 — volumetric generator** (3D massing from a footprint).
  ~1–2 weeks for an MVP.
- **L-shape / U-shape support in `floor_layout.py`** — current MVP assumes
  rectangular floors only. ~2–3 hours to add proper sub-rectangle handling.
- **Wall + door export to ArchiCAD** — currently we export Zones only.
  Real walls and Door elements would close the loop. ~2 hours.
- **English translation of remaining Polish doc strings** in
  `docs/ARCHITECTURE.md`, `docs/FUNDAMENTAL_RULES.md`,
  `docs/LESSONS_LEARNED.md`, `docs/OPEN_QUESTIONS.md`.

### What we will reject

- Patches that bend a rule (F1–F10) to make a solver "work". The rule wins;
  fix the approach instead.
- Patches without a corresponding test.
- A third attempt at the same broken approach (rule B1: rewrite instead).
- New abstraction layers without a concrete user.
- New features added on top of known bugs (fix the bug first).

## Architectural decisions

For decisions that affect the building behaviour (e.g. which apartment type
absorbs excess area, how walking distances are validated), open a
**Discussion** of category *Q&A → Design questions*. The project owner
(Dawid, an architect) makes the call. Document the answer in
`docs/OPEN_QUESTIONS.md` and reference it in the code.

## Questions?

Open a Discussion or @-mention `@poolpet` on an issue.
