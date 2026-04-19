# 22 BenchStore YAML Reference

This document defines the YAML contract for BenchStore catalog entries under:

- `AISB/catalog/*.yaml`

BenchStore reads these files directly, validates them, and exposes them through the
BenchStore API.

The frontend is intentionally tolerant at render time:

- only fields that actually exist are rendered
- missing optional fields are simply omitted from the UI
- only `name` is strictly required

## 1. File placement

Put one benchmark entry in one file:

- `AISB/catalog/aisb.t3.026_gartkg.yaml`
- `AISB/catalog/my_custom_benchmark.yaml`

Subdirectories are also allowed. BenchStore scans `AISB/catalog/` recursively.
For the curated AutoSOTA batch, keep files flat directly under `AISB/catalog/`
instead of reintroducing an `autosota/` subdirectory.

## 2. Minimal valid example

```yaml
name: My Benchmark
```

That is the only mandatory field.

## 3. Recommended example

```yaml
schema_version: 1
id: aisb.t3.tdc_admet
name: TDC ADMET Discovery
version: 0.1.0
one_line: Evaluate whether an AI Scientist can improve molecular property prediction through hypothesis-driven experiments.

capability_tags:
  - scientific_discovery
  - hypothesis_experiment_validation

aisb_direction: T3
track_fit:
  - paper_track
  - benchmark_track

task_mode: experiment_driven
requires_execution: true
requires_paper: true
integrity_level: cas_plus_canary

cost_band: low
time_band: 1-2h
difficulty: medium
data_access: public

recommended_when: Use this benchmark to test hypothesis-driven experimental improvement with real logged experiments.
not_recommended_when: Do not use this for pure reasoning, theorem proving, or long-horizon software engineering.

paper:
  title: Thermotherapeutics Data Commons: Machine Learning Datasets and Tasks for Drug Discovery and Development
  venue: NeurIPS 2021 Datasets and Benchmarks
  year: 2021
  url: https://openreview.net/forum?id=8nvgnORnoWr

download:
  provider: github_release
  repo: ResearAI/DeepScientist
  tag: benchstore-assets-2026-04-13
  asset_name: aisb.t3.tdc_admet-v0.1.0.zip
  url: https://github.com/ResearAI/DeepScientist/releases/download/benchstore-assets-2026-04-13/aisb.t3.tdc_admet-v0.1.0.zip
  archive_type: zip
  local_dir_name: aisb.t3.tdc_admet
  version: 0.1.0
  sha256: <sha256>
  size_bytes: 12345678

resources:
  minimum:
    cpu_cores: 8
    ram_gb: 16
    disk_gb: 20
    gpu_count: 1
    gpu_vram_gb: 8
  recommended:
    cpu_cores: 16
    ram_gb: 32
    disk_gb: 50
    gpu_count: 1
    gpu_vram_gb: 16

environment:
  python: "3.10"
  cuda: "11.8"
  pytorch: "2.1.0"
  flash_attn: null
  key_packages:
    - deepspeed==0.15.4
    - transformers==4.46.3
  notes:
    - Use the repository requirements file for the full dependency set.

commercial:
  annual_fee: null

display:
  palette_seed: sage-coral-mist
  art_style: morandi-minimal
  accent_priority: high
```

## 4. Field reference

### Required

**`name`**

- Type: `string`
- Required: yes
- Purpose: primary user-facing benchmark name

### Strongly recommended

**`id`**

- Type: `string`
- Required: no
- Recommended: yes
- Example: `aisb.t3.026_gartkg`
- Rule: if omitted, BenchStore derives it from the file stem
- Best practice: keep it identical to the file stem unless you intentionally need a
  compatibility alias

**`one_line`**

- Type: `string`
- Required: no
- Purpose: short summary used on cards and compact views

**`task_description`**

- Type: `string`
- Required: no
- Purpose: longer detail-page description and setup-agent context

**`image_path`**

- Type: `string`
- Required: no
- Purpose: relative path to a representative JPG cover image for the benchmark
- Guidance: prefer a repo-relative path such as `../../../AISB/image/001_aisb.t3.001_savvy.jpg`

### Classification and discovery

**`capability_tags`**

- Type: `string[]`
- Required: no
- Example: `["scientific_discovery", "drug_discovery"]`

**`aisb_direction`**

- Type: `string`
- Required: no
- Example: `T1`, `T2`, `T3`

**`track_fit`**

- Type: `string[]`
- Required: no
- Example: `["paper_track", "benchmark_track"]`

**`task_mode`**

- Type: `string`
- Required: no
- Example: `experiment_driven`, `analysis_driven`, `evaluation_driven`

### Runtime intent

**`requires_execution`**

- Type: `boolean`
- Required: no
- Meaning: whether the benchmark normally expects actual code or experiment execution

**`requires_paper`**

- Type: `boolean`
- Required: no
- Meaning: whether paper-quality output is normally part of success

**`integrity_level`**

- Type: `string`
- Required: no
- Example: `cas_plus_canary`

### Planning hints

**`cost_band`**
Important release note:

- if an entry is published as a downloadable source package, keep `risk_flags` and `risk_notes` unchanged; release availability must not erase known caveats


- Type: `string`
- Required: no
- Example: `low`, `medium`, `high`

**`time_band`**

- Type: `string`
- Required: no
- Example: `30-60m`, `1-2h`, `1d+`, `2-4d`, `4d+`
- Guidance: estimate wall-clock for a first credible end-to-end run on recommended hardware, including required setup, major evaluation, and paper-faithful stages; use minute / hour / day ranges for bounded tasks, and open-ended values like `1d+` or `4d+` when the benchmark routinely spans multiple days

**`difficulty`**

- Type: `string`
- Required: no
- Example: `easy`, `medium`, `hard`

**`data_access`**

- Type: `string`
- Required: no
- Example: `public`, `restricted`, `private`

**`recommended_when`**

- Type: `string`
- Required: no

**`not_recommended_when`**

- Type: `string`
- Required: no

### Paper metadata

**`paper.title`**

- Type: `string`
- Required: no

**`paper.venue`**

- Type: `string`
- Required: no
- This is the preferred field for "paper venue / accepted venue / publication place"

**`paper.year`**

- Type: `integer`
- Required: no

**`paper.url`**

- Type: `string`
- Required: no

### Download metadata

**`download.url`**

- Type: `string`
- Required: no
- Guidance: for DeepScientist-curated mirrors, prefer
  `https://deepscientist.cc/AISB/<three-digit>_<slug>` instead of an upstream GitHub
  archive link

**`download.archive_type`**

- Type: `string`
- Required: no
- Example: `zip`, `tar.gz`

**`download.local_dir_name`**

- Type: `string`
- Required: no
- Preferred install directory name after download and extraction

### Dataset acquisition metadata

Use this block when the benchmark depends on one or more concrete dataset routes. BenchStore can now surface
these details directly in the frontend and setup-agent context.

Recommended shape:

```yaml
dataset_download:
  primary_method: mixed
  sources:
    - kind: huggingface
      url: https://huggingface.co/datasets/example/bench
      access: public
      note: Primary public dataset route.
  notes:
    - Requires converting the raw split into project-specific JSON files.
```

Supported keys by convention:

- `dataset_download.primary_method`: `string`
- `dataset_download.sources`: `object[]`
- `dataset_download.notes`: `string[]`
- `dataset_download.sources[].kind`: `string | null`
- `dataset_download.sources[].url`: `string | null`
- `dataset_download.sources[].access`: `string | null`
- `dataset_download.sources[].note`: `string | null`

### Credential metadata

Use this when the benchmark depends on API keys, gated model tokens, Kaggle credentials, or similar secrets.

Recommended shape:

```yaml
credential_requirements:
  mode: conditional
  items:
    - OPENAI_API_KEY
    - HF_TOKEN
  notes:
    - OpenAI access is only needed for the optional evaluator route.
```

Supported keys by convention:

- `credential_requirements.mode`: `string`
- `credential_requirements.items`: `string[]`
- `credential_requirements.notes`: `string[]`

### Runtime state metadata

These fields help the frontend present a Steam-like benchmark detail page with clearer status and launch guidance.

**`snapshot_status`**

- Type: `string`
- Required: no
- Example: `runnable`, `partial`, `docs_only`, `restore_needed`, `external_eval_required`
- Guidance: describe what the current local snapshot can realistically do today, not what the upstream paper could do in principle.

**`support_level`**

- Type: `string`
- Required: no
- Example: `turnkey`, `advanced`, `recovery`
- Guidance: use this to indicate whether the benchmark is ready to run, requires careful multi-step setup, or mainly needs source restoration and audit work.

**`primary_outputs`**

- Type: `string[]`
- Required: no
- Example: `["aid_accuracy", "model_checkpoint", "evaluation_report"]`
- Guidance: list the most important measurable outputs or artifacts a user should expect after a credible run.

**`launch_profiles`**

- Type: `object[]`
- Required: no
- Recommended shape:

```yaml
launch_profiles:
  - id: quick_check
    label: Quick Check
    description: Run the smallest safe route on the current device.
  - id: paper_faithful
    label: Paper-Faithful
    description: Run the full reproduction path described by the paper.
```

Supported subfields:

- `launch_profiles[].id`: `string | null`
- `launch_profiles[].label`: `string | null`
- `launch_profiles[].description`: `string | null`

### Resource requirements

Use structured machine-readable fields here. Do not write only natural-language hardware prose if
you want compatibility scoring, ranking, or automatic filtering to work.

**`resources.minimum`**

- Type: object
- Required: no

**`resources.recommended`**

- Type: object
- Required: no

Supported subfields:

- `cpu_cores`: number
- `ram_gb`: number
- `disk_gb`: number
- `gpu_count`: number
- `gpu_vram_gb`: number

Example:

```yaml
resources:
  minimum:
    cpu_cores: 8
    ram_gb: 16
    disk_gb: 20
    gpu_count: 1
    gpu_vram_gb: 8
  recommended:
    cpu_cores: 16
    ram_gb: 32
    disk_gb: 50
    gpu_count: 1
    gpu_vram_gb: 16
```

### Optional environment metadata

Use this when reproducibility depends on a narrow runtime stack.

Recommended shape:

```yaml
environment:
  python: "3.10"
  cuda: "11.8"
  pytorch: "2.1.0"
  flash_attn: "2.7.0.post2"
  key_packages:
    - deepspeed==0.15.4
    - transformers==4.46.3
  notes:
    - Install from requirements.txt for the full dependency set.
```

Supported keys by convention:

- `environment.python`: `string`
- `environment.cuda`: `string | null`
- `environment.pytorch`: `string | null`
- `environment.flash_attn`: `string | null`
- `environment.key_packages`: `string[]`
- `environment.notes`: `string[]`

Guidance:

- Prefer exact versions when the upstream repo specifies them.
- Use `null` when a component is not required or unknown.
- Keep `key_packages` short and high-signal instead of copying the full lockfile.
- Use `notes` for install constraints such as CPU-only support, `nvcc` requirement, or external toolkit prerequisites.

### Optional image metadata

If you have a benchmark preview image, you may store it as a relative path:

```yaml
image_path: ../../../AISB/image/026_aisb.t3.026_gartkg.jpg
```

Guidance:

- Prefer `jpg` images under 100KB when possible.
- Prefer 16:9 crops for consistent gallery presentation.
- Prefer naming the image `<three-digit>_<yaml_stem>.jpg` so it remains mechanically
  aligned with the YAML file.
- Prefer a README main figure first.
- If README does not expose a suitable figure, use the paper PDF main figure.
- If a clean main figure is unavailable, fall back to a cropped first-page preview.

## 5. Curated AutoSOTA Profile

For the manually curated AutoSOTA batch, use the following conventions together:

- YAML path: `AISB/catalog/aisb.t3.026_gartkg.yaml`
- `id: aisb.t3.026_gartkg`
- `download.url: https://deepscientist.cc/AISB/026_gartkg`
- `image_path: ../../../AISB/image/026_aisb.t3.026_gartkg.jpg`

Authoring guidance for this batch:

- `task_description` should mention the actual local repo or optimization evidence,
  not just restate the paper abstract.
- `resources.minimum` and `resources.recommended` should be conservative operational
  estimates, especially for GPU VRAM and disk usage.
- `environment` should only contain versions that are explicitly supported by local
  README, requirements, environment manifests, or clearly stated install commands.
- When an exact version is unknown, prefer `null` over guesses.

### Commercial metadata

**`commercial.annual_fee`**

- Type: `string | number | null`
- Required: no
- Example: `99`, `"$99/year"`, `null`

### Display hints

These are optional hints for BenchStore rendering. The frontend may ignore them when a future design
system changes, but they are safe to include.

**`display.palette_seed`**

- Type: `string`
- Required: no

**`display.art_style`**

- Type: `string`
- Required: no
- Example: `morandi-minimal`

**`display.accent_priority`**

- Type: `string`
- Required: no
- Example: `low`, `medium`, `high`

## 6. Validation behavior

BenchStore follows these rules:

- `name` must exist and be a non-empty string
- all other fields are optional
- unknown extra fields are preserved but may not be rendered yet
- invalid files are skipped from the main catalog response and reported as catalog errors

## 7. Authoring guidance

Prefer:

- short stable identifiers
- real structured resource values
- concise `one_line`
- longer `task_description` only when detail is useful
- `paper.venue` instead of ad hoc keys like `accepted_place`

Avoid:

- giant blobs of prompt text inside the YAML
- natural-language-only hardware descriptions
- mixing install state into catalog files
- storing local absolute paths in catalog entries
