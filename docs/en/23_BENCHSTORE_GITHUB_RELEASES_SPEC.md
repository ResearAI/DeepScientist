# 23 BenchStore GitHub Releases Spec

This document defines the **release and distribution contract** for BenchStore benchmark source packages when the delivery backend is **GitHub Releases**.

It is intentionally narrower than the YAML reference:

- [22 BenchStore YAML Reference](./22_BENCHSTORE_YAML_REFERENCE.md) defines the catalog schema
- this document defines how benchmark source packages should be built, named, published, and consumed when they are downloaded from GitHub Releases

The target is a stable workflow where:

1. a benchmark source package is prepared from a local curated snapshot
2. the package is uploaded as a GitHub Release asset
3. BenchStore downloads that exact asset through `download.url`
4. the downloaded asset can be verified and unpacked deterministically

## 1. Scope

This spec applies to benchmark source packages that:

- are listed in `AISB/catalog/*.yaml`
- are installed through BenchStore `Download` / `Install`
- are distributed through GitHub Release assets

This spec does **not** require datasets, checkpoints, or credentials to be bundled into the same asset.

## 2. Release model

The recommended model is:

- use **one GitHub repository** as the release host
- publish **many benchmark zip files** into one benchmark-assets release
- include one machine-readable `manifest.json` in the same release

Recommended repository:

- `ResearAI/DeepScientist`

Recommended release tag style:

- `benchstore-assets-2026-04-13`
- `benchstore-assets-r1`
- `benchstore-assets-2026q2`

Do **not** mix benchmark assets into ordinary application-version tags such as `v1.5.17` unless you are fully willing to couple software release cadence and benchmark asset cadence.

## 3. Asset granularity

Each benchmark must remain an **independent archive asset**.

Recommended asset naming rule:

- `<benchmark_id>-v<package_version>.zip`

Examples:

- `aisb.t3.001_savvy-v0.1.0.zip`
- `aisb.t3.048_proxyspex-v0.1.0.zip`
- `aisb.t3.084_ift-v0.1.0.zip`

Why this is required:

- one benchmark can be updated without rebuilding every other benchmark
- BenchStore can map one catalog entry to one asset deterministically
- checksums and install records stay benchmark-specific

## 4. Manifest requirement

Each benchmark-assets release should contain:

- benchmark zip assets
- one `manifest.json`

Recommended `manifest.json` shape:

```json
{
  "schema_version": 1,
  "release_id": "benchstore-assets-2026-04-13",
  "published_at": "2026-04-13T00:00:00Z",
  "repo": "ResearAI/DeepScientist",
  "assets": [
    {
      "benchmark_id": "aisb.t3.001_savvy",
      "version": "0.1.0",
      "asset_name": "aisb.t3.001_savvy-v0.1.0.zip",
      "archive_type": "zip",
      "sha256": "<sha256>",
      "size_bytes": 12345678,
      "published_at": "2026-04-13T00:00:00Z"
    }
  ]
}
```

The manifest is recommended even if BenchStore currently installs directly from `download.url`.
It gives you one durable source of truth for:

- integrity verification
- bulk updates
- release audits
- future migration away from hardcoded URLs

## 5. What a benchmark archive must contain

A release asset should contain only the **source package needed for benchmark installation and later quest-local use**.

It should usually contain:

- source code
- README and install notes
- requirements / pyproject / package metadata
- benchmark-local configs and scripts
- `json/metric_contract.json` if the package is built from a prepared local baseline root
- small benchmark-owned support files that are legal to redistribute

It should usually **not** contain:

- datasets
- model checkpoints unless redistribution is clearly allowed
- API secrets, auth files, local cookies, or tokens
- generated logs, caches, outputs, or user-specific artifacts
- local machine absolute paths
- `.git`, `.ds`, `.codex`, `.claude`, `node_modules`, `dist`, `build`, `__pycache__`, `.pytest_cache`, `wandb`

## 6. Release-safe packaging rules

Before publishing a benchmark archive, the packager must:

1. copy from a curated local source snapshot, not from a live quest worktree with unknown transient state
2. remove generated artifacts and local runtime residue
3. remove secrets and workstation-specific auth material
4. preserve upstream source identity where legally possible
5. keep the archive root deterministic
6. compute and record `sha256`

Recommended archive root layout:

- archive root directory name should match `download.local_dir_name`

For example, if YAML says:

```yaml
download:
  local_dir_name: aisb.t3.048_proxyspex
```

then the zip should unpack into:

- `aisb.t3.048_proxyspex/...`

not into a random temporary folder name.

## 7. YAML contract for GitHub Releases

BenchStore currently needs only these fields to install a package:

```yaml
download:
  url: https://github.com/ResearAI/DeepScientist/releases/download/benchstore-assets-2026-04-13/aisb.t3.048_proxyspex-v0.1.0.zip
  archive_type: zip
  local_dir_name: aisb.t3.048_proxyspex
```

For GitHub Releases, the recommended full contract is:

```yaml
download:
  provider: github_release
  repo: ResearAI/DeepScientist
  tag: benchstore-assets-2026-04-13
  asset_name: aisb.t3.048_proxyspex-v0.1.0.zip
  url: https://github.com/ResearAI/DeepScientist/releases/download/benchstore-assets-2026-04-13/aisb.t3.048_proxyspex-v0.1.0.zip
  archive_type: zip
  local_dir_name: aisb.t3.048_proxyspex
  version: 0.1.0
  sha256: <sha256>
  size_bytes: 12345678
  published_at: 2026-04-13T00:00:00Z
  source_repo: https://github.com/ResearAI/DeepScientist
  source_commit: <git_commit_sha>
```

Rules:

- `download.url` must point to a concrete immutable release asset, not a moving branch archive such as `main.zip`
- `download.archive_type` must match the real asset type
- `download.local_dir_name` must match the expected unpacked root directory
- `download.sha256` should be provided for all public release assets
- `download.provider` should be `github_release` for this mode
- `download.repo`, `download.tag`, and `download.asset_name` should be filled even if `download.url` is already present

## 8. Paper and data separation

GitHub Release source assets should contain benchmark code, not the whole research universe.

Keep these separate:

- `paper.url`: paper or benchmark paper link
- `download.*`: benchmark source package link
- `dataset_download.*`: dataset acquisition route
- `credential_requirements.*`: tokens or API keys needed later

Do not overload `paper.url` with repository or archive links when the entry actually has a paper.

Do not overload `download.url` with dataset links when the field is meant for source installation.

## 9. Versioning rules

`version` should be treated as the **BenchStore package version**, not necessarily the paper version and not necessarily the upstream repository tag.

Bump the package version when:

- packaged source contents change
- release-safe cleanup changes the public archive contents
- bundled configs or install-critical files change

A pure YAML description edit that does not change the archive asset does not require a new asset version.

## 10. Publishing workflow

Recommended workflow:

1. prepare a clean staging directory from the curated benchmark root
2. apply release-safe exclusions
3. ensure the unpacked root directory name is deterministic
4. build zip
5. compute `sha256` and `size_bytes`
6. update `manifest.json`
7. upload assets to the benchmark-assets GitHub release
8. update `AISB/catalog/*.yaml`
9. verify one installation through BenchStore before calling the release complete

## 11. BenchStore install behavior

For GitHub Releases, BenchStore should continue to behave as a backend-mediated installer:

1. fetch `download.url`
2. save archive under runtime downloads
3. optionally verify `download.sha256`
4. extract archive to a temporary directory
5. resolve a deterministic install root
6. move into the final install location
7. write an install record with asset metadata

Recommended future install record fields:

- `download_provider`
- `download_repo`
- `download_tag`
- `download_asset_name`
- `expected_sha256`
- `archive_sha256`
- `size_bytes`

## 12. What not to do

Do not:

- publish moving `main` or `master` branch zip URLs as production asset URLs
- publish one giant archive that contains every benchmark unless BenchStore explicitly changes to support that mode
- rely on GitHub release notes alone as the machine-readable index
- ship datasets, secrets, or local runtime debris in release archives
- overwrite a previously published asset in-place without changing version or tag

## 13. Publishing all current entries

If you want **every currently aligned BenchStore entry** to be downloadable through the frontend `Download` button, that is acceptable.

The important rule is:

- **downloadable** does not mean **fully runnable**
- **published** does not mean **recommendable for every user**

When publishing all entries, keep the existing risk metadata instead of hiding it.

Recommended interpretation:

- entries without `risk_flags` are standard release packages
- entries with `risk_flags: [route_caveat]` are still valid source packages, but the user must see the route warning in BenchStore
- entries with `risk_flags: [source_snapshot_incomplete]` are still valid source snapshots, but the package should be understood as incomplete or blocked for faithful reproduction

In other words:

- you may publish all current aligned entries
- you should **not** flatten them into one false notion of "all are equally ready"
- BenchStore should continue to differentiate recommendation, warning, and installability

## 14. What must be supplemented before an all-entry release

If you publish all entries, then every published benchmark package should have these minimum pieces completed:

1. `download.url`
2. `download.archive_type`
3. `download.local_dir_name`
4. `download.sha256`
5. `download.size_bytes`
6. `paper.url` set to a real paper link, or `null` if the entry has no real external paper page
7. `risk_flags` and `risk_notes` preserved when the entry is caveated or incomplete
8. `dataset_download` and `credential_requirements` preserved as user-facing truth, not hidden because the code package was published

For all-entry publication, the minimum honesty rule is:

- never remove risk metadata just because a zip exists
- never replace a missing paper link with an example link
- never imply that a source snapshot package contains datasets or checkpoints when it does not

## 15. Relationship to the YAML reference

This document is the distribution guide for GitHub Releases.
The YAML reference remains the field-by-field catalog reference.

Use both together:

- [22 BenchStore YAML Reference](./22_BENCHSTORE_YAML_REFERENCE.md)
- this document for GitHub Releases publication and install behavior
