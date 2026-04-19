# 22 BenchStore YAML 参考

这份文档定义 BenchStore catalog 的 YAML 合同，目录位置是：

- `AISB/catalog/*.yaml`

BenchStore 会直接读取这些文件、校验它们，并通过 BenchStore API 提供出去。

前端渲染是“宽松显示”的：

- 只渲染实际存在的字段
- 缺失的可选字段会自动跳过
- 唯一严格必填字段是 `name`

## 1. 文件放置规则

一个 benchmark 对应一个文件：

- `AISB/catalog/aisb.t3.026_gartkg.yaml`
- `AISB/catalog/my_custom_benchmark.yaml`

也允许子目录。BenchStore 会递归扫描 `AISB/catalog/`。
但对当前这批人工整理的 AutoSOTA 条目，建议全部直接放在
`AISB/catalog/` 根下，不要再额外套一层 `autosota/` 子目录。

## 2. 最小合法示例

```yaml
name: My Benchmark
```

这就是唯一的必填项。

## 3. 推荐示例

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

## 4. 字段说明

### 必填字段

**`name`**

- 类型：`string`
- 是否必填：是
- 含义：benchmark 的主展示名称

### 强烈建议填写

**`id`**

- 类型：`string`
- 是否必填：否
- 是否推荐：是
- 示例：`aisb.t3.026_gartkg`
- 规则：如果不填，BenchStore 会用文件名自动生成
- 最佳实践：除非确实需要兼容旧标识，否则直接让它和文件名 stem 保持一致

**`one_line`**

- 类型：`string`
- 是否必填：否
- 含义：卡片和概览页上的一句话摘要

**`task_description`**

- 类型：`string`
- 是否必填：否
- 含义：详情页展示和 setup agent 理解任务时使用的更长描述

**`image_path`**

- 类型：`string`
- 是否必填：否
- 含义：benchmark 对应的本地预览 JPG 图片相对路径
- 建议：优先写 repo 内相对路径，例如 `../../../AISB/image/001_aisb.t3.001_savvy.jpg`

### 分类与发现

**`capability_tags`**

- 类型：`string[]`
- 是否必填：否
- 示例：`["scientific_discovery", "drug_discovery"]`

**`aisb_direction`**

- 类型：`string`
- 是否必填：否
- 示例：`T1`、`T2`、`T3`

**`track_fit`**

- 类型：`string[]`
- 是否必填：否
- 示例：`["paper_track", "benchmark_track"]`

**`task_mode`**

- 类型：`string`
- 是否必填：否
- 示例：`experiment_driven`、`analysis_driven`、`evaluation_driven`

### 运行形态

**`requires_execution`**

- 类型：`boolean`
- 是否必填：否
- 含义：这个 benchmark 是否通常需要真实代码/实验执行

**`requires_paper`**

- 类型：`boolean`
- 是否必填：否
- 含义：这个 benchmark 是否通常要求论文级输出

**`integrity_level`**

- 类型：`string`
- 是否必填：否
- 示例：`cas_plus_canary`

### 规划提示

**`cost_band`**
重要发布说明：

- 如果条目作为可下载源码包公开发布，必须保留 `risk_flags` 与 `risk_notes`；可下载不应覆盖已知 caveat


- 类型：`string`
- 是否必填：否
- 示例：`low`、`medium`、`high`

**`time_band`**

- 类型：`string`
- 是否必填：否
- 示例：`30-60m`、`1-2h`、`1d+`、`2-4d`、`4d+`
- 建议：按“推荐硬件上的第一次可信端到端运行”估算 wall-clock，需把必要的环境准备、主要评测和论文所要求的关键阶段一起算进去；有明确上界时写分钟 / 小时 / 天区间，经常跨多天的 benchmark 用 `1d+`、`4d+` 这类开放区间

**`difficulty`**

- 类型：`string`
- 是否必填：否
- 示例：`easy`、`medium`、`hard`

**`data_access`**

- 类型：`string`
- 是否必填：否
- 示例：`public`、`restricted`、`private`

**`recommended_when`**

- 类型：`string`
- 是否必填：否

**`not_recommended_when`**

- 类型：`string`
- 是否必填：否

### 论文信息

**`paper.title`**

- 类型：`string`
- 是否必填：否

**`paper.venue`**

- 类型：`string`
- 是否必填：否
- 这是“论文场地 / 录用场所 / 发表 venue”的推荐字段

**`paper.year`**

- 类型：`integer`
- 是否必填：否

**`paper.url`**

- 类型：`string`
- 是否必填：否

### 下载信息

**`download.url`**

- 类型：`string`
- 是否必填：否
- 建议：生产环境里的 BenchStore 分发应优先使用 GitHub Release asset 这类不可变源码包链接，而不是分支压缩包。
- 参见：[23 BenchStore GitHub Releases 分发规范](./23_BENCHSTORE_GITHUB_RELEASES_SPEC.md)

**`download.archive_type`**

- 类型：`string`
- 是否必填：否
- 示例：`zip`、`tar.gz`

**`download.local_dir_name`**

- 类型：`string`
- 是否必填：否
- 含义：下载并解压后建议使用的本地目录名

### 数据获取元数据

当 benchmark 依赖明确的数据下载路线时，建议补充这一节。BenchStore 现在可以直接把这些信息显示在前端详情页和 setup-agent 上下文里。

推荐结构：

```yaml
dataset_download:
  primary_method: mixed
  sources:
    - kind: huggingface
      url: https://huggingface.co/datasets/example/bench
      access: public
      note: 主公开数据入口。
  notes:
    - 需要先把原始 split 转成项目自己的 JSON 文件。
```

约定字段：

- `dataset_download.primary_method`: `string`
- `dataset_download.sources`: `object[]`
- `dataset_download.notes`: `string[]`
- `dataset_download.sources[].kind`: `string | null`
- `dataset_download.sources[].url`: `string | null`
- `dataset_download.sources[].access`: `string | null`
- `dataset_download.sources[].note`: `string | null`

### 凭证元数据

当 benchmark 依赖 API key、gated model token、Kaggle 凭证等密钥时，建议补充这一节。

推荐结构：

```yaml
credential_requirements:
  mode: conditional
  items:
    - OPENAI_API_KEY
    - HF_TOKEN
  notes:
    - 只有可选 evaluator 路线才需要 OpenAI 访问。
```

约定字段：

- `credential_requirements.mode`: `string`
- `credential_requirements.items`: `string[]`
- `credential_requirements.notes`: `string[]`

### 运行态状态元数据

这些字段主要服务于前端详情页和后续类似 Steam 的启动逻辑，用来更清楚地表达“当前这个本地 snapshot 到底能做什么”。

**`snapshot_status`**

- 类型：`string`
- 是否必填：否
- 示例：`runnable`、`partial`、`docs_only`、`restore_needed`、`external_eval_required`
- 建议：这里描述的是“当前本地快照今天真实能做什么”，不是论文上游理论上能做什么。

**`support_level`**

- 类型：`string`
- 是否必填：否
- 示例：`turnkey`、`advanced`、`recovery`
- 建议：用来区分这个 benchmark 是即装即跑、需要复杂多步配置，还是主要用于源码恢复与人工审计。

**`primary_outputs`**

- 类型：`string[]`
- 是否必填：否
- 示例：`["aid_accuracy", "model_checkpoint", "evaluation_report"]`
- 建议：列出一次可信运行后最重要的产物或指标，而不是把所有内部中间量都塞进去。

**`launch_profiles`**

- 类型：`object[]`
- 是否必填：否
- 推荐结构：

```yaml
launch_profiles:
  - id: quick_check
    label: Quick Check
    description: 在当前设备上先跑最小可行路径。
  - id: paper_faithful
    label: Paper-Faithful
    description: 按论文描述跑完整复现路径。
```

支持的子字段：

- `launch_profiles[].id`: `string | null`
- `launch_profiles[].label`: `string | null`
- `launch_profiles[].description`: `string | null`

### 资源需求

这里必须尽量写成结构化数值，不能只写自然语言硬件描述。否则兼容性判断、排序、过滤都无法自动工作。

**`resources.minimum`**

- 类型：object
- 是否必填：否

**`resources.recommended`**

- 类型：object
- 是否必填：否

支持的子字段：

- `cpu_cores`: number
- `ram_gb`: number
- `disk_gb`: number
- `gpu_count`: number
- `gpu_vram_gb`: number

示例：

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

### 可选环境元数据

当 benchmark 的可复现性明显依赖某个运行时组合时，建议补充这一节。

推荐结构：

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

约定字段：

- `environment.python`: `string`
- `environment.cuda`: `string | null`
- `environment.pytorch`: `string | null`
- `environment.flash_attn`: `string | null`
- `environment.key_packages`: `string[]`
- `environment.notes`: `string[]`

填写建议：

- 上游仓库写了明确版本时，优先填精确版本。
- 不需要或无法确认时填 `null`。
- `key_packages` 只保留高价值依赖，不要把整个 lockfile 全塞进去。
- `notes` 用来写 CPU-only、需要 `nvcc`、需要额外 toolkit 之类的安装约束。

### 可选图片元数据

如果有 benchmark 预览图，可以补充：

```yaml
image_path: ../../../AISB/image/026_aisb.t3.026_gartkg.jpg
```

建议：

- 尽量使用 100KB 以内的 `jpg`
- 尽量统一为 16:9
- 图片文件名尽量使用 `<三位编号>_<yaml_stem>.jpg`，这样可以和 YAML 条目做机械对应
- 优先使用 README 里的主图
- README 没有合适图时，退回到论文 PDF 的主图
- 再不行就用论文首页做裁剪预览

## 5. AutoSOTA 扁平规范

对当前这批人工维护的 AutoSOTA catalog，建议同时遵守下面几条：

- YAML 路径：`AISB/catalog/aisb.t3.026_gartkg.yaml`
- `id: aisb.t3.026_gartkg`
- `download.url: https://deepscientist.cc/AISB/026_gartkg`
- `image_path: ../../../AISB/image/026_aisb.t3.026_gartkg.jpg`

这批条目的额外编写建议：

- `task_description` 要对应本地仓库里真实存在的 README、优化笔记或代码焦点，不能只是复述摘要。
- `resources.minimum` 和 `resources.recommended` 要偏保守，尤其是 GPU 显存和磁盘需求。
- `environment` 只填本地 README、requirements、环境文件或明确安装命令里能证实的版本。
- 版本不确定时宁可填 `null`，不要猜。

### 商业信息

**`commercial.annual_fee`**

- 类型：`string | number | null`
- 是否必填：否
- 示例：`99`、`"$99/year"`、`null`

### 展示提示

这些是可选的显示 hint。未来前端视觉系统升级时，可能不会逐字段照搬，但现在可以安全写入。

**`display.palette_seed`**

- 类型：`string`
- 是否必填：否

**`display.art_style`**

- 类型：`string`
- 是否必填：否
- 示例：`morandi-minimal`

**`display.accent_priority`**

- 类型：`string`
- 是否必填：否
- 示例：`low`、`medium`、`high`

## 6. 校验行为

BenchStore 会遵循下面这些规则：

- `name` 必须存在且不能为空
- 其他字段都可选
- 未识别的额外字段会保留，但当前不一定渲染
- 非法文件会从主 catalog 中跳过，并作为 catalog 错误返回

## 7. 编写建议

建议：

- 使用稳定、简短的 `id`
- 尽量提供真实的结构化资源需求
- `one_line` 保持短小
- `task_description` 只在确实有必要时写长一点
- 用 `paper.venue` 表示论文场地，不要再单独发明 `accepted_place` 之类字段

避免：

- 在 YAML 里塞超长 prompt 文本
- 只写自然语言硬件需求，不写结构化数值
- 把安装状态写进 catalog 文件
- 提交本地机器绝对路径
