# 22 BenchStore YAML 编写指南

这份文档说明如何在 `AISB/catalog/` 下新增一个 BenchStore 条目、系统如何自动发现它，以及当前 BenchStore 真正会读取哪些字段。

如果你要发布可下载的 benchmark 源码包，请同时参考
[23 BenchStore GitHub Releases 分发规范](./23_BENCHSTORE_GITHUB_RELEASES_SPEC.md)。

## 1. 自动发现规则

BenchStore 不需要手工注册表。

只要你把 YAML 文件放进 `AISB/catalog/`，BenchStore 下一次扫描 catalog 时就会自动读到它。

当前规则是：

- BenchStore 会递归扫描 `AISB/catalog/**/*.yaml`。
- 一个 YAML 文件对应一个条目。
- `name` 是唯一严格必填字段。
- `id` 可以不写；不写时会自动回退成文件名 stem。
- 整个 catalog 内的 `id` 必须唯一。
- 以 `.zh.yaml` 结尾的文件是中文本地化版本。
- 当 locale 是 `zh` 时，BenchStore 会优先读取 `<stem>.zh.yaml`，而不是 `<stem>.yaml`。
- `.zh.yaml` 不是局部覆盖，而是完整替换。

例如：

- `AISB/catalog/my.benchmark.yaml`
- `AISB/catalog/my.benchmark.zh.yaml`
- `AISB/catalog/vision/my.benchmark.yaml`

推荐命名规则：

- 文件名 stem 直接等于你想要的 entry id。
- stem 里尽量只用字母、数字、`.`、`_`、`-`。

## 2. 快速上手：新增一个 YAML

### 最小可用文件

最小合法内容只有这一行：

```yaml
name: My Benchmark
```

它会出现在 BenchStore 里，但信息会非常少。

### 推荐起步模板

通常建议从这个模板开始：

```yaml
schema_version: 1
id: my.benchmark
name: My Benchmark
version: 0.1.0

one_line: 卡片和概览里展示的一句话摘要。
task_description: >
  详情页和 BenchStore setup 流程使用的较长描述。

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

### 中文本地化

如果你要支持中文展示，就再加一个同 stem 的文件：

- `AISB/catalog/my.benchmark.yaml`
- `AISB/catalog/my.benchmark.zh.yaml`

这里有一个很重要的坑：

- `my.benchmark.zh.yaml` 必须是一份完整条目。
- BenchStore 不会把中文文件和英文文件做字段合并。
- 如果你只在 `.zh.yaml` 里写翻译过的几个字段，其他字段就真的没有了。

## 3. 具体填写要求和规范

### 3.1 系统硬要求

下面这些属于当前实现层面的硬要求或硬行为：

- YAML 根节点必须是 object，不能是纯字符串或纯列表。
- `name` 必须是非空字符串。
- `id` 如果写了，应该是字符串；如果不写，会自动从文件名 stem 推导。
- 最终解析出来的 `id` 必须在整个 catalog 中唯一。
- `.zh.yaml` 会完整替换同 stem 的英文文件，不会做字段合并。
- `capability_tags`、`track_fit`、`primary_outputs`、`risk_flags`、`risk_notes`、`environment.key_packages`、`environment.notes`、`dataset_download.notes`、`credential_requirements.items`、`credential_requirements.notes`、`launch_profiles` 必须写成列表。
- `resources.minimum` 和 `resources.recommended` 如果写了，必须是 object。
- `environment`、`dataset_download`、`credential_requirements`、`paper`、`download`、`display`、`commercial` 如果写了，必须是 object。
- `launch_profiles` 里的每个元素都必须是 object。
- `download.url` 是安装流程真正依赖的最小字段；没有它就不能走 BenchStore 安装。

### 3.2 推荐填写规范

下面这些不是“代码强校验”，但如果你想让条目表现稳定、推荐结果正常、后续维护成本低，建议严格按这个约定来写。

**基础规范**

- `schema_version`：固定写 `1`。
- `id`：直接等于文件名 stem，例如文件是 `aisb.t3.026_gartkg.yaml`，就写 `id: aisb.t3.026_gartkg`。
- `id` 风格：推荐全小写，稳定，不要频繁改名；只用字母、数字、`.`、`_`、`-`。
- `version`：推荐用 semver，例如 `0.1.0`、`0.2.3`。
- `requires_execution`、`requires_paper`：用 YAML 布尔值 `true` / `false`，不要写自然语言。

**文案规范**

- `name`：主标题，给用户看，尽量使用 benchmark 或项目的正式名字。
- `one_line`：一行摘要，建议 1 句话，适合直接放在卡片上，不要写成长段。
- `task_description`：建议 1 段到 3 段，重点写“这个 benchmark 现在在 DeepScientist 里实际要做什么”，不要只是复述论文摘要。
- `recommended_when` / `not_recommended_when`：分别说明适合场景和不适合场景，建议都写成完整句子。

**推荐系统会识别的标准取值**

- `cost_band`：推荐只用 `very_low`、`low`、`medium`、`high`、`very_high`。
- `difficulty`：推荐只用 `easy`、`medium`、`hard`、`expert`。
- `data_access`：推荐只用 `public`、`restricted`、`private`。
- `snapshot_status`：推荐只用 `runnable`、`runnable_not_verified`、`partial`、`restore_needed`、`external_eval_required`、`data_only`。
- `support_level`：推荐只用 `turnkey`、`advanced`、`recovery`。

重要说明：

- `cost_band`、`difficulty`、`snapshot_status`、`support_level` 这些字段虽然代码不做强枚举校验，但推荐排序逻辑只会识别上面这些标准值。
- 如果你写了别的字符串，条目不会报错，但推荐分数通常会退回到“未知值”的默认处理。

**`time_band` 格式规范**

BenchStore 当前能稳定识别这些格式：

- 单值：`30m`、`2h`、`3d`
- 区间：`30-60m`、`1-2h`、`2-4d`
- 开放区间：`6h+`、`1d+`、`4d+`

建议：

- 用最保守的“第一次可信端到端运行” wall-clock 估计。
- 推荐直接写成不带空格的规范格式，例如 `1-2h`，不要写“about one day”这类自然语言。

**资源填写规范**

- `resources.minimum` 和 `resources.recommended` 里，当前真正会读取的只有这 5 个数值键：
- `cpu_cores`
- `ram_gb`
- `disk_gb`
- `gpu_count`
- `gpu_vram_gb`

补充说明：

- 这里建议只写数字。
- 即使你在 `resources.minimum` 里额外塞 `notes` 之类字段，当前 BenchStore 也不会把它们用于兼容性计算。
- 如果要写额外说明，优先放到 `task_description` 或 `environment.notes`。

**下载字段规范**

- `download.url`：必须指向具体可下载资产。
- `download.archive_type`：推荐只写 `zip`、`tar.gz`、`tar`。
- `download.local_dir_name`：推荐等于解压后的根目录名；通常也建议和 `id` 保持一致。
- 如果你走 GitHub Releases 分发，推荐同时补齐 `download.provider`、`download.repo`、`download.tag`、`download.asset_name`、`download.sha256`、`download.size_bytes`。

**图片与本地化规范**

- `image_path`：推荐写相对于 YAML 文件的相对路径；解析后文件必须真实存在，并且仍然位于当前 workspace 内。
- `.zh.yaml`：建议把英文文件完整复制一份，再只翻译文案字段；不要只写中文增量字段。

**风险字段规范**

- `risk_flags` 和 `risk_notes` 只在确实存在重要 caveat 时填写。
- 一旦条目写入 `risk_flags` 或 `risk_notes`，BenchStore 推荐逻辑会把它排除出推荐结果。

### 3.3 按目标来看，需要填写哪些字段

### 只要能在 BenchStore 里出现

必填：

- `name`

强烈建议：

- `id`
- `one_line`
- `task_description`

### 想让推荐、过滤、排序更靠谱

这些字段会明显影响 catalog 质量：

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

补充说明：

- `resources.minimum` 和 `resources.recommended` 会参与设备匹配判断。
- `snapshot_status` 和 `support_level` 会参与推荐分数。
- `risk_flags` 和 `risk_notes` 用来标记已知风险。
- 只要条目带有 `risk_flags` 或 `risk_notes`，BenchStore 就不会把它放进推荐结果里。

### 想让条目支持 BenchStore 安装

安装流程的最小要求：

- `download.url`

强烈建议同时写：

- `download.archive_type`
- `download.local_dir_name`
- `download.provider`
- `download.repo`
- `download.tag`
- `download.asset_name`
- `download.sha256`
- `download.size_bytes`

重要行为：

- 如果 `requires_execution: true`，那么条目在本地安装前不能直接 launch。
- 如果不写 `download.archive_type`，BenchStore 会尝试根据 URL 后缀自动推断。
- 如果不写 `download.local_dir_name`，BenchStore 会退回使用 entry id 作为安装目录名。

### 想让详情页和 setup packet 更完整

这些字段很有用：

- `paper`
- `primary_outputs`
- `launch_profiles`
- `dataset_download`
- `credential_requirements`
- `environment`
- `recommended_when`
- `not_recommended_when`
- `image_path`
- `display`
- `commercial`

## 4. 当前支持的字段

BenchStore 目前会读取这些顶层字段：

- `schema_version`
- `id`
- `name`
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
- `display`
- `image_path`

当前识别的嵌套字段是：

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
- `launch_profiles[].id`
- `launch_profiles[].label`
- `launch_profiles[].description`

如果你额外加了别的 key，不要默认当前 UI、安装器或推荐逻辑会用到它。

## 5. 不需要手动填写的字段

这些字段是 BenchStore 自动生成的：

- `source_file`
- `image_url`
- `search_text`
- `install_state`
- `compatibility`
- `recommendation`
- `setup_prompt_preview`
- `raw_payload`

另外：

- `schema_version` 不写时默认会变成 `1`。
- `id` 不写时会自动从文件名 stem 推导。

## 6. 常见错误

### 把 `.zh.yaml` 当成局部补丁

错误写法：

- 英文文件里有完整字段。
- 中文文件里只写 `name` 和 `one_line`。

结果：

- 中文界面会丢掉其他字段，因为中文 YAML 会完整替换英文 YAML。

### 重复 id

如果两个文件最终解析成同一个 `id`，后出现的那个会被标记为无效条目。

### 列表字段写成了非列表

下面这些字段如果出现，就必须是列表：

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

### 图片路径无效

`image_path` 默认会相对 YAML 文件所在目录解析。解析后的文件必须实际存在，而且必须仍然位于 DeepScientist workspace 内。

## 7. 如何验证新条目

新增或修改 YAML 之后，可以这样验证：

- 打开 Web 里的 BenchStore，看卡片是否出现。
- 调 `GET /api/benchstore/entries`，确认条目是否在列表里。
- 调 `GET /api/benchstore/entries/<entry_id>`，检查归一化后的 payload。
- 如果条目没出现，检查 catalog 返回里的 `invalid_entries`。

这里没有额外“注册”步骤。创建 YAML 文件本身就是注册。
