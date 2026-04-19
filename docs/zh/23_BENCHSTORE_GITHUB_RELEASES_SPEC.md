# 23 BenchStore GitHub Releases 分发规范

这份文档定义当 BenchStore 基准源码包通过 **GitHub Releases** 分发时，应该遵守的发布与安装规范。

它和 YAML 参考文档的关系是：

- [22 BenchStore YAML 参考](./22_BENCHSTORE_YAML_REFERENCE.md) 负责定义 catalog 字段
- 本文负责定义 benchmark 源码包在 GitHub Releases 上应该怎样构建、命名、发布和消费

目标是形成一条稳定链路：

1. 从本地整理后的 benchmark 快照中准备源码包
2. 将源码包上传为 GitHub Release asset
3. BenchStore 通过 `download.url` 下载该 asset
4. 下载后的源码包可以被确定性校验与解压安装

## 1. 适用范围

本规范适用于：

- 被 `AISB/catalog/*.yaml` 引用的 benchmark
- 通过 BenchStore `Download` / `Install` 安装的 benchmark
- 其源码包分发后端为 GitHub Release assets 的场景

本规范不要求把数据集、模型权重或 API 凭据一起塞进源码包。

## 2. Release 模型

推荐模型是：

- 使用 **一个 GitHub 仓库** 作为 benchmark 资产发布宿主
- 在同一个 benchmark-assets release 中发布 **多个 benchmark zip**
- 同时放置一个机器可读的 `manifest.json`

推荐仓库：

- `ResearAI/DeepScientist`

推荐 tag 形式：

- `benchstore-assets-2026-04-13`
- `benchstore-assets-r1`
- `benchstore-assets-2026q2`

不要把 benchmark 资产直接混入普通程序版本 tag，例如 `v1.5.17`，除非你明确接受“程序版本节奏”和“benchmark 资产节奏”强绑定。

## 3. 资产粒度

每个 benchmark 都必须保持为一个**独立 archive asset**。

推荐文件名规则：

- `<benchmark_id>-v<package_version>.zip`

例如：

- `aisb.t3.001_savvy-v0.1.0.zip`
- `aisb.t3.048_proxyspex-v0.1.0.zip`
- `aisb.t3.084_ift-v0.1.0.zip`

为什么必须这样做：

- 可以单独更新某一个 benchmark，而不必重打其他 benchmark
- BenchStore 可以把一个 catalog 条目稳定映射到一个 asset
- checksum 和安装记录都能保持 benchmark 粒度

## 4. Manifest 要求

每个 benchmark-assets release 应包含：

- benchmark zip 资产
- 一个 `manifest.json`

推荐 `manifest.json` 结构：

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

即使 BenchStore 当前仍主要依赖 `download.url` 直接安装，也建议维护 manifest，因为它是未来做这些事情的稳定基础：

- 校验
- 批量更新
- 发布审计
- 摆脱硬编码 URL

## 5. Benchmark archive 必须包含什么

Release asset 应只包含 **安装 benchmark 所需的源码包**。

通常应该包含：

- 源码
- README 与安装说明
- requirements / pyproject / package 元数据
- benchmark 自己的配置与脚本
- 如果来源于本地整理好的 baseline root，则可以包含 `json/metric_contract.json`
- 可以合法分发的小型辅助资源

通常不应该包含：

- 数据集
- 模型权重，除非明确允许再分发
- API secret、auth 文件、本地 cookie、token
- 日志、缓存、输出物、用户本地临时产物
- 本地机器绝对路径
- `.git`、`.ds`、`.codex`、`.claude`、`node_modules`、`dist`、`build`、`__pycache__`、`.pytest_cache`、`wandb`

## 6. Release-safe 打包规则

发布 benchmark archive 前，打包器必须：

1. 从整理好的本地 benchmark 快照复制，而不是从带未知临时状态的 quest worktree 直接打包
2. 删除生成产物和本地运行残留
3. 删除 secret 与本地认证材料
4. 在法律允许范围内保留上游源码身份
5. 保证 archive 根目录稳定
6. 计算并记录 `sha256`

推荐 archive 根目录规则：

- archive 解压后的根目录名应与 `download.local_dir_name` 一致

例如如果 YAML 是：

```yaml
download:
  local_dir_name: aisb.t3.048_proxyspex
```

那么 zip 解压后应当得到：

- `aisb.t3.048_proxyspex/...`

而不是随机目录名。

## 7. GitHub Releases 模式下的 YAML 合同

BenchStore 当前真正安装时最少依赖这几个字段：

```yaml
download:
  url: https://github.com/ResearAI/DeepScientist/releases/download/benchstore-assets-2026-04-13/aisb.t3.048_proxyspex-v0.1.0.zip
  archive_type: zip
  local_dir_name: aisb.t3.048_proxyspex
```

针对 GitHub Releases，推荐完整写法：

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

规则：

- `download.url` 必须指向具体的、不可变的 release asset，而不是 `main.zip` 这种可漂移的分支压缩包
- `download.archive_type` 必须与真实资产类型一致
- `download.local_dir_name` 必须与解压后的根目录一致
- 所有公开 release asset 都建议填写 `download.sha256`
- GitHub Releases 模式下，`download.provider` 应写为 `github_release`
- 即便已经有 `download.url`，也建议同时写 `download.repo`、`download.tag`、`download.asset_name`

## 8. 论文链接和数据链接要分离

GitHub Release 资产应该承载 benchmark 源码，而不是把所有语义都塞到一个链接里。

请明确分开：

- `paper.url`：论文或 benchmark 论文链接
- `download.*`：源码包链接
- `dataset_download.*`：数据集获取路径
- `credential_requirements.*`：需要的 token / key 提示

如果条目有真实论文，不要再把 `paper.url` 写成仓库页或 zip 链接。
如果 `download.url` 是源码包，就不要再把它混成数据集下载地址。

## 9. 版本规则

这里的 `version` 应理解为 **BenchStore 源码包版本**，不是论文版本，也不一定等于上游 repo tag。

以下情况必须 bump：

- 发布包中的源码内容改变
- release-safe 清理逻辑改变，导致公开资产内容改变
- 打包时附带的配置或安装关键文件改变

如果只是改 YAML 描述，而 archive 资产本身没变，不需要强制 bump 源码包版本。

## 10. 发布流程

推荐发布流程：

1. 从整理好的 benchmark root 准备干净 staging 目录
2. 应用 release-safe 排除规则
3. 保证解压根目录名稳定
4. 打 zip
5. 计算 `sha256` 与 `size_bytes`
6. 更新 `manifest.json`
7. 上传 benchmark-assets release
8. 回写 `AISB/catalog/*.yaml`
9. 至少用 BenchStore 真装一轮再认为发布完成

## 11. BenchStore 安装行为

对于 GitHub Releases，BenchStore 应继续保持“后端代理安装”：

1. 拉取 `download.url`
2. 保存到 runtime downloads
3. 如果 YAML 提供 `download.sha256`，则校验
4. 解压到临时目录
5. 解析稳定 install root
6. 移动到最终安装目录
7. 写 install record

推荐未来 install record 里增加：

- `download_provider`
- `download_repo`
- `download_tag`
- `download_asset_name`
- `expected_sha256`
- `archive_sha256`
- `size_bytes`

## 12. 不要这样做

不要：

- 把 `main` 或 `master` 分支压缩包当成生产安装 URL
- 把全部 benchmark 打成一个巨大 archive，除非 BenchStore 明确升级成这种模式
- 只写 release note，不提供机器可读 manifest
- 在 release archive 里夹带数据集、secret 或本地运行残留
- 在不变更版本或 tag 的前提下静默替换已有资产内容

## 13. 推荐的首批迁移对象

第一次迁移到 GitHub Releases 时，优先选这类 benchmark：

- 结构完整
- 没有风险标记
- 代码再分发权利明确
- 不依赖私有 checkpoint 或受限数据集打包

不建议首批发布这类：

- `route_caveat`
- `source_snapshot_incomplete`
- 已知夹带 secret、本地路径或分发权利不清晰的条目

## 14. 与 YAML 参考文档的关系

本文是分发规范。
YAML 参考文档仍然是字段级参考。

应组合使用：

- [22 BenchStore YAML 参考](./22_BENCHSTORE_YAML_REFERENCE.md)
- 本文：GitHub Releases 分发与安装规范
