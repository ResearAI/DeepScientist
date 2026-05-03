# 22 BenchStore YAML Authoring Guide

This guide explains how to add a new BenchStore catalog entry under `AISB/catalog/`,
how auto-discovery works, and which fields BenchStore actually reads today.

For packaging and publishing downloadable benchmark source bundles on GitHub
Releases, see [23 BenchStore GitHub Releases Spec](./23_BENCHSTORE_GITHUB_RELEASES_SPEC.md).

## 1. How auto-discovery works

BenchStore does not use a manual registry.

If you add a YAML file under `AISB/catalog/`, BenchStore will pick it up
automatically on the next catalog scan.

The current rules are:

- BenchStore scans `AISB/catalog/**/*.yaml` recursively.
- One YAML file represents one entry.
- `name` is the only strictly required field.
- `id` is optional. If missing, BenchStore derives it from the file stem.
- Entry ids must be unique across the whole catalog.
- Files ending in `.zh.yaml` are locale-specific variants for Chinese surfaces.
- When locale is `zh`, BenchStore prefers `<stem>.zh.yaml` over `<stem>.yaml`.
- The `.zh.yaml` file is a full replacement, not a partial override.

Examples:

- `AISB/catalog/my.benchmark.yaml`
- `AISB/catalog/my.benchmark.zh.yaml`
- `AISB/catalog/vision/my.benchmark.yaml`

Recommended naming rule:

- Keep the file stem identical to the intended entry id.
- Use only letters, numbers, `.`, `_`, and `-` in the stem.

## 2. Quick start: create a new YAML entry

### Minimal entry

This is the smallest valid file:

```yaml
name: My Benchmark
```

That entry will appear in BenchStore, but it will be very bare.

### Recommended starter template

Use this as the normal starting point:

```yaml
schema_version: 1
id: my.benchmark
name: My Benchmark
version: 0.1.0

one_line: One-sentence summary shown in cards and compact views.
task_description: >
  A longer description used by the detail view and BenchStore setup flow.

task_mode: evaluation_driven
requires_execution: true
requires_paper: true

capability_tags:
  - scientific_discovery
track_fit:
  - benchmark_track

time_band: 1-2h
cost_band: medium
difficulty: medium
data_access: public

snapshot_status: runnable
support_level: advanced

resources:
  minimum:
    cpu_cores: 8
    ram_gb: 16
    disk_gb: 50
    gpu_count: 1
    gpu_vram_gb: 12
  recommended:
    cpu_cores: 16
    ram_gb: 32
    disk_gb: 100
    gpu_count: 1
    gpu_vram_gb: 24

paper:
  title: My Benchmark Paper
  venue: NeurIPS 2026
  year: 2026
  url: https://example.com/paper

download:
  url: https://example.com/my.benchmark.zip
  archive_type: zip
  local_dir_name: my.benchmark

image_path: ../../../AISB/image/my.benchmark.jpg
```

### Chinese localization

If you want a Chinese catalog entry, create a second file with the same stem:

- `AISB/catalog/my.benchmark.yaml`
- `AISB/catalog/my.benchmark.zh.yaml`

Important:

- `my.benchmark.zh.yaml` must contain a complete entry.
- BenchStore does not merge the Chinese file onto the English file.
- If you only put translated fragments into `.zh.yaml`, missing fields will really be missing.

## 3. Exact requirements and conventions

### 3.1 Hard requirements

The following are hard requirements or hard runtime behaviors in the current implementation:

- The YAML root must be an object, not a plain string or list.
- `name` must be a non-empty string.
- If `id` is present, it should be a string. If omitted, BenchStore derives it from the file stem.
- The final resolved `id` must be unique across the whole catalog.
- `.zh.yaml` fully replaces the matching English file. It is not merged field-by-field.
- `capability_tags`, `track_fit`, `primary_outputs`, `risk_flags`, `risk_notes`, `environment.key_packages`, `environment.notes`, `dataset_download.notes`, `credential_requirements.items`, `credential_requirements.notes`, and `launch_profiles` must be lists.
- If present, `resources.minimum` and `resources.recommended` must be objects.
- If present, `environment`, `dataset_download`, `credential_requirements`, `paper`, `download`, `display`, and `commercial` must be objects.
- Every item in `launch_profiles` must be an object.
- `download.url` is the true minimum field required by the install flow. Without it, BenchStore install cannot run.

### 3.2 Recommended conventions

These are not strict validator rules, but if you want stable entries, predictable recommendations, and low maintenance cost, you should follow them closely.

**Base conventions**

- `schema_version`: always write `1`.
- `id`: make it identical to the file stem. For example, if the file is `aisb.t3.026_gartkg.yaml`, write `id: aisb.t3.026_gartkg`.
- `id` style: prefer lowercase, stable identifiers, using only letters, numbers, `.`, `_`, and `-`.
- `version`: prefer semver such as `0.1.0` or `0.2.3`.
- `requires_execution` and `requires_paper`: write YAML booleans `true` / `false`, not natural-language strings.

**Writing conventions**

- `name`: primary user-facing title; prefer the official benchmark or project name.
- `one_line`: one sentence suitable for a card; do not turn it into a long paragraph.
- `task_description`: usually 1 to 3 paragraphs describing what this benchmark actually means inside DeepScientist, not just a copy of the paper abstract.
- `recommended_when` / `not_recommended_when`: write complete sentences describing fit and non-fit conditions.

**Canonical values recognized by recommendation logic**

- `cost_band`: prefer only `very_low`, `low`, `medium`, `high`, `very_high`.
- `difficulty`: prefer only `easy`, `medium`, `hard`, `expert`.
- `data_access`: prefer only `public`, `restricted`, `private`.
- `snapshot_status`: prefer only `runnable`, `runnable_not_verified`, `partial`, `restore_needed`, `external_eval_required`, `data_only`.
- `support_level`: prefer only `turnkey`, `advanced`, `recovery`.

Important:

- `cost_band`, `difficulty`, `snapshot_status`, and `support_level` are not hard-enforced enums, but the recommendation logic only assigns special meaning to these canonical values.
- If you write another string, the entry will still load, but recommendation behavior will usually fall back to unknown/default handling.

**`time_band` format**

BenchStore currently parses these formats reliably:

- single value: `30m`, `2h`, `3d`
- closed range: `30-60m`, `1-2h`, `2-4d`
- open-ended range: `6h+`, `1d+`, `4d+`

Guidance:

- estimate the first credible end-to-end wall-clock run
- prefer normalized no-space forms like `1-2h` instead of natural-language text such as "about one day"

**Resource conventions**

- Inside `resources.minimum` and `resources.recommended`, BenchStore currently reads only these five numeric keys:
- `cpu_cores`
- `ram_gb`
- `disk_gb`
- `gpu_count`
- `gpu_vram_gb`

Notes:

- Keep them numeric.
- Even if you add extra keys such as `notes` inside `resources.minimum`, current compatibility logic does not use them.
- Put explanatory prose into `task_description` or `environment.notes` instead.

**Download conventions**

- `download.url`: must point to a concrete downloadable asset.
- `download.archive_type`: prefer only `zip`, `tar.gz`, or `tar`.
- `download.local_dir_name`: make it match the unpacked root directory; in most cases it should also match the entry id.
- For GitHub Releases distribution, also fill `download.provider`, `download.repo`, `download.tag`, `download.asset_name`, `download.sha256`, and `download.size_bytes`.

**Image and localization conventions**

- `image_path`: prefer a path relative to the YAML file; the resolved file must exist and stay inside the current workspace.
- `.zh.yaml`: duplicate the full English entry first, then translate only the text-bearing fields; do not write a partial Chinese delta file.

**Risk conventions**

- Fill `risk_flags` and `risk_notes` only when there are real caveats worth surfacing.
- As soon as an entry has `risk_flags` or `risk_notes`, BenchStore recommendation logic excludes it from recommended results.

### 3.3 What to fill, by outcome

### Enough to show up in BenchStore

Required:

- `name`

Strongly recommended:

- `id`
- `one_line`
- `task_description`

### Enough to rank, filter, and recommend well

These fields materially affect catalog quality:

- `task_mode`
- `capability_tags`
- `aisb_direction`
- `track_fit`
- `cost_band`
- `time_band`
- `difficulty`
- `data_access`
- `resources.minimum`
- `resources.recommended`
- `snapshot_status`
- `support_level`

Notes:

- `resources.minimum` and `resources.recommended` drive device-fit checks.
- `snapshot_status` and `support_level` affect recommendation scoring.
- `risk_flags` and `risk_notes` mark known caveats.
- Entries with `risk_flags` or `risk_notes` are excluded from BenchStore recommendations.

### Enough to be installable from BenchStore

Strict minimum for the install flow:

- `download.url`

Strongly recommended:

- `download.archive_type`
- `download.local_dir_name`
- `download.provider`
- `download.repo`
- `download.tag`
- `download.asset_name`
- `download.sha256`
- `download.size_bytes`

Important behavior:

- If `requires_execution: true`, BenchStore launch is blocked until the entry is installed locally.
- If `download.archive_type` is omitted, BenchStore tries to infer it from the URL suffix.
- If `download.local_dir_name` is omitted, BenchStore falls back to the entry id.

### Helpful metadata for detail pages and setup packets

Useful fields:

- `paper`
- `primary_outputs`
- `launch_profiles`
- `dataset_download`
- `credential_requirements`
- `environment`
- `recommended_when`
- `not_recommended_when`
- `image_path`
- `homepage`
- `official_links`
- `discovery`
- `display`
- `commercial`

## 4. Supported keys today

BenchStore currently reads these top-level keys:

- `schema_version`
- `id`
- `name`
- `homepage`
- `version`
- `one_line`
- `task_description`
- `capability_tags`
- `aisb_direction`
- `track_fit`
- `task_mode`
- `requires_execution`
- `requires_paper`
- `integrity_level`
- `snapshot_status`
- `support_level`
- `primary_outputs`
- `launch_profiles`
- `cost_band`
- `time_band`
- `difficulty`
- `data_access`
- `risk_flags`
- `risk_notes`
- `recommended_when`
- `not_recommended_when`
- `paper`
- `download`
- `dataset_download`
- `credential_requirements`
- `resources`
- `environment`
- `commercial`
- `official_links`
- `discovery`
- `display`
- `image_path`

Nested objects currently recognized:

- `paper.title`
- `paper.venue`
- `paper.year`
- `paper.url`
- `download.url`
- `download.archive_type`
- `download.local_dir_name`
- `download.provider`
- `download.repo`
- `download.tag`
- `download.asset_name`
- `download.sha256`
- `download.size_bytes`
- `dataset_download.primary_method`
- `dataset_download.sources[].kind`
- `dataset_download.sources[].url`
- `dataset_download.sources[].access`
- `dataset_download.sources[].note`
- `dataset_download.notes[]`
- `credential_requirements.mode`
- `credential_requirements.items[]`
- `credential_requirements.notes[]`
- `resources.minimum.cpu_cores`
- `resources.minimum.ram_gb`
- `resources.minimum.disk_gb`
- `resources.minimum.gpu_count`
- `resources.minimum.gpu_vram_gb`
- `resources.recommended.cpu_cores`
- `resources.recommended.ram_gb`
- `resources.recommended.disk_gb`
- `resources.recommended.gpu_count`
- `resources.recommended.gpu_vram_gb`
- `environment.python`
- `environment.cuda`
- `environment.pytorch`
- `environment.flash_attn`
- `environment.key_packages[]`
- `environment.notes[]`
- `commercial.annual_fee`
- `display.palette_seed`
- `display.art_style`
- `display.accent_priority`
- `display.placement`
- `display.card_size`
- `display.badge`
- `official_links.homepage`
- `official_links.github`
- `official_links.docs`
- `discovery.collection`
- `discovery.collection_priority`
- `discovery.recommendation_weight`
- `discovery.featured`
- `discovery.featured_reason`
- `launch_profiles[].id`
- `launch_profiles[].label`
- `launch_profiles[].description`

If you add extra keys beyond this set, they are preserved in `raw_payload` for downstream
consumers but do not affect the current UI, installer, or recommendation logic directly.
To propose a new first-class field, open an RFC issue and update this reference doc alongside
the `service.py` and `prompt_builder.py` changes.

## 5. Fields you should not write manually

BenchStore generates these fields itself:

- `source_file`
- `image_url`
- `search_text`
- `install_state`
- `compatibility`
- `recommendation`
- `setup_prompt_preview`
- `raw_payload`

Also note:

- `schema_version` defaults to `1` if omitted.
- `id` is auto-derived from the file stem if omitted.

## 6. Common mistakes

### Partial `.zh.yaml` files

Wrong approach:

- English file has all fields.
- Chinese file contains only `name` and `one_line`.

Result:

- the Chinese surface loses every other field, because the Chinese YAML fully replaces
  the base file.

### Duplicate ids

If two files resolve to the same `id`, BenchStore marks the later one invalid.

### Wrong collection types

These must be lists if present:

- `capability_tags`
- `track_fit`
- `primary_outputs`
- `risk_flags`
- `risk_notes`
- `environment.key_packages`
- `environment.notes`
- `dataset_download.sources`
- `dataset_download.notes`
- `credential_requirements.items`
- `credential_requirements.notes`
- `launch_profiles`

### Invalid image paths

`image_path` is resolved relative to the YAML file unless you use an absolute path.
The resolved file must stay inside the DeepScientist workspace and actually exist.

## 7. How to verify a new entry

After creating or editing a YAML file, you can verify it in any of these ways:

- Open BenchStore in the web UI and check whether the card appears.
- Call `GET /api/benchstore/entries` and confirm the entry is listed.
- Call `GET /api/benchstore/entries/<entry_id>` and inspect the normalized payload.
- Check `invalid_entries` in the catalog response if an entry does not appear.

There is no extra registration step. Creating the file is the registration step.
