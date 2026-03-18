# DeepScientist

<p align="center">
  <img src="assets/branding/logo.svg" alt="DeepScientist logo" width="120" />
</p>

<p align="center">
  Local-first research operating system with a Python runtime, an npm launcher,
  one quest per Git repository, and shared web plus TUI surfaces.
</p>

## Install

Install DeepScientist:

```bash
npm install -g @researai/deepscientist
```

## Start

```bash
ds
```

DeepScientist starts the local web workspace at `http://127.0.0.1:20999` by default.

On first start, `ds` will:

- bootstrap a local `uv` runtime manager automatically if your machine does not already have one
- use the bundled Codex CLI that ships with the npm package
- still require you to complete Codex login once if your account is not ready yet

If you want another port:

```bash
ds --port 21000
```

If you want to bind on all interfaces:

```bash
ds --host 0.0.0.0 --port 21000
```

DeepScientist now uses `uv` to manage a locked local Python runtime. If a conda environment is active and already provides Python `>=3.11`, `ds` prefers it automatically; otherwise it bootstraps a managed `uv` + Python toolchain under `~/DeepScientist/runtime/`.

The default DeepScientist home is:

- macOS / Linux: `~/DeepScientist`
- Windows: `%USERPROFILE%\\DeepScientist`

Use `ds --home <path>` if you want to place the runtime somewhere else.

If you want to use the current working directory directly as the DeepScientist home, use:

```bash
ds --hero
```

This is equivalent to launching with `ds --home "$PWD"`.

If you want to install the bundled CLI tree into another base path from a source checkout:

```bash
bash install.sh --dir /data/DeepScientist
```

If you already have a populated DeepScientist home and want to move it safely:

```bash
ds migrate /data/DeepScientist
```

`ds migrate` stops the managed daemon first, shows the absolute source and target paths, asks for a double confirmation, verifies the copied tree, updates launcher wrappers, and only then removes the old path.

## Troubleshooting

```bash
ds doctor
```

`ds docker` is also accepted as a compatibility alias, but `ds doctor` is the documented command.

## Local PDF Compile

```bash
ds latex install-runtime
```

This installs a lightweight TinyTeX `pdflatex` runtime for local paper compilation.

## QQ Connector

- [Quick Start (English)](docs/en/00_QUICK_START.md)
- [快速开始（中文）](docs/zh/00_QUICK_START.md)
- [QQ Connector Guide (English)](docs/en/03_QQ_CONNECTOR_GUIDE.md)
- [QQ Connector Guide (中文)](docs/zh/03_QQ_CONNECTOR_GUIDE.md)

## Maintainers

- [Architecture](docs/en/90_ARCHITECTURE.md)
- [Development Guide](docs/en/91_DEVELOPMENT.md)

## Citation

This project is currently contributed by Yixuan Weng, Shichen Li, Weixu Zhao, Minjun Zhu. If you find our work valuable, please cite:

本项目当前由 Yixuan Weng、Shichen Li、Weixu Zhao、Minjun Zhu 共同贡献。如果你觉得我们的工作有价值，请引用：

```bibtex
@inproceedings{
weng2026deepscientist,
title={DeepScientist: Advancing Frontier-Pushing Scientific Findings Progressively},
author={Yixuan Weng and Minjun Zhu and Qiujie Xie and QiYao Sun and Zhen Lin and Sifan Liu and Yue Zhang},
booktitle={The Fourteenth International Conference on Learning Representations},
year={2026},
url={https://openreview.net/forum?id=cZFgsLq8Gs}
}
```

## License

[MIT](LICENSE)
