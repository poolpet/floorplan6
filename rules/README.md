# Code Packs

Code packs hold country-specific rules + constants. The reference pack is
`rules/PL/` (Polska, WT 2002).

## Pack structure

```
rules/{PACK_ID}/
├── pack.yaml          # Manifest (id, version, locale, references, file list)
├── wt_rules.json      # Verifier rules (analogous to PL's wt_rules.json)
├── constants.yaml     # Rule-driven constants (extracted from config.py)
└── user_rules.json    # User MPZP overrides (default: empty list)
```

## Manifest schema (`pack.yaml`)

Validated by `rules._schema.PackManifest`:

| Field | Required | Description |
|---|---|---|
| `code_pack_id` | yes | Pack ID, e.g. "PL", "UK" |
| `country_code` | yes | ISO country code |
| `locale` | yes | POSIX locale, e.g. `pl_PL` |
| `version` | yes | Pack version (semver-ish) |
| `version_compat` | yes | FloorPlan6 version range |
| `display_name` | yes | Human-readable PL name |
| `display_name_en` | no | English fallback |
| `description` | yes | One-line description |
| `references` | no | Legal/regulatory references |
| `files` | no | File mapping (defaults to standard names) |

## Constants schema (`constants.yaml`)

Validated by `rules._schema.PackConstants`. **All keys required** — see
`rules/_schema.py` for the full list. Adding a new constant requires:

1. Add field to `PackConstants` model
2. Add value to every existing pack's `constants.yaml` (or set default)
3. Update consuming code to read from `pack.constants[...]`

## Adding a new pack (e.g. UK)

1. Copy `rules/PL/` to `rules/UK/`
2. Edit `rules/UK/pack.yaml`: change `code_pack_id`, `locale`, `version`,
   `display_name`, `references` (to UK Building Regulations citations)
3. Translate/adapt `wt_rules.json` to UK BR equivalents (rule IDs typically
   prefixed `uk_001`, `uk_002`, ...)
4. Adapt `constants.yaml` (UK uses different setbacks, FAR vs WIZ, etc.)
5. Validate: `python -c "from rules._loader import load_pack; load_pack('UK')"`
6. Add tests: copy `tests/test_pack_loader.py::TestLoadPackHappyPath` patterns

## Loading a pack at runtime

```python
from rules._loader import load_pack

pack = load_pack("PL")  # default
pack.rules                # parsed wt_rules.json
pack.constants            # parsed constants.yaml dict
pack.constants["wt_max_area"]["bathroom_m2"]  # 5.0
pack.user_overrides       # parsed user_rules.json
pack.manifest             # Pydantic PackManifest model
pack.path                 # Path to rules/PL/
```

## Constraints (NOT implemented yet, by design)

- **NO runtime hot-swap** between packs — load once at session start
- **NO generic constraint engine** — F1-F10 stay hardcoded in solver/validator
- **NO i18n in pack** — locale string is metadata only, UI translation is
  separate concern (Phase 3+)
