# Chinese Author Alignment

Use this file when the user writes in Chinese, provides a Chinese Data Availability draft, or asks
for bilingual wording. The goal is not to translate Chinese literally. The goal is to convert the
author's Chinese description into a Nature-ready English availability route.

## Core terminology

| 中文 | Preferred English | Notes |
|---|---|---|
| 数据可用性声明 / 数据获取声明 | Data Availability | Use the journal heading `Data Availability`. |
| 本研究产生的数据 | data generated in this study | Include repository and identifier when public. |
| 原始数据 | raw data | Do not call processed tables raw data. |
| 处理后数据 | processed data | State whether processing scripts are available. |
| 源数据 | source data | Usually data underlying figures or tables. |
| 补充材料 / 附录 | Supplementary Information | Use exact file/table names when possible. |
| 公共数据库 | public database / public repository | Name the database and identifier. |
| 数据存储库 | data repository | Prefer repository over platform unless it is a true archive. |
| 登录号 / 编号 | accession number | Use for repositories that assign accession IDs. |
| DOI / 永久链接 | DOI / persistent URL | Prefer DOI when available. |
| 受限数据 | restricted data | Explain legal, ethical, consent, commercial, or third-party reason. |
| 脱敏数据 | de-identified data | Do not say anonymous unless re-identification risk is addressed. |
| 合理请求 | reasonable request | Not enough alone; add route, eligibility, and conditions. |
| 通讯作者 | corresponding author | Avoid making an email the only durable access route if an institutional route exists. |
| 数据使用协议 | data-use agreement | State when required for access. |
| 伦理审批 | ethics approval | Name approval body or requirement when relevant. |
| 代码可用性 | Code Availability | Keep separate if the journal separates data and code. |

## Chinese-to-English conversion rules

- Convert "本文所有数据均包含在正文和补充材料中" to a specific claim:
  name Source Data files, Supplementary Tables, or repository records. If raw data are absent, say
  so as a risk flag rather than pretending they are included.
- Convert "可向通讯作者合理索取" only after adding:
  why public sharing is impossible, who reviews requests, eligible requesters, required approvals
  or data-use agreement, and expected access route.
- Convert "数据因隐私原因不可公开" into a controlled-access pattern:
  state privacy/consent/legal basis, public metadata if available, access committee or institution,
  and conditions.
- Convert "商业数据/企业数据不可公开" into a third-party or commercial restriction pattern:
  name the provider or owner, request route, and whether derived or aggregate data can be shared.
- Convert "数据将在接收后上传" into an action item:
  deposit before submission or create a private reviewer link if the repository supports it.
- Convert "使用公开数据集" into a citation requirement:
  include source, version/release/date accessed when relevant, and dataset citation.

## Bilingual intake questions

Ask only what is needed for the statement.

```text
请确认这些字段：
1. 哪些数据支撑主文图、补充图和统计分析？
2. 每类数据是否已有仓库、DOI、登录号或审稿人私密链接？
3. 是否包含人类参与者、隐私、商业、第三方授权或国家/机构限制？
4. 如果数据不能公开，谁负责审核申请？需要伦理审批或数据使用协议吗？
5. 是否有代码、脚本或 README 能解释 raw data 到 figure source data 的处理过程？
```

## Common Chinese draft fixes

| 中文原意 | Avoid literal English | Nature-ready direction |
|---|---|---|
| 数据可向通讯作者索取。 | Data are available from the corresponding author upon request. | State the restriction reason and institutional access process. |
| 所有数据见补充材料。 | All data are in the supplementary materials. | Name exact Supplementary Tables/Source Data and flag missing raw data if any. |
| 数据暂未上传。 | Data will be uploaded later. | Deposit now or list repository action as blocking. |
| 使用了公开数据库。 | Public databases were used. | Name database, accession/version/date accessed, and cite dataset. |
| 因隐私不能公开。 | Data cannot be public for privacy reasons. | Add de-identification status, access committee, eligibility, and agreement terms. |

## Recommended bilingual output

When useful, provide English first and Chinese second:

```text
Data Availability
[English statement for submission]

中文核对
- 这句话对应中文含义：[brief Chinese explanation]
- 需要作者确认：[missing accession / repository / ethics condition]
```

Do not put Chinese explanatory notes inside the final English statement unless the target journal
allows bilingual manuscript text.
