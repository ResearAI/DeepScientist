"use client";

import * as React from "react";
import { ArrowLeft, ArrowUpRight, Search } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { OverlayDialog } from "@/components/home/OverlayDialog";
import { SetupAgentQuestPanel } from "@/components/projects/SetupAgentQuestPanel";
import { SetupAgentRail } from "@/components/projects/SetupAgentRail";
import { Button } from "@/components/ui/button";
import { client } from "@/lib/api";
import {
  buildBenchStoreEntryImageUrl,
  getBenchStoreEntry,
  getBenchStoreSetupPacket,
  installBenchStoreEntry,
  listBenchStoreEntries,
} from "@/lib/api/benchstore";
import { useAdminTaskStream } from "@/lib/hooks/useAdminTaskStream";
import type {
  BenchCatalogPayload,
  BenchCompatibility,
  BenchEntry,
  BenchResourceSpec,
  BenchSetupPacket,
} from "@/lib/types/benchstore";
import { cn } from "@/lib/utils";
import { normalizeBuiltinRunnerName, runnerLabel } from "@/lib/runnerBranding";
import type { QuestSummary } from "@/types";

type BenchStoreDialogProps = {
  open: boolean;
  locale: "en" | "zh";
  onClose: () => void;
  setupQuestId?: string | null;
  setupQuestCreating?: boolean;
  onStartWithSetupPacket?: (
    setupPacket: BenchSetupPacket,
  ) => void | Promise<void>;
  onRequestSetupAgent?: (payload: {
    message: string;
    entry?: BenchEntry | null;
    setupPacket?: BenchSetupPacket | null;
  }) => void | Promise<void>;
};

type SortMode =
  | "recommended"
  | "minimum_spec"
  | "recommended_spec"
  | "fastest"
  | "easiest"
  | "name"
  | "year";
type FitFilter =
  | "all"
  | "best_match"
  | "runnable"
  | "installed"
  | "hide_unsupported";
type BooleanFilter = "all" | "true" | "false";
type BenchViewMode = "store" | "library";

function stableHash(input: string) {
  let hash = 0x811c9dc5;
  for (let index = 0; index < input.length; index += 1) {
    hash ^= input.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
}

function buildPalette(seed: string) {
  const hash = stableHash(seed);
  const warmHues = [18, 24, 30, 36];
  const mistHues = [194, 202, 208, 214];
  const sageHues = [142, 150, 158, 166];
  const hueA = warmHues[hash % warmHues.length];
  const hueB = mistHues[(hash >>> 3) % mistHues.length];
  const hueC = sageHues[(hash >>> 7) % sageHues.length];
  return {
    backgroundImage: `
      radial-gradient(circle at 18% 20%, hsla(${hueA}, 42%, 88%, 0.94), transparent 34%),
      radial-gradient(circle at 82% 16%, hsla(${hueB}, 28%, 84%, 0.68), transparent 30%),
      radial-gradient(circle at 62% 78%, hsla(${hueC}, 22%, 78%, 0.58), transparent 28%),
      linear-gradient(135deg, hsla(${hueA}, 24%, 71%, 0.96), hsla(${hueB}, 18%, 82%, 0.98) 42%, hsla(${hueC}, 18%, 88%, 0.96))
    `,
    borderColor: `hsla(${hueB}, 18%, 70%, 0.28)`,
    lineColor: `hsla(${hueC}, 18%, 96%, 0.55)`,
    dotColor: `hsla(${hueA}, 22%, 94%, 0.85)`,
  };
}

function formatBytes(value?: number | null) {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0)
    return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = value;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }
  return `${size >= 100 || unitIndex === 0 ? size.toFixed(0) : size.toFixed(1)} ${units[unitIndex]}`;
}

function formatEta(value?: number | null) {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0)
    return null;
  const totalSeconds = Math.round(value);
  if (totalSeconds < 60) return `${totalSeconds}s`;
  if (totalSeconds < 3600) {
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${minutes}m ${seconds}s`;
  }
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  return `${hours}h ${minutes}m`;
}

function mergeInstallState(
  entry: BenchEntry | null | undefined,
  patch: Record<string, unknown> | null | undefined,
) {
  if (!entry || !patch) return entry ?? null;
  const patchedEntryId = String(patch.entry_id || "").trim();
  if (patchedEntryId && patchedEntryId !== entry.id) {
    return entry;
  }
  return {
    ...entry,
    install_state: {
      ...(entry.install_state || {}),
      ...patch,
    },
  };
}

function extractInstallRecord(
  events: Array<{ event?: string; data?: Record<string, unknown> | null }> | undefined,
  entryId: string | null | undefined,
) {
  const normalizedEntryId = String(entryId || "").trim();
  if (!normalizedEntryId || !Array.isArray(events)) return null;
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const item = events[index];
    const data =
      item?.data && typeof item.data === "object" && !Array.isArray(item.data)
        ? item.data
        : null;
    const installRecord =
      data?.install_record &&
      typeof data.install_record === "object" &&
      !Array.isArray(data.install_record)
        ? (data.install_record as Record<string, unknown>)
        : null;
    if (!installRecord) continue;
    const recordEntryId = String(installRecord.entry_id || "").trim();
    if (!recordEntryId || recordEntryId === normalizedEntryId) {
      return installRecord;
    }
  }
  return null;
}

function readNumberMeta(
  record: Record<string, unknown> | null | undefined,
  key: string,
) {
  const value = record?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function formatQuestUpdatedAt(
  value?: string | null,
  locale: "en" | "zh" = "en",
) {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat(locale === "zh" ? "zh-CN" : "en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
}

function benchEntryIdFromQuest(summary: QuestSummary | null | undefined) {
  const startupContract =
    summary?.startup_contract && typeof summary.startup_contract === "object"
      ? (summary.startup_contract as Record<string, unknown>)
      : null;
  const benchContext =
    startupContract?.benchstore_context &&
    typeof startupContract.benchstore_context === "object"
      ? (startupContract.benchstore_context as Record<string, unknown>)
      : null;
  const entryId = String(benchContext?.entry_id || "").trim();
  return entryId || null;
}

function isQuestRunning(summary: QuestSummary | null | undefined) {
  const status = String(summary?.status || "")
    .trim()
    .toLowerCase();
  const runtimeStatus = String(summary?.runtime_status || "")
    .trim()
    .toLowerCase();
  return status === "active" || runtimeStatus === "running";
}

function copy(locale: "en" | "zh") {
  return locale === "zh"
    ? {
        title: "AI Scientist Bench",
        description:
          "像商店一样浏览、安装并选择适合当前设备的 benchmark，然后一键带入全自动启动表单。",
        searchPlaceholder: "搜索 benchmark、论文标题、venue、tag...",
        recommended: "推荐给当前设备",
        all: "全部任务",
        deviceSummary: "当前设备",
        openDetail: "查看详情",
        backToStore: "返回商店",
        empty: "当前没有可展示的 benchmark。",
        noResults: "没有匹配结果。",
        sortRecommended: "优先推荐",
        sortMinimumSpec: "按最低配置",
        sortRecommendedSpec: "按推荐配置",
        sortFastest: "按时长",
        sortEasiest: "按难度",
        sortName: "名称",
        sortYear: "年份",
        sortVenue: "Venue",
        setupAgentTitle: "SetupAgent",
        fitFilterLabel: "设备适配",
        fitFilterAll: "全部",
        fitFilterBest: "最佳匹配",
        fitFilterRunnable: "可运行",
        fitFilterInstalled: "已安装",
        fitFilterHideUnsupported: "隐藏不适合",
        directionFilterLabel: "方向",
        modeFilterLabel: "模式",
        trackFilterLabel: "轨道",
        accessFilterLabel: "数据",
        executionFilterLabel: "执行",
        paperFilterLabel: "论文",
        costFilterLabel: "成本",
        difficultyFilterLabel: "难度",
        moreFilters: "更多筛选",
        fewerFilters: "收起筛选",
        featuredHeading: "为当前设备优先推荐",
        browseShelf: "全部任务",
        storeTab: "Store",
        libraryTab: "Library",
        openLibrary: "进入 Library",
        returnToStore: "返回 Store",
        backToLibrary: "返回 Library",
        libraryHeading: "你的 Bench Library",
        libraryIntro:
          "集中管理已安装 Bench，以及已经关联到 quest 的 benchmark。",
        libraryInstalled: "已安装 Bench",
        libraryReady: "可直接启动",
        latestQuest: "最近 Quest",
        notInstalledYet: "尚未安装",
        libraryEmpty: "还没有已安装或已关联 quest 的 benchmark。",
        linkedQuests: "关联 Quest",
        linkedQuestCount: "关联数量",
        runningQuestCount: "运行中",
        openQuest: "打开 Quest",
        continueQuest: "继续最近 Quest",
        showAll: "展开全部",
        showLess: "收起列表",
        actionStrip: "快速操作",
        whyRecommended: "推荐判断",
        moreDetails: "更多信息",
        lessDetails: "收起信息",
        coreInfo: "核心信息",
        quickFacts: "快速信息",
        signalTags: "标签列",
        trackFit: "适合轨道",
        details: "详情",
        taskDescription: "任务描述",
        recommendedWhen: "适合使用场景",
        notRecommendedWhen: "不适合使用场景",
        minimum: "最低配置",
        recommendedSpec: "推荐配置",
        links: "链接",
        download: "下载链接",
        downloadAction: "Download",
        reinstallAction: "重新安装",
        startAction: "Start",
        downloadingAction: "正在下载",
        extractingAction: "正在解压",
        installedState: "已安装到本地",
        installFailed: "安装失败",
        localPath: "本地路径",
        speed: "速率",
        eta: "预计剩余",
        paperLink: "论文链接",
        sourceFile: "Catalog 源文件",
        unknown: "未知",
        compatibilityRecommended: "推荐运行",
        compatibilityMinimum: "可运行",
        compatibilityUnsupported: "设备偏弱",
        venue: "录用场所",
        year: "年份",
        version: "版本",
        catalogId: "Catalog ID",
        annualFee: "年费",
        dataAccess: "数据访问",
        integrityLevel: "完整性级别",
        runtimeEnvironment: "运行环境",
        keyPackages: "关键依赖",
        environmentNotes: "环境说明",
        imagePath: "图片路径",
        requiresPaper: "论文要求",
        requiresExecution: "执行要求",
        python: "Python",
        cuda: "CUDA",
        pytorch: "PyTorch",
        flashAttn: "FlashAttention",
        riskWarning: "风险提示",
        reproduction: "复现信息",
        timeBand: "时长估计",
        costBand: "成本档位",
        paperTitle: "论文标题",
        paperContext: "论文信息",
        paperAuthors: "作者",
        paperInstitutions: "机构",
        paperLicense: "许可",
        paperDoi: "DOI",
        paperLinks: "相关链接",
        packageInfo: "打包信息",
        archiveType: "压缩格式",
        localDirName: "本地目录名",
        packageNotes: "打包说明",
        catalogStyle: "Catalog 风格",
        schemaVersion: "Schema 版本",
        paletteSeed: "调色种子",
        artStyle: "视觉风格",
        accentPriority: "强调优先级",
        displayTags: "展示标签",
        resourceConfidence: "资源信息完整度",
        recommendationScore: "推荐分",
        fullRisks: "完整风险",
        riskFlags: "风险标签",
        riskNotes: "风险说明",
        datasetRoute: "数据获取",
        datasetMethod: "获取方式",
        datasetSources: "数据源",
        datasetNotes: "数据说明",
        credentialRequirements: "凭证要求",
        credentialMode: "凭证模式",
        credentialItems: "需要的凭证",
        credentialNotes: "凭证说明",
        snapshotStatus: "快照状态",
        supportLevel: "支持等级",
        primaryOutputs: "主要产物",
        launchProfiles: "启动档位",
        additionalCatalogFields: "补充字段",
        yes: "是",
        no: "否",
      }
    : {
        title: "AI Scientist Bench",
        description:
          "Browse, install, and choose benchmarks like a storefront, then send them directly into the autonomous start form.",
        searchPlaceholder:
          "Search benchmarks, paper titles, venues, or tags...",
        recommended: "Recommended For This Device",
        all: "All Benchmarks",
        deviceSummary: "Current Device",
        openDetail: "Open Details",
        backToStore: "Back To Store",
        empty: "No benchmarks are currently available.",
        noResults: "No matching benchmarks found.",
        sortRecommended: "Recommended",
        sortMinimumSpec: "Minimum Spec",
        sortRecommendedSpec: "Recommended Spec",
        sortFastest: "Fastest",
        sortEasiest: "Easiest",
        sortName: "Name",
        sortYear: "Year",
        sortVenue: "Venue",
        setupAgentTitle: "SetupAgent",
        fitFilterLabel: "Device Fit",
        fitFilterAll: "All",
        fitFilterBest: "Best Match",
        fitFilterRunnable: "Runnable",
        fitFilterInstalled: "Installed",
        fitFilterHideUnsupported: "Hide Unsupported",
        directionFilterLabel: "Direction",
        modeFilterLabel: "Mode",
        trackFilterLabel: "Track",
        accessFilterLabel: "Access",
        executionFilterLabel: "Execution",
        paperFilterLabel: "Paper",
        costFilterLabel: "Cost",
        difficultyFilterLabel: "Difficulty",
        moreFilters: "More Filters",
        fewerFilters: "Fewer Filters",
        featuredHeading: "Top Picks For This Device",
        browseShelf: "All Benchmarks",
        storeTab: "Store",
        libraryTab: "Library",
        openLibrary: "Open Library",
        returnToStore: "Back To Store",
        backToLibrary: "Back To Library",
        libraryHeading: "Your Bench Library",
        libraryIntro:
          "Manage installed benches and every benchmark already linked to an existing quest.",
        libraryInstalled: "Installed Benches",
        libraryReady: "Ready To Start",
        latestQuest: "Latest Quest",
        notInstalledYet: "Not installed yet",
        libraryEmpty: "No installed or linked benchmarks yet.",
        linkedQuests: "Linked Quests",
        linkedQuestCount: "Linked Count",
        runningQuestCount: "Running",
        openQuest: "Open Quest",
        continueQuest: "Continue Last Quest",
        showAll: "Show All",
        showLess: "Show Less",
        actionStrip: "Quick Actions",
        whyRecommended: "Why It Fits",
        moreDetails: "More Details",
        lessDetails: "Less Details",
        coreInfo: "Core Info",
        quickFacts: "Quick Facts",
        signalTags: "Signal Tags",
        trackFit: "Track Fit",
        details: "Details",
        taskDescription: "Task Description",
        recommendedWhen: "Recommended When",
        notRecommendedWhen: "Not Recommended When",
        minimum: "Minimum Spec",
        recommendedSpec: "Recommended Spec",
        links: "Links",
        download: "Download Link",
        downloadAction: "Download",
        reinstallAction: "Reinstall",
        startAction: "Start",
        downloadingAction: "Downloading",
        extractingAction: "Extracting",
        installedState: "Installed locally",
        installFailed: "Install failed",
        localPath: "Local Path",
        speed: "Speed",
        eta: "ETA",
        paperLink: "Paper Link",
        sourceFile: "Catalog Source",
        unknown: "Unknown",
        compatibilityRecommended: "Recommended",
        compatibilityMinimum: "Runnable",
        compatibilityUnsupported: "Below Target",
        venue: "Venue",
        year: "Year",
        version: "Version",
        catalogId: "Catalog ID",
        annualFee: "Annual Fee",
        dataAccess: "Data Access",
        integrityLevel: "Integrity Level",
        runtimeEnvironment: "Runtime Environment",
        keyPackages: "Key Packages",
        environmentNotes: "Environment Notes",
        imagePath: "Image Path",
        requiresPaper: "Paper Required",
        requiresExecution: "Execution Required",
        python: "Python",
        cuda: "CUDA",
        pytorch: "PyTorch",
        flashAttn: "FlashAttention",
        riskWarning: "Risk Warning",
        reproduction: "Reproduction",
        timeBand: "Time Band",
        costBand: "Cost Band",
        paperTitle: "Paper Title",
        paperContext: "Paper Context",
        paperAuthors: "Authors",
        paperInstitutions: "Institutions",
        paperLicense: "License",
        paperDoi: "DOI",
        paperLinks: "Related Links",
        packageInfo: "Package",
        archiveType: "Archive Type",
        localDirName: "Local Folder",
        packageNotes: "Package Notes",
        catalogStyle: "Catalog Style",
        schemaVersion: "Schema Version",
        paletteSeed: "Palette Seed",
        artStyle: "Art Style",
        accentPriority: "Accent Priority",
        displayTags: "Display Tags",
        resourceConfidence: "Resource Confidence",
        recommendationScore: "Recommendation Score",
        fullRisks: "Full Risks",
        riskFlags: "Risk Flags",
        riskNotes: "Risk Notes",
        datasetRoute: "Dataset Route",
        datasetMethod: "Primary Method",
        datasetSources: "Sources",
        datasetNotes: "Dataset Notes",
        credentialRequirements: "Credential Requirements",
        credentialMode: "Credential Mode",
        credentialItems: "Credential Items",
        credentialNotes: "Credential Notes",
        snapshotStatus: "Snapshot Status",
        supportLevel: "Support Level",
        primaryOutputs: "Primary Outputs",
        launchProfiles: "Launch Profiles",
        additionalCatalogFields: "Additional Catalog Fields",
        yes: "Yes",
        no: "No",
      };
}

function compatibilityLabel(
  value: BenchCompatibility | null | undefined,
  locale: "en" | "zh",
) {
  const t = copy(locale);
  if (value?.recommended_ok) return t.compatibilityRecommended;
  if (value?.minimum_ok) return t.compatibilityMinimum;
  return t.compatibilityUnsupported;
}

function booleanFilterText(value: BooleanFilter, locale: "en" | "zh") {
  if (value === "true") return locale === "zh" ? "需要" : "Required";
  if (value === "false") return locale === "zh" ? "不需要" : "Not Required";
  return locale === "zh" ? "全部" : "All";
}

function hasBenchImage(entry: BenchEntry | null | undefined) {
  return Boolean(String(entry?.image_path || entry?.image_url || "").trim());
}

function hasBenchRisk(entry: BenchEntry | null | undefined) {
  return Boolean(
    (entry?.risk_flags || []).length || (entry?.risk_notes || []).length,
  );
}

function benchRiskSummary(
  entry: BenchEntry | null | undefined,
  locale: "en" | "zh",
) {
  const notes = (entry?.risk_notes || []).filter(Boolean);
  if (notes.length > 0) return notes.join(locale === "zh" ? "；" : " | ");
  const flags = (entry?.risk_flags || []).filter(Boolean);
  return flags.join(locale === "zh" ? "；" : " | ");
}

function credentialModeText(
  value: string | null | undefined,
  locale: "en" | "zh",
) {
  const normalized = String(value || "")
    .trim()
    .toLowerCase();
  if (!normalized) return locale === "zh" ? "未知" : "Unknown";
  if (normalized === "required") return locale === "zh" ? "必需" : "Required";
  if (normalized === "conditional")
    return locale === "zh" ? "条件式" : "Conditional";
  if (normalized === "none") return locale === "zh" ? "无" : "None";
  return value || (locale === "zh" ? "未知" : "Unknown");
}

function resourceConfidenceText(
  value: string | null | undefined,
  locale: "en" | "zh",
) {
  const normalized = String(value || "")
    .trim()
    .toLowerCase();
  if (!normalized) return locale === "zh" ? "未知" : "Unknown";
  if (normalized === "full") return locale === "zh" ? "完整" : "Full";
  if (normalized === "partial") return locale === "zh" ? "部分" : "Partial";
  if (normalized === "none") return locale === "zh" ? "缺失" : "None";
  return value || (locale === "zh" ? "未知" : "Unknown");
}

function formatTimeUpperHours(
  value: number | null | undefined,
  locale: "en" | "zh",
) {
  if (typeof value !== "number" || !Number.isFinite(value) || value <= 0)
    return null;
  if (value >= 24) {
    const days = value / 24;
    const text = Number.isInteger(days) ? days.toFixed(0) : days.toFixed(1);
    return locale === "zh" ? `${text} 天` : `${text} days`;
  }
  const text = Number.isInteger(value) ? value.toFixed(0) : value.toFixed(1);
  return locale === "zh" ? `${text} 小时` : `${text} hours`;
}

function formatAnnualFee(value: string | number | null | undefined) {
  if (value == null || value === "") return null;
  return String(value);
}

function humanizeEnum(value: string | null | undefined, locale: "en" | "zh") {
  const raw = String(value || "").trim();
  if (!raw) return locale === "zh" ? "未知" : "Unknown";
  return raw.replace(/[_-]+/g, " ");
}

const CONSUMED_CATALOG_PATHS = new Set([
  "id",
  "name",
  "version",
  "one_line",
  "task_description",
  "capability_tags",
  "track_fit",
  "task_mode",
  "requires_execution",
  "requires_paper",
  "integrity_level",
  "snapshot_status",
  "support_level",
  "primary_outputs",
  "launch_profiles",
  "cost_band",
  "time_band",
  "difficulty",
  "data_access",
  "risk_flags",
  "risk_notes",
  "recommended_when",
  "not_recommended_when",
  "image_path",
  "paper.title",
  "paper.venue",
  "paper.year",
  "paper.url",
  "download.url",
  "dataset_download.primary_method",
  "dataset_download.sources",
  "dataset_download.notes",
  "credential_requirements.mode",
  "credential_requirements.items",
  "credential_requirements.notes",
  "resources.minimum",
  "resources.recommended",
  "environment.python",
  "environment.cuda",
  "environment.pytorch",
  "environment.flash_attn",
  "environment.key_packages",
  "environment.notes",
  "commercial.annual_fee",
  "aisb_direction",
  "schema_version",
  "download.archive_type",
  "download.local_dir_name",
  "download.notes",
  "download.upstream_url",
  "download.upstream_repo",
  "display.palette_seed",
  "display.art_style",
  "display.accent_priority",
  "display.tags",
  "display.summary_cards",
  "display.domain_tags",
  "paper.authors",
  "paper.institution",
  "paper.affiliations",
  "paper.affiliation",
  "paper.institutions",
  "paper.license",
  "paper.notes",
  "paper.code_url",
  "paper.github",
  "paper.project_url",
  "paper.github_url",
  "paper.arxiv_url",
  "paper.homepage",
  "paper.pypi",
  "paper.code",
  "paper.project_page",
  "paper.doi",
  "paper.abstract",
  "paper.abstract_summary",
  "paper.note",
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function isEmptyCatalogValue(value: unknown): boolean {
  if (value == null) return true;
  if (typeof value === "string") return value.trim().length === 0;
  if (Array.isArray(value))
    return value.every((item) => isEmptyCatalogValue(item));
  if (isRecord(value))
    return Object.values(value).every((item) => isEmptyCatalogValue(item));
  return false;
}

function pruneCatalogPayload(value: unknown, path = ""): unknown {
  if (path && CONSUMED_CATALOG_PATHS.has(path)) return undefined;
  if (Array.isArray(value)) {
    const items = value
      .map((item) => pruneCatalogPayload(item))
      .filter((item) => !isEmptyCatalogValue(item));
    return items.length > 0 ? items : undefined;
  }
  if (isRecord(value)) {
    const result: Record<string, unknown> = {};
    for (const [key, item] of Object.entries(value)) {
      const childPath = path ? `${path}.${key}` : key;
      const next = pruneCatalogPayload(item, childPath);
      if (!isEmptyCatalogValue(next)) result[key] = next;
    }
    return Object.keys(result).length > 0 ? result : undefined;
  }
  return isEmptyCatalogValue(value) ? undefined : value;
}

function formatCatalogFieldLabel(key: string) {
  return key
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatCatalogScalar(value: unknown, locale: "en" | "zh") {
  const t = copy(locale);
  if (typeof value === "boolean") return value ? t.yes : t.no;
  return String(value ?? "");
}

function serializeCatalogValue(value: unknown) {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function catalogStringList(value: unknown): string[] {
  if (typeof value === "string") {
    const normalized = value.trim();
    return normalized ? [normalized] : [];
  }
  if (Array.isArray(value)) {
    return value.flatMap((item) => catalogStringList(item));
  }
  return [];
}

function catalogLinkEntries(record: Record<string, unknown> | null) {
  if (!record) return [];
  return [
    "code_url",
    "github",
    "github_url",
    "project_url",
    "project_page",
    "homepage",
    "pypi",
    "arxiv_url",
    "code",
  ]
    .map((key) => {
      const value = record[key];
      const url = typeof value === "string" ? value.trim() : "";
      if (!url) return null;
      return { key, url };
    })
    .filter((item): item is { key: string; url: string } => Boolean(item));
}

function AutoCatalogValue({
  value,
  locale,
}: {
  value: unknown;
  locale: "en" | "zh";
}) {
  if (value == null) return null;
  if (
    typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean"
  ) {
    return (
      <div className="text-sm leading-7 text-[#544E46]">
        {formatCatalogScalar(value, locale)}
      </div>
    );
  }
  if (Array.isArray(value)) {
    const primitiveItems = value.filter(
      (item) =>
        typeof item === "string" ||
        typeof item === "number" ||
        typeof item === "boolean",
    );
    if (primitiveItems.length === value.length) {
      return (
        <div className="flex flex-wrap gap-2">
          {primitiveItems.map((item, index) => (
            <BenchChip key={`${String(item)}-${index}`}>
              {formatCatalogScalar(item, locale)}
            </BenchChip>
          ))}
        </div>
      );
    }
  }
  return (
    <pre className="overflow-x-auto rounded-[10px] border border-black/8 bg-white/58 px-4 py-3 text-xs leading-6 text-[#4A433B]">
      {serializeCatalogValue(value)}
    </pre>
  );
}

function formatResourceSpec(spec?: BenchResourceSpec | null) {
  if (!spec) return [];
  const rows = [
    spec.cpu_cores != null ? `${spec.cpu_cores} CPU` : null,
    spec.ram_gb != null ? `${spec.ram_gb}GB RAM` : null,
    spec.disk_gb != null ? `${spec.disk_gb}GB Disk` : null,
    spec.gpu_count != null ? `${spec.gpu_count} GPU` : null,
    spec.gpu_vram_gb != null ? `${spec.gpu_vram_gb}GB VRAM` : null,
  ];
  return rows.filter((item): item is string => Boolean(item));
}

function minimumFootprint(entry: BenchEntry) {
  const minimum = entry.resources?.minimum;
  if (!minimum) return Number.POSITIVE_INFINITY;
  return (
    Number(minimum.gpu_vram_gb || 0) * 5 +
    Number(minimum.gpu_count || 0) * 20 +
    Number(minimum.ram_gb || 0) * 1.5 +
    Number(minimum.cpu_cores || 0) * 1.2 +
    Number(minimum.disk_gb || 0) * 0.05
  );
}

function recommendedFootprint(entry: BenchEntry) {
  const recommended = entry.resources?.recommended;
  if (!recommended) return Number.POSITIVE_INFINITY;
  return (
    Number(recommended.gpu_vram_gb || 0) * 5 +
    Number(recommended.gpu_count || 0) * 20 +
    Number(recommended.ram_gb || 0) * 1.5 +
    Number(recommended.cpu_cores || 0) * 1.2 +
    Number(recommended.disk_gb || 0) * 0.05
  );
}

function sortEntries(entries: BenchEntry[], mode: SortMode) {
  const next = [...entries];
  next.sort((left, right) => {
    const leftRisk = hasBenchRisk(left) ? 1 : 0;
    const rightRisk = hasBenchRisk(right) ? 1 : 0;
    if (leftRisk !== rightRisk) return leftRisk - rightRisk;
    if (mode === "minimum_spec") {
      return minimumFootprint(left) - minimumFootprint(right);
    }
    if (mode === "recommended_spec") {
      return recommendedFootprint(left) - recommendedFootprint(right);
    }
    if (mode === "fastest") {
      return (
        Number(
          left.recommendation?.time_upper_hours || Number.POSITIVE_INFINITY,
        ) -
        Number(
          right.recommendation?.time_upper_hours || Number.POSITIVE_INFINITY,
        )
      );
    }
    if (mode === "easiest") {
      return (
        Number(
          left.recommendation?.difficulty_rank || Number.POSITIVE_INFINITY,
        ) -
        Number(
          right.recommendation?.difficulty_rank || Number.POSITIVE_INFINITY,
        )
      );
    }
    if (mode === "name")
      return String(left.name || "").localeCompare(String(right.name || ""));
    if (mode === "year")
      return Number(right.paper?.year || 0) - Number(left.paper?.year || 0);
    const leftCompat = left.compatibility;
    const rightCompat = right.compatibility;
    const rightScore = Number(
      right.recommendation?.score || rightCompat?.score || 0,
    );
    const leftScore = Number(
      left.recommendation?.score || leftCompat?.score || 0,
    );
    const rightRecommended = rightCompat?.recommended_ok ? 1 : 0;
    const leftRecommended = leftCompat?.recommended_ok ? 1 : 0;
    if (rightRecommended !== leftRecommended)
      return rightRecommended - leftRecommended;
    const rightMinimum = rightCompat?.minimum_ok ? 1 : 0;
    const leftMinimum = leftCompat?.minimum_ok ? 1 : 0;
    if (rightMinimum !== leftMinimum) return rightMinimum - leftMinimum;
    if (rightScore !== leftScore) return rightScore - leftScore;
    return String(left.name || "").localeCompare(String(right.name || ""));
  });
  return next;
}

function BenchArtwork({
  entry,
  locale,
  className,
}: {
  entry: BenchEntry;
  locale: "en" | "zh";
  className?: string;
}) {
  const palette = React.useMemo(
    () =>
      buildPalette(`${entry.id}:${entry.display?.palette_seed || entry.name}`),
    [entry.display?.palette_seed, entry.id, entry.name],
  );
  const resolvedImageUrl = React.useMemo(() => {
    if (entry.image_url) return buildBenchStoreEntryImageUrl(entry.id, locale);
    if (entry.image_path) return buildBenchStoreEntryImageUrl(entry.id, locale);
    return null;
  }, [entry.id, entry.image_path, entry.image_url, locale]);
  const [imageFailed, setImageFailed] = React.useState(false);

  React.useEffect(() => {
    setImageFailed(false);
  }, [resolvedImageUrl]);

  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-[10px] border border-black/10 shadow-[0_28px_80px_-54px_rgba(61,54,46,0.45)]",
        className,
      )}
      style={{
        backgroundImage: palette.backgroundImage,
        borderColor: palette.borderColor,
      }}
      aria-hidden
    >
      {resolvedImageUrl && !imageFailed ? (
        <img
          src={resolvedImageUrl}
          alt={entry.name}
          className="absolute inset-0 h-full w-full object-cover opacity-[0.94] saturate-[0.92] contrast-[0.96]"
          loading="lazy"
          onError={() => setImageFailed(true)}
        />
      ) : null}
      <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(255,255,255,0.18),rgba(255,255,255,0.02))]" />
      <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(24,22,19,0.04),rgba(24,22,19,0.22))]" />
      <div
        className="absolute -left-6 top-6 h-40 w-40 rounded-[12px] border blur-[2px]"
        style={{ borderColor: palette.lineColor }}
      />
      <div
        className="absolute right-8 top-10 h-24 w-24 rounded-[14px] border"
        style={{ borderColor: palette.lineColor }}
      />
      <div
        className="absolute bottom-8 left-10 h-20 w-28 rounded-[14px] border"
        style={{ borderColor: palette.lineColor }}
      />
      <div
        className="absolute bottom-10 right-16 h-32 w-32 rounded-[12px] border"
        style={{ borderColor: palette.lineColor }}
      />
      <div className="absolute inset-x-0 bottom-0 h-28 bg-[linear-gradient(180deg,transparent,rgba(36,34,31,0.36))]" />
      <div className="absolute inset-x-6 top-6 flex items-center justify-between">
        <div className="rounded-[12px] border border-white/40 bg-white/30 px-3 py-1 text-[10px] uppercase tracking-[0.22em] text-[#191714] backdrop-blur-md">
          AI Scientist Bench
        </div>
        <div className="flex items-center gap-2">
          <span
            className="h-2.5 w-2.5 rounded-[12px]"
            style={{ backgroundColor: palette.dotColor }}
          />
          <span className="h-2.5 w-2.5 rounded-[12px] bg-white/50" />
        </div>
      </div>
    </div>
  );
}

function BenchChip({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "rounded-[12px] border border-black/10 bg-white/58 px-3 py-1 text-[11px] font-medium text-[#5F5A54] backdrop-blur-md",
        className,
      )}
    >
      {children}
    </span>
  );
}

function BenchCard({
  entry,
  locale,
  onOpen,
  linkedQuestCount = 0,
  activeQuestCount = 0,
}: {
  entry: BenchEntry;
  locale: "en" | "zh";
  onOpen: () => void;
  linkedQuestCount?: number;
  activeQuestCount?: number;
}) {
  const t = copy(locale);
  return (
    <button type="button" onClick={onOpen} className="group text-left">
      <div className="overflow-hidden rounded-[10px] border border-black/10 bg-[rgba(255,250,245,0.78)] p-3 text-[#191714] shadow-[0_24px_80px_-58px_rgba(44,39,34,0.44)] backdrop-blur-xl transition duration-300 hover:-translate-y-1 hover:shadow-[0_32px_90px_-56px_rgba(44,39,34,0.5)]">
        <div className="relative">
          <BenchArtwork entry={entry} className="h-44" />
          <div className="pointer-events-none absolute inset-x-3 bottom-3 rounded-[12px] bg-white/30 px-4 py-3 backdrop-blur-md">
            <div className="line-clamp-2 text-base font-semibold tracking-[-0.02em] text-[#191714]">
              {entry.name}
            </div>
            {entry.one_line ? (
              <div className="mt-1 line-clamp-2 text-xs leading-5 text-[#191714]">
                {entry.one_line}
              </div>
            ) : null}
          </div>
        </div>
        <div className="mt-3 space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <BenchChip className="text-[#191714]">
              {compatibilityLabel(entry.compatibility, locale)}
            </BenchChip>
            {entry.install_state?.status === "installed" ? (
              <BenchChip className="text-[#191714]">{t.installedState}</BenchChip>
            ) : null}
            {entry.paper?.year ? (
              <BenchChip className="text-[#191714]">{entry.paper.year}</BenchChip>
            ) : null}
            {linkedQuestCount > 0 ? (
              <BenchChip className="text-[#191714]">
                {locale === "zh"
                  ? `Quest ${linkedQuestCount}`
                  : `${linkedQuestCount} quest${linkedQuestCount > 1 ? "s" : ""}`}
              </BenchChip>
            ) : null}
            {activeQuestCount > 0 ? (
              <BenchChip className="text-[#191714]">
                {locale === "zh"
                  ? `运行中 ${activeQuestCount}`
                  : `${activeQuestCount} running`}
              </BenchChip>
            ) : null}
          </div>
          <div className="flex items-center justify-between gap-3 text-xs text-[#191714]">
            <div className="truncate">
              {entry.paper?.venue || entry.task_mode || t.unknown}
            </div>
            <div className="inline-flex items-center gap-1 font-medium text-[#191714] transition group-hover:text-[#191714]">
              {t.openDetail}
              <ArrowUpRight className="h-3.5 w-3.5" />
            </div>
          </div>
        </div>
      </div>
    </button>
  );
}

function BenchFeatureMiniCard({
  entry,
  locale,
  onOpen,
  linkedQuestCount = 0,
}: {
  entry: BenchEntry;
  locale: "en" | "zh";
  onOpen: () => void;
  linkedQuestCount?: number;
}) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="group grid gap-3 rounded-[14px] bg-[rgba(255,252,248,0.58)] p-3 text-left shadow-[0_18px_54px_-46px_rgba(26,30,38,0.42)] backdrop-blur-xl transition duration-300 hover:-translate-y-0.5 hover:bg-[rgba(255,252,248,0.74)] sm:grid-cols-[118px_minmax(0,1fr)]"
    >
      <div className="relative">
        <BenchArtwork
          entry={entry}
          locale={locale}
          className="h-[96px] rounded-[12px]"
        />
        <div className="pointer-events-none absolute inset-x-2 bottom-2 rounded-[10px] bg-white/30 px-3 py-2 backdrop-blur-md">
          <div className="line-clamp-2 text-sm font-semibold leading-5 text-[#191714]">
            {entry.name}
          </div>
        </div>
      </div>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <BenchChip>
            {compatibilityLabel(entry.compatibility, locale)}
          </BenchChip>
          {entry.install_state?.status === "installed" ? (
            <BenchChip>{locale === "zh" ? "已安装" : "Installed"}</BenchChip>
          ) : null}
          {linkedQuestCount > 0 ? (
            <BenchChip>
              {locale === "zh"
                ? `Quest ${linkedQuestCount}`
                : `${linkedQuestCount} quest${linkedQuestCount > 1 ? "s" : ""}`}
            </BenchChip>
          ) : null}
        </div>
        <div className="mt-3 line-clamp-2 text-sm leading-6 text-[#666055]">
          {entry.one_line ||
            entry.task_description ||
            entry.paper?.venue ||
            entry.task_mode ||
            ""}
        </div>
        <div className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-[#4F6971] transition group-hover:text-[#375B66]">
          {locale === "zh" ? "查看任务" : "Open"}
          <ArrowUpRight className="h-3.5 w-3.5" />
        </div>
      </div>
    </button>
  );
}

function BenchLibrarySummaryCard({
  label,
  value,
  hint,
}: {
  label: string;
  value: number;
  hint?: string | null;
}) {
  return (
    <div className="inline-flex min-w-[148px] items-center gap-3 rounded-full border border-black/8 bg-white/74 px-4 py-2.5 text-left shadow-[0_14px_34px_-30px_rgba(44,39,34,0.28)] backdrop-blur-xl">
      <div className="text-xl font-semibold tracking-[-0.04em] text-[#2D2A26]">
        {value}
      </div>
      <div className="min-w-0">
        <div className="text-[10px] uppercase tracking-[0.16em] text-[#9B9389]">
          {label}
        </div>
        {hint ? (
          <div className="truncate text-xs leading-5 text-[#7B746A]">
            {hint}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function BenchLibraryCard({
  entry,
  locale,
  linkedQuests,
  onOpen,
  onOpenQuest,
}: {
  entry: BenchEntry;
  locale: "en" | "zh";
  linkedQuests: QuestSummary[];
  onOpen: () => void;
  onOpenQuest: (questId: string) => void;
}) {
  const t = copy(locale);
  const latestQuest = linkedQuests[0] ?? null;
  const runningQuestCount = linkedQuests.filter((quest) =>
    isQuestRunning(quest),
  ).length;
  const linkedQuestCount = linkedQuests.length;
  const isInstalled = entry.install_state?.status === "installed";

  return (
    <div className="rounded-[10px] border border-black/8 bg-white/72 px-4 py-4 shadow-[0_18px_52px_-44px_rgba(44,39,34,0.28)] backdrop-blur-xl">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-center">
        <button
          type="button"
          onClick={onOpen}
          className="w-full shrink-0 text-left xl:w-[164px]"
        >
          <BenchArtwork entry={entry} locale={locale} className="h-[110px]" />
        </button>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <BenchChip>
              {compatibilityLabel(entry.compatibility, locale)}
            </BenchChip>
            {isInstalled ? <BenchChip>{t.installedState}</BenchChip> : null}
            {linkedQuestCount > 0 ? (
              <BenchChip>
                {locale === "zh"
                  ? `Quest ${linkedQuestCount}`
                  : `${linkedQuestCount} quest${linkedQuestCount > 1 ? "s" : ""}`}
              </BenchChip>
            ) : null}
            {runningQuestCount > 0 ? (
              <BenchChip>
                {locale === "zh"
                  ? `运行中 ${runningQuestCount}`
                  : `${runningQuestCount} running`}
              </BenchChip>
            ) : null}
          </div>
          <div className="mt-3 text-[22px] font-semibold tracking-[-0.03em] text-[#1F1B17]">
            {entry.name}
          </div>
          <div className="mt-2 line-clamp-2 text-sm leading-7 text-[#5D554C]">
            {entry.one_line || entry.task_description || t.unknown}
          </div>
          <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-xs leading-6 text-[#746B61]">
            <div className="min-w-0">
              <span className="mr-2 uppercase tracking-[0.14em] text-[#9B9389]">
                {t.latestQuest}
              </span>
              <span className="font-medium text-[#2D2A26]">
                {latestQuest
                  ? latestQuest.title || latestQuest.quest_id
                  : locale === "zh"
                    ? "暂未关联"
                    : "None"}
              </span>
            </div>
            <div className="min-w-0 max-w-full">
              <span className="mr-2 uppercase tracking-[0.14em] text-[#9B9389]">
                {t.localPath}
              </span>
              <span className="inline-block max-w-[260px] truncate align-middle text-[#2D2A26]">
                {entry.install_state?.local_path || t.notInstalledYet}
              </span>
            </div>
          </div>
        </div>
        <div className="flex shrink-0 gap-2 xl:flex-col">
          <Button
            className="rounded-[12px] bg-[linear-gradient(135deg,#C8A482,#B7C8CF)] px-5 text-[#221C18] hover:opacity-95"
            onClick={onOpen}
          >
            {t.openDetail}
          </Button>
          {latestQuest ? (
            <Button
              variant="outline"
              className="rounded-[12px] border-black/10 bg-white/72 px-5 text-[#2D2A26] hover:bg-white"
              onClick={() => onOpenQuest(latestQuest.quest_id)}
            >
              {t.continueQuest}
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function MetadataRow({
  label,
  value,
}: {
  label: string;
  value?: React.ReactNode;
}) {
  if (value == null || value === "") return null;
  return (
    <div className="flex items-start justify-between gap-4 border-b border-black/6 py-3">
      <div className="text-xs uppercase tracking-[0.18em] text-[#9B9389]">
        {label}
      </div>
      <div className="text-right text-sm leading-6 text-[#342F2B]">{value}</div>
    </div>
  );
}

export function BenchStoreDialog({
  open,
  locale,
  onClose,
  setupQuestId = null,
  setupQuestCreating = false,
  onStartWithSetupPacket,
  onRequestSetupAgent,
}: BenchStoreDialogProps) {
  const navigate = useNavigate();
  const t = React.useMemo(() => copy(locale), [locale]);
  const [catalog, setCatalog] = React.useState<BenchCatalogPayload | null>(
    null,
  );
  const [questSummaries, setQuestSummaries] = React.useState<QuestSummary[]>(
    [],
  );
  const [libraryView, setLibraryView] = React.useState<BenchViewMode>("store");
  const [selectedEntryId, setSelectedEntryId] = React.useState<string | null>(
    null,
  );
  const [detailEntry, setDetailEntry] = React.useState<BenchEntry | null>(null);
  const [installTaskIds, setInstallTaskIds] = React.useState<
    Record<string, string>
  >({});
  const [setupPacketLoading, setSetupPacketLoading] = React.useState(false);
  const [actionError, setActionError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [loadingDetail, setLoadingDetail] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [sortMode, setSortMode] = React.useState<SortMode>("recommended");
  const [fitFilter, setFitFilter] = React.useState<FitFilter>("all");
  const [directionFilter, setDirectionFilter] = React.useState("all");
  const [modeFilter, setModeFilter] = React.useState("all");
  const [trackFilter, setTrackFilter] = React.useState("all");
  const [accessFilter, setAccessFilter] = React.useState("all");
  const [executionFilter, setExecutionFilter] =
    React.useState<BooleanFilter>("all");
  const [paperFilter, setPaperFilter] = React.useState<BooleanFilter>("all");
  const [costFilter, setCostFilter] = React.useState("all");
  const [difficultyFilter, setDifficultyFilter] = React.useState("all");
  const [showExtendedFilters, setShowExtendedFilters] = React.useState(false);
  const [showAllBrowse, setShowAllBrowse] = React.useState(false);
  const [query, setQuery] = React.useState("");
  const [activeRunnerName, setActiveRunnerName] = React.useState(() => normalizeBuiltinRunnerName("codex"));
  const contentScrollRef = React.useRef<HTMLDivElement | null>(null);

  React.useEffect(() => {
    if (!open) return;
    let active = true;
    void client.configDocument("config").then((payload) => {
      if (!active) return;
      const structured = payload.meta?.structured_config && typeof payload.meta.structured_config === "object"
        ? (payload.meta.structured_config as Record<string, unknown>)
        : {};
      setActiveRunnerName(normalizeBuiltinRunnerName(structured.default_runner));
    }).catch(() => {});
    return () => {
      active = false;
    };
  }, [open]);

  const openStoreView = React.useCallback(() => {
    setLibraryView("store");
    setSelectedEntryId(null);
    setDetailEntry(null);
    setShowExtendedFilters(false);
    setShowAllBrowse(false);
    contentScrollRef.current?.scrollTo({ top: 0, behavior: "auto" });
  }, []);

  const openLibraryView = React.useCallback(() => {
    setLibraryView("library");
    setSelectedEntryId(null);
    setDetailEntry(null);
    setShowExtendedFilters(false);
    setShowAllBrowse(false);
    contentScrollRef.current?.scrollTo({ top: 0, behavior: "auto" });
  }, []);

  const reloadCatalog = React.useCallback(async () => {
    const payload = await listBenchStoreEntries(locale);
    setCatalog(payload);
  }, [locale]);

  const reloadDetail = React.useCallback(async (entryId: string) => {
    const payload = await getBenchStoreEntry(entryId, locale);
    setDetailEntry(payload.entry);
  }, [locale]);

  React.useEffect(() => {
    if (!open) return;
    let active = true;
    setLoading(true);
    void Promise.allSettled([listBenchStoreEntries(locale), client.quests()])
      .then((results) => {
        if (!active) return;
        const [catalogResult, questResult] = results;
        if (catalogResult.status === "fulfilled") {
          setCatalog(catalogResult.value);
          setError(null);
        } else {
          setError(
            catalogResult.reason instanceof Error
              ? catalogResult.reason.message
              : "Failed to load BenchStore.",
          );
        }
        if (questResult.status === "fulfilled") {
          setQuestSummaries(questResult.value || []);
        } else {
          setQuestSummaries([]);
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [open, locale]);

  React.useEffect(() => {
    if (!selectedEntryId) {
      setActionError(null);
    }
  }, [selectedEntryId]);

  React.useEffect(() => {
    if (open) return;
    setLibraryView("store");
    setSelectedEntryId(null);
    setDetailEntry(null);
    setShowExtendedFilters(false);
    setShowAllBrowse(false);
  }, [open]);

  React.useEffect(() => {
    if (!open) return;
    contentScrollRef.current?.scrollTo({ top: 0, behavior: "auto" });
  }, [open, selectedEntryId]);

  React.useEffect(() => {
    setShowAllBrowse(false);
  }, [
    query,
    fitFilter,
    directionFilter,
    modeFilter,
    trackFilter,
    accessFilter,
    executionFilter,
    paperFilter,
    costFilter,
    difficultyFilter,
    sortMode,
    libraryView,
  ]);

  React.useEffect(() => {
    if (!open || !selectedEntryId) return;
    let active = true;
    setLoadingDetail(true);
    void getBenchStoreEntry(selectedEntryId, locale)
      .then((payload) => {
        if (!active) return;
        setDetailEntry(payload.entry);
      })
      .catch(() => {
        if (!active) return;
        const local =
          catalog?.items.find((item) => item.id === selectedEntryId) ?? null;
        setDetailEntry(local);
      })
      .finally(() => {
        if (active) setLoadingDetail(false);
      });
    return () => {
      active = false;
    };
  }, [catalog?.items, locale, open, selectedEntryId]);

  const linkedQuestMap = React.useMemo(() => {
    const map = new Map<string, QuestSummary[]>();
    for (const summary of questSummaries) {
      const entryId = benchEntryIdFromQuest(summary);
      if (!entryId) continue;
      const current = map.get(entryId) || [];
      current.push(summary);
      current.sort(
        (left, right) =>
          Date.parse(right.updated_at || "") -
          Date.parse(left.updated_at || ""),
      );
      map.set(entryId, current);
    }
    return map;
  }, [questSummaries]);

  const libraryEntries = React.useMemo(
    () =>
      sortEntries(
        (catalog?.items ?? []).filter(
          (item) =>
            item.install_state?.status === "installed" ||
            (linkedQuestMap.get(item.id)?.length || 0) > 0,
        ),
        sortMode,
      ),
    [catalog?.items, linkedQuestMap, sortMode],
  );

  const libraryStats = React.useMemo(() => {
    const linkedQuestTotal = libraryEntries.reduce(
      (total, entry) => total + (linkedQuestMap.get(entry.id)?.length || 0),
      0,
    );
    const runningQuestTotal = libraryEntries.reduce(
      (total, entry) =>
        total +
        (linkedQuestMap.get(entry.id) || []).filter((quest) =>
          isQuestRunning(quest),
        ).length,
      0,
    );
    const installedCount = libraryEntries.filter(
      (entry) => entry.install_state?.status === "installed",
    ).length;
    const readyCount = libraryEntries.filter(
      (entry) =>
        entry.install_state?.status === "installed" &&
        (entry.compatibility?.minimum_ok ||
          entry.compatibility?.recommended_ok),
    ).length;
    return { installedCount, linkedQuestTotal, runningQuestTotal, readyCount };
  }, [libraryEntries, linkedQuestMap]);

  const filteredEntries = React.useMemo(() => {
    const raw =
      libraryView === "library" ? libraryEntries : (catalog?.items ?? []);
    const normalizedQuery = query.trim().toLowerCase();
    const searched = normalizedQuery
      ? raw.filter((item) => {
          const searchText = String(
            item.search_text ||
              [
                item.id,
                item.name,
                item.one_line,
                item.task_description,
                item.paper?.title,
                item.paper?.venue,
                ...(item.capability_tags || []),
                ...(item.track_fit || []),
                ...(item.environment?.key_packages || []),
                ...(item.environment?.notes || []),
              ]
                .filter(Boolean)
                .join(" "),
          ).toLowerCase();
          return searchText.includes(normalizedQuery);
        })
      : raw;
    const filtered = searched.filter((item) => {
      if (
        fitFilter === "best_match" &&
        item.recommendation?.shelf_bucket !== "best_match"
      )
        return false;
      if (
        fitFilter === "runnable" &&
        !(item.compatibility?.minimum_ok || item.compatibility?.recommended_ok)
      )
        return false;
      if (
        fitFilter === "installed" &&
        item.install_state?.status !== "installed"
      )
        return false;
      if (
        fitFilter === "hide_unsupported" &&
        !item.compatibility?.minimum_ok &&
        !item.compatibility?.recommended_ok
      )
        return false;
      if (
        directionFilter !== "all" &&
        String(item.aisb_direction || "") !== directionFilter
      )
        return false;
      if (modeFilter !== "all" && String(item.task_mode || "") !== modeFilter)
        return false;
      if (
        trackFilter !== "all" &&
        !(item.track_fit || []).includes(trackFilter)
      )
        return false;
      if (
        accessFilter !== "all" &&
        String(item.data_access || "") !== accessFilter
      )
        return false;
      if (executionFilter !== "all") {
        const needsExecution =
          item.requires_execution == null
            ? null
            : String(Boolean(item.requires_execution));
        if (needsExecution !== executionFilter) return false;
      }
      if (paperFilter !== "all") {
        const needsPaper =
          item.requires_paper == null
            ? null
            : String(Boolean(item.requires_paper));
        if (needsPaper !== paperFilter) return false;
      }
      if (costFilter !== "all" && String(item.cost_band || "") !== costFilter)
        return false;
      if (
        difficultyFilter !== "all" &&
        String(item.difficulty || "") !== difficultyFilter
      )
        return false;
      return true;
    });
    return sortEntries(filtered, sortMode);
  }, [
    accessFilter,
    catalog?.items,
    libraryEntries,
    libraryView,
    linkedQuestMap,
    costFilter,
    difficultyFilter,
    directionFilter,
    executionFilter,
    fitFilter,
    modeFilter,
    paperFilter,
    query,
    sortMode,
    trackFilter,
  ]);

  const safeFilteredEntries = React.useMemo(
    () => filteredEntries.filter((item) => !hasBenchRisk(item)),
    [filteredEntries],
  );

  const recommendedEntries = React.useMemo(
    () =>
      safeFilteredEntries
        .filter(
          (item) =>
            item.compatibility?.minimum_ok ||
            item.compatibility?.recommended_ok,
        )
        .slice(0, 6),
    [safeFilteredEntries],
  );

  const featuredEntry = React.useMemo(() => {
    const items = safeFilteredEntries;
    const bestMatchIds = new Set(catalog?.shelves?.best_match_ids || []);
    return (
      items.find((item) => bestMatchIds.has(item.id) && hasBenchImage(item)) ??
      items.find((item) => bestMatchIds.has(item.id)) ??
      recommendedEntries.find((item) => hasBenchImage(item)) ??
      recommendedEntries[0] ??
      safeFilteredEntries.find((item) => hasBenchImage(item)) ??
      safeFilteredEntries[0] ??
      null
    );
  }, [
    catalog?.shelves?.best_match_ids,
    recommendedEntries,
    safeFilteredEntries,
  ]);

  const browseEntries = React.useMemo(
    () => (showAllBrowse ? filteredEntries : filteredEntries.slice(0, 12)),
    [filteredEntries, showAllBrowse],
  );

  const activeEntry = React.useMemo(() => {
    if (!selectedEntryId) return null;
    return detailEntry?.id === selectedEntryId
      ? detailEntry
      : (catalog?.items.find((item) => item.id === selectedEntryId) ?? null);
  }, [catalog?.items, detailEntry, selectedEntryId]);

  const activeInstallTaskId = React.useMemo(() => {
    if (!selectedEntryId) return null;
    const fromLocalMap = installTaskIds[selectedEntryId];
    if (fromLocalMap) return fromLocalMap;
    const taskId = String(activeEntry?.install_state?.task_id || "").trim();
    if (taskId && activeEntry?.install_state?.status === "installing")
      return taskId;
    return null;
  }, [
    activeEntry?.install_state?.status,
    activeEntry?.install_state?.task_id,
    installTaskIds,
    selectedEntryId,
  ]);

  const installStream = useAdminTaskStream(activeInstallTaskId);
  const installTask = installStream.task;
  const installStatus = String(installTask?.status || "")
    .trim()
    .toLowerCase();
  const installMetadata =
    installTask?.metadata &&
    typeof installTask.metadata === "object" &&
    !Array.isArray(installTask.metadata)
      ? (installTask.metadata as Record<string, unknown>)
      : null;
  const installBytesDownloaded = readNumberMeta(
    installMetadata,
    "bytes_downloaded",
  );
  const installBytesTotal = readNumberMeta(installMetadata, "bytes_total");
  const installSpeed = readNumberMeta(installMetadata, "speed_bytes_per_sec");
  const installEta = readNumberMeta(installMetadata, "eta_seconds");
  const installInFlight = Boolean(
    installTask &&
    !["completed", "failed", "cancelled"].includes(installStatus),
  );

  React.useEffect(() => {
    if (!selectedEntryId || !activeInstallTaskId || !installTask) return;
    const metadata =
      installTask.metadata &&
      typeof installTask.metadata === "object" &&
      !Array.isArray(installTask.metadata)
        ? (installTask.metadata as Record<string, unknown>)
        : null;
    if (String(metadata?.entry_id || "").trim() !== selectedEntryId) return;
    const optimisticPatch: Record<string, unknown> = {
      entry_id: selectedEntryId,
      task_id: activeInstallTaskId,
      status:
        installStatus === "failed" || installStatus === "cancelled"
          ? "failed"
          : installStatus === "completed"
            ? "installed"
            : "installing",
      bytes_downloaded: installBytesDownloaded ?? undefined,
      bytes_total: installBytesTotal ?? undefined,
      download_url: metadata?.download_url,
      archive_type: metadata?.archive_type,
      local_path: metadata?.install_dir,
    };
    setDetailEntry((current) => mergeInstallState(current, optimisticPatch));
    setCatalog((current) =>
      current
        ? {
            ...current,
            items: current.items.map((item) =>
              item.id === selectedEntryId
                ? (mergeInstallState(item, optimisticPatch) as BenchEntry)
                : item,
            ),
          }
        : current,
    );
  }, [
    activeInstallTaskId,
    installBytesDownloaded,
    installBytesTotal,
    installStatus,
    installTask,
    selectedEntryId,
  ]);

  React.useEffect(() => {
    if (!selectedEntryId || !activeInstallTaskId) return;
    if (!["completed", "failed", "cancelled"].includes(installStatus)) return;
    const installRecord = extractInstallRecord(installStream.events, selectedEntryId);
    if (installRecord) {
      setDetailEntry((current) => mergeInstallState(current, installRecord));
      setCatalog((current) =>
        current
          ? {
              ...current,
              items: current.items.map((item) =>
                item.id === selectedEntryId
                  ? (mergeInstallState(item, installRecord) as BenchEntry)
                  : item,
              ),
            }
          : current,
      );
    }
    setInstallTaskIds((current) => {
      if (!Object.prototype.hasOwnProperty.call(current, selectedEntryId)) {
        return current;
      }
      const next = { ...current };
      delete next[selectedEntryId];
      return next;
    });
    if (installStatus === "failed" || installStatus === "cancelled") {
      setActionError(
        String(installTask?.error || installTask?.message || t.installFailed),
      );
    }
    void reloadCatalog();
    void reloadDetail(selectedEntryId);
  }, [
    activeInstallTaskId,
    installStatus,
    installStream.events,
    installTask?.error,
    installTask?.message,
    reloadCatalog,
    reloadDetail,
    selectedEntryId,
    t.installFailed,
  ]);

  const progressPercent = React.useMemo(() => {
    if (
      typeof installTask?.progress_percent === "number" &&
      Number.isFinite(installTask.progress_percent)
    ) {
      return Math.max(0, Math.min(100, installTask.progress_percent));
    }
    const record = activeEntry?.install_state;
    if (
      typeof record?.bytes_downloaded === "number" &&
      typeof record?.bytes_total === "number" &&
      record.bytes_total > 0
    ) {
      return Math.max(
        0,
        Math.min(100, (record.bytes_downloaded / record.bytes_total) * 100),
      );
    }
    return 0;
  }, [activeEntry?.install_state, installTask?.progress_percent]);

  const additionalCatalogFields = React.useMemo(() => {
    if (!isRecord(activeEntry?.raw_payload)) return [];
    const remainder = pruneCatalogPayload(activeEntry.raw_payload);
    if (!isRecord(remainder)) return [];
    return Object.entries(remainder).filter(
      ([, value]) => !isEmptyCatalogValue(value),
    );
  }, [activeEntry?.raw_payload]);

  const rawPaper = React.useMemo(
    () =>
      isRecord(activeEntry?.raw_payload?.paper)
        ? activeEntry.raw_payload.paper
        : null,
    [activeEntry?.raw_payload],
  );
  const rawDownload = React.useMemo(
    () =>
      isRecord(activeEntry?.raw_payload?.download)
        ? activeEntry.raw_payload.download
        : null,
    [activeEntry?.raw_payload],
  );
  const rawDisplay = React.useMemo(
    () =>
      isRecord(activeEntry?.raw_payload?.display)
        ? activeEntry.raw_payload.display
        : null,
    [activeEntry?.raw_payload],
  );
  const paperAuthors = React.useMemo(
    () => catalogStringList(rawPaper?.authors),
    [rawPaper],
  );
  const paperInstitutions = React.useMemo(
    () => [
      ...catalogStringList(rawPaper?.institution),
      ...catalogStringList(rawPaper?.institutions),
      ...catalogStringList(rawPaper?.affiliation),
      ...catalogStringList(rawPaper?.affiliations),
    ],
    [rawPaper],
  );
  const paperLinks = React.useMemo(
    () => catalogLinkEntries(rawPaper),
    [rawPaper],
  );
  const paperNotes = React.useMemo(
    () => [
      ...catalogStringList(rawPaper?.notes),
      ...catalogStringList(rawPaper?.note),
      ...catalogStringList(rawPaper?.abstract_summary),
    ],
    [rawPaper],
  );
  const packageNotes = React.useMemo(
    () => [
      ...catalogStringList(rawDownload?.notes),
      ...catalogStringList(rawDownload?.upstream_url),
      ...catalogStringList(rawDownload?.upstream_repo),
    ],
    [rawDownload],
  );
  const displayTags = React.useMemo(
    () => [
      ...catalogStringList(rawDisplay?.tags),
      ...catalogStringList(rawDisplay?.domain_tags),
      ...catalogStringList(rawDisplay?.summary_cards),
    ],
    [rawDisplay],
  );

  const handleInstall = React.useCallback(async (entry: BenchEntry) => {
    const response = await installBenchStoreEntry(entry.id);
    setInstallTaskIds((current) => ({
      ...current,
      [entry.id]: response.task.task_id,
    }));
  }, []);

  const renderSpec = React.useCallback(
    (spec?: BenchResourceSpec | null) => {
      const rows = formatResourceSpec(spec);
      if (rows.length === 0)
        return <div className="text-sm text-[#8D867C]">{t.unknown}</div>;
      return (
        <div className="space-y-2">
          {rows.map((row) => (
            <div key={row} className="text-sm text-[#372F2A]">
              {row}
            </div>
          ))}
        </div>
      );
    },
    [t.unknown],
  );

  return (
    <OverlayDialog
      open={open}
      title={t.title}
      description={t.description}
      onClose={onClose}
      className="h-[90svh] w-[97vw] max-w-[min(1554px,97vw)] bg-[radial-gradient(circle_at_14%_12%,rgba(225,196,172,0.42),transparent_26%),radial-gradient(circle_at_85%_8%,rgba(175,194,205,0.28),transparent_24%),linear-gradient(180deg,rgba(247,243,237,0.98),rgba(236,228,219,0.96))]"
      closeButtonDataOnboardingId="benchstore-close"
    >
      <div
        className="grid h-full min-h-0 gap-4 lg:grid-cols-[minmax(0,1.55fr)_minmax(360px,0.9fr)]"
        data-onboarding-id="benchstore-dialog"
      >
        <div
          ref={contentScrollRef}
          data-onboarding-id={
            !selectedEntryId ? "benchstore-overview-surface" : undefined
          }
          className="feed-scrollbar modal-scrollbar min-h-0 overflow-y-scroll overscroll-contain px-4 py-4 sm:px-5 sm:py-5"
          onWheel={(event) => event.stopPropagation()}
        >
          {selectedEntryId && activeEntry ? (
            <div
              className="space-y-5"
              data-onboarding-id="benchstore-detail-surface"
            >
              <div className="flex items-center justify-between gap-4">
                <Button
                  variant="outline"
                  className="rounded-[12px] border-black/12 bg-white/70 text-[#2D2A26] hover:bg-white"
                  onClick={() => {
                    setSelectedEntryId(null);
                    setDetailEntry(null);
                  }}
                >
                  <ArrowLeft className="mr-2 h-4 w-4" />
                  {libraryView === "library" ? t.backToLibrary : t.backToStore}
                </Button>
                {loadingDetail ? (
                  <div className="text-sm text-[#7C756B]">Loading...</div>
                ) : null}
              </div>

              <section className="overflow-hidden rounded-[12px] bg-[linear-gradient(145deg,rgba(253,247,241,0.9),rgba(239,229,220,0.82)_42%,rgba(226,235,239,0.78))] p-4 shadow-[0_30px_100px_-64px_rgba(44,39,34,0.5)] backdrop-blur-2xl sm:p-5">
                <div className="relative overflow-hidden rounded-[10px]">
                  <BenchArtwork
                    entry={activeEntry}
                    locale={locale}
                    className="h-[276px] sm:h-[312px]"
                  />
                  <div className="pointer-events-none absolute inset-x-5 bottom-5 rounded-[14px] bg-white/22 px-5 py-4 backdrop-blur-md">
                    <div className="flex flex-wrap gap-2">
                      <BenchChip>
                        {compatibilityLabel(activeEntry.compatibility, locale)}
                      </BenchChip>
                      {activeEntry.task_mode ? (
                        <BenchChip>{activeEntry.task_mode}</BenchChip>
                      ) : null}
                      {activeEntry.snapshot_status ? (
                        <BenchChip>
                          {humanizeEnum(activeEntry.snapshot_status, locale)}
                        </BenchChip>
                      ) : null}
                      {activeEntry.support_level ? (
                        <BenchChip>
                          {humanizeEnum(activeEntry.support_level, locale)}
                        </BenchChip>
                      ) : null}
                    </div>
                    <div className="mt-3 text-[32px] font-semibold tracking-[-0.04em] text-[#181713] sm:text-[38px]">
                      {activeEntry.name}
                    </div>
                    <div className="mt-3 max-w-3xl text-sm leading-7 text-[#2D2722] sm:text-base">
                      {activeEntry.one_line ||
                        activeEntry.task_description ||
                        t.unknown}
                    </div>
                  </div>
                </div>

                <div
                  className="mt-4 overflow-hidden rounded-[14px] border border-white/10 bg-[linear-gradient(180deg,rgba(68,72,79,0.94),rgba(51,55,61,0.98))] shadow-[0_24px_70px_-52px_rgba(15,18,24,0.5)]"
                  data-onboarding-id="benchstore-detail-action-strip"
                >
                  <div className="flex flex-wrap items-center gap-3 px-5 py-3.5">
                    <Button
                      className="h-12 min-w-[13.5rem] rounded-[12px] bg-[linear-gradient(135deg,#B89A72,#8F6F4F)] px-8 text-[#201812] shadow-[0_16px_36px_-24px_rgba(10,14,18,0.55)] hover:opacity-95"
                      onClick={async () => {
                        setActionError(null);
                        try {
                          if (
                            activeEntry.install_state?.status === "installed"
                          ) {
                            setSetupPacketLoading(true);
                            try {
                              const payload = await getBenchStoreSetupPacket(
                                activeEntry.id,
                                locale,
                              );
                              await onStartWithSetupPacket?.(
                                payload.setup_packet,
                              );
                            } finally {
                              setSetupPacketLoading(false);
                            }
                            return;
                          }
                          await handleInstall(activeEntry);
                        } catch (caught) {
                          setActionError(
                            caught instanceof Error
                              ? caught.message
                              : String(caught),
                          );
                        }
                      }}
                      isLoading={installInFlight || setupPacketLoading}
                    >
                      {installInFlight
                        ? installTask?.current_step === "verify"
                          ? "Verifying SHA-256"
                          : installTask?.current_step === "extract"
                            ? t.extractingAction
                            : t.downloadingAction
                        : activeEntry.install_state?.status === "installed"
                          ? t.startAction
                          : activeEntry.install_state?.status === "failed" ||
                              activeEntry.install_state?.status === "missing"
                            ? t.reinstallAction
                            : t.downloadAction}
                    </Button>
                    <div className="ml-auto flex flex-wrap items-center gap-x-5 gap-y-3 text-white font-semibold">
                      <div>
                        <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-white">
                          {t.venue}
                        </div>
                        <div className="mt-1 text-sm font-semibold text-white">
                          {activeEntry.paper?.venue || t.unknown}
                        </div>
                      </div>
                      <div>
                        <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-white">
                          {t.year}
                        </div>
                        <div className="mt-1 text-sm font-semibold text-white">
                          {activeEntry.paper?.year || t.unknown}
                        </div>
                      </div>
                      <div>
                        <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-white">
                          {t.trackFit}
                        </div>
                        <div className="mt-1 text-sm font-semibold text-white">
                          {(activeEntry.track_fit || [])
                            .slice(0, 2)
                            .join(", ") || t.unknown}
                        </div>
                      </div>
                    </div>
                  </div>
                  {installInFlight ||
                  activeEntry.install_state?.status === "installed" ||
                  activeEntry.install_state?.status === "failed" ||
                  activeEntry.install_state?.status === "missing" ||
                  actionError ||
                  activeEntry.install_state?.local_path ? (
                    <div className="border-t border-white/8 px-5 py-4">
                      {installInFlight ||
                      activeEntry.install_state?.status === "installed" ? (
                        <>
                          <div className="flex items-center justify-between gap-3 text-xs uppercase tracking-[0.16em] text-white/56">
                            <span>
                              {installTask?.current_step ||
                                activeEntry.install_state?.status ||
                                "install"}
                            </span>
                            <span>
                              {installBytesDownloaded != null
                                ? installBytesTotal != null
                                  ? `${formatBytes(installBytesDownloaded)} / ${formatBytes(installBytesTotal)}`
                                  : formatBytes(installBytesDownloaded)
                                : activeEntry.install_state?.bytes_total != null
                                  ? `${formatBytes(activeEntry.install_state?.bytes_downloaded ?? 0)} / ${formatBytes(activeEntry.install_state?.bytes_total ?? 0)}`
                                  : ""}
                            </span>
                          </div>
                          <div className="mt-3 h-2.5 overflow-hidden rounded-[12px] bg-white/10">
                            <div
                              className="h-full rounded-[12px] bg-[linear-gradient(90deg,#D1A98A,#AFC3CB)] transition-all duration-300"
                              style={{ width: `${progressPercent}%` }}
                            />
                          </div>
                          <div className="mt-3 flex flex-wrap items-center gap-4 text-sm text-white/64">
                            {installSpeed != null ? (
                              <div>
                                {t.speed}: {formatBytes(installSpeed)}/s
                              </div>
                            ) : null}
                            {formatEta(installEta) ? (
                              <div>
                                {t.eta}: {formatEta(installEta)}
                              </div>
                            ) : null}
                            {activeEntry.install_state?.local_path ? (
                              <div>{activeEntry.install_state.local_path}</div>
                            ) : null}
                          </div>
                        </>
                      ) : null}
                      {!installInFlight &&
                      (activeEntry.install_state?.status === "failed" ||
                        activeEntry.install_state?.status === "missing") &&
                      !actionError ? (
                        <div className="mt-3 text-sm text-[#F0C0B6]">
                          {t.installFailed}
                        </div>
                      ) : null}
                      {actionError ? (
                        <div className="mt-3 text-sm text-[#F0C0B6]">
                          {actionError}
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              </section>

              <section className="grid gap-4 xl:grid-cols-[minmax(0,1.08fr)_minmax(320px,0.92fr)]">
                <div className="rounded-[10px] border border-black/8 bg-white/70 px-5 py-5 shadow-[0_18px_52px_-44px_rgba(44,39,34,0.24)] backdrop-blur-xl">
                  <div className="text-xs uppercase tracking-[0.18em] text-[#9B9389]">
                    {t.quickFacts}
                  </div>
                  <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                    {activeEntry.paper?.venue ? (
                      <div className="rounded-[10px] bg-[rgba(245,240,234,0.72)] px-4 py-3">
                        <div className="text-[10px] uppercase tracking-[0.16em] text-[#9B9389]">
                          {t.venue}
                        </div>
                        <div className="mt-1 text-sm font-medium text-[#2D2A26]">
                          {activeEntry.paper.venue}
                        </div>
                      </div>
                    ) : null}
                    {activeEntry.paper?.year ? (
                      <div className="rounded-[10px] bg-[rgba(245,240,234,0.72)] px-4 py-3">
                        <div className="text-[10px] uppercase tracking-[0.16em] text-[#9B9389]">
                          {t.year}
                        </div>
                        <div className="mt-1 text-sm font-medium text-[#2D2A26]">
                          {activeEntry.paper.year}
                        </div>
                      </div>
                    ) : null}
                    {activeEntry.aisb_direction ? (
                      <div className="rounded-[10px] bg-[rgba(245,240,234,0.72)] px-4 py-3">
                        <div className="text-[10px] uppercase tracking-[0.16em] text-[#9B9389]">
                          {t.directionFilterLabel}
                        </div>
                        <div className="mt-1 text-sm font-medium text-[#2D2A26]">
                          {activeEntry.aisb_direction}
                        </div>
                      </div>
                    ) : null}
                    {activeEntry.data_access ? (
                      <div className="rounded-[10px] bg-[rgba(245,240,234,0.72)] px-4 py-3">
                        <div className="text-[10px] uppercase tracking-[0.16em] text-[#9B9389]">
                          {t.dataAccess}
                        </div>
                        <div className="mt-1 text-sm font-medium text-[#2D2A26]">
                          {activeEntry.data_access}
                        </div>
                      </div>
                    ) : null}
                    {activeEntry.download?.archive_type ? (
                      <div className="rounded-[10px] bg-[rgba(245,240,234,0.72)] px-4 py-3">
                        <div className="text-[10px] uppercase tracking-[0.16em] text-[#9B9389]">
                          {t.archiveType}
                        </div>
                        <div className="mt-1 text-sm font-medium text-[#2D2A26]">
                          {activeEntry.download.archive_type}
                        </div>
                      </div>
                    ) : null}
                    {activeEntry.download?.local_dir_name ? (
                      <div className="rounded-[10px] bg-[rgba(245,240,234,0.72)] px-4 py-3">
                        <div className="text-[10px] uppercase tracking-[0.16em] text-[#9B9389]">
                          {t.localDirName}
                        </div>
                        <div className="mt-1 truncate text-sm font-medium text-[#2D2A26]">
                          {activeEntry.download.local_dir_name}
                        </div>
                      </div>
                    ) : null}
                  </div>
                </div>

                <div className="rounded-[10px] border border-black/8 bg-white/70 px-5 py-5 shadow-[0_18px_52px_-44px_rgba(44,39,34,0.24)] backdrop-blur-xl">
                  <div className="text-xs uppercase tracking-[0.18em] text-[#9B9389]">
                    {t.signalTags}
                  </div>
                  <div className="mt-4 space-y-4">
                    {(activeEntry.track_fit || []).length > 0 ? (
                      <div>
                        <div className="text-[10px] uppercase tracking-[0.16em] text-[#9B9389]">
                          {t.trackFit}
                        </div>
                        <div className="mt-2 flex flex-wrap gap-2">
                          {(activeEntry.track_fit || []).map((item) => (
                            <BenchChip key={item}>{item}</BenchChip>
                          ))}
                        </div>
                      </div>
                    ) : null}
                    {(activeEntry.primary_outputs || []).length > 0 ? (
                      <div>
                        <div className="text-[10px] uppercase tracking-[0.16em] text-[#9B9389]">
                          {t.primaryOutputs}
                        </div>
                        <div className="mt-2 flex flex-wrap gap-2">
                          {(activeEntry.primary_outputs || [])
                            .slice(0, 6)
                            .map((item) => (
                              <BenchChip key={item}>{item}</BenchChip>
                            ))}
                        </div>
                      </div>
                    ) : null}
                    {(activeEntry.capability_tags || []).length > 0 ? (
                      <div>
                        <div className="text-[10px] uppercase tracking-[0.16em] text-[#9B9389]">
                          Tags
                        </div>
                        <div className="mt-2 flex flex-wrap gap-2">
                          {(activeEntry.capability_tags || [])
                            .slice(0, 8)
                            .map((tag) => (
                              <BenchChip key={tag}>{tag}</BenchChip>
                            ))}
                        </div>
                      </div>
                    ) : null}
                  </div>
                </div>
              </section>

              <div className="grid gap-4 xl:grid-cols-[minmax(0,1.18fr)_minmax(300px,0.82fr)]">
                <section className="rounded-[10px] bg-white/66 px-6 py-5 shadow-[0_24px_76px_-58px_rgba(44,39,34,0.3)] backdrop-blur-xl">
                  <div className="text-xs uppercase tracking-[0.18em] text-[#9B9389]">
                    {t.taskDescription}
                  </div>
                  <div className="mt-4 text-[15px] leading-8 text-[#342F2B]">
                    {activeEntry.task_description ||
                      activeEntry.one_line ||
                      t.unknown}
                  </div>

                  {hasBenchRisk(activeEntry) ? (
                    <div className="mt-4 text-sm font-medium leading-7 text-[#B24637]">
                      {t.riskWarning}: {benchRiskSummary(activeEntry, locale)}
                    </div>
                  ) : null}

                  {activeEntry.recommended_when ? (
                    <div className="mt-6 border-t border-black/6 pt-6">
                      <div className="text-xs uppercase tracking-[0.18em] text-[#7D9077]">
                        {t.recommendedWhen}
                      </div>
                      <div className="mt-2 text-sm leading-7 text-[#3B4037]">
                        {activeEntry.recommended_when}
                      </div>
                    </div>
                  ) : null}

                  {activeEntry.not_recommended_when ? (
                    <div className="mt-6 border-t border-black/6 pt-6">
                      <div className="text-xs uppercase tracking-[0.18em] text-[#A37F73]">
                        {t.notRecommendedWhen}
                      </div>
                      <div className="mt-2 text-sm leading-7 text-[#463A35]">
                        {activeEntry.not_recommended_when}
                      </div>
                    </div>
                  ) : null}

                  {(linkedQuestMap.get(activeEntry.id)?.length || 0) > 0 ? (
                    <div className="mt-6 border-t border-black/6 pt-6">
                      <div className="flex items-center justify-between gap-3">
                        <div className="text-xs uppercase tracking-[0.18em] text-[#7A8796]">
                          {t.linkedQuests}
                        </div>
                        <div className="text-xs text-[#8A8278]">
                          {linkedQuestMap.get(activeEntry.id)?.length || 0}
                        </div>
                      </div>
                      <div className="mt-3 space-y-3">
                        {(linkedQuestMap.get(activeEntry.id) || [])
                          .slice(0, 4)
                          .map((quest) => (
                            <button
                              key={quest.quest_id}
                              type="button"
                              onClick={() => {
                                onClose();
                                navigate(`/projects/${quest.quest_id}`);
                              }}
                              className="w-full rounded-[10px] border border-black/8 bg-white/55 px-4 py-3 text-left transition hover:bg-white"
                            >
                              <div className="flex items-center justify-between gap-3">
                                <div className="min-w-0 text-sm font-medium text-[#2D2A26]">
                                  {quest.title || quest.quest_id}
                                </div>
                                <div className="text-[11px] uppercase tracking-[0.14em] text-[#8A8278]">
                                  {quest.status}
                                </div>
                              </div>
                              <div className="mt-1 text-xs text-[#6E675E]">
                                {formatQuestUpdatedAt(quest.updated_at, locale)}
                              </div>
                            </button>
                          ))}
                      </div>
                    </div>
                  ) : null}

                  {(activeEntry.environment?.key_packages || []).length > 0 ||
                  (activeEntry.environment?.notes || []).length > 0 ||
                  activeEntry.environment?.python ||
                  activeEntry.environment?.cuda ||
                  activeEntry.environment?.pytorch ||
                  activeEntry.environment?.flash_attn ||
                  (activeEntry.capability_tags || []).length > 0 ||
                  activeEntry.download?.url ||
                  activeEntry.source_file ||
                  activeEntry.image_path ||
                  activeEntry.paper?.title ||
                  activeEntry.dataset_download?.primary_method ||
                  (activeEntry.dataset_download?.sources || []).length > 0 ||
                  (activeEntry.dataset_download?.notes || []).length > 0 ||
                  activeEntry.credential_requirements?.mode ||
                  (activeEntry.credential_requirements?.items || []).length >
                    0 ||
                  (activeEntry.credential_requirements?.notes || []).length >
                    0 ||
                  hasBenchRisk(activeEntry) ? (
                    <div className="mt-6 border-t border-black/6 pt-6">
                      <div className="space-y-4 pt-4">
                        {activeEntry.paper?.title ? (
                          <section>
                            <div className="text-xs uppercase tracking-[0.18em] text-[#9B9389]">
                              {t.paperTitle}
                            </div>
                            <div className="mt-2 text-sm leading-7 text-[#544E46]">
                              {activeEntry.paper.title}
                            </div>
                          </section>
                        ) : null}
                        {(activeEntry.capability_tags || []).length > 0 ? (
                          <section>
                            <div className="text-xs uppercase tracking-[0.18em] text-[#9B9389]">
                              Tags
                            </div>
                            <div className="mt-3 flex flex-wrap gap-2">
                              {(activeEntry.capability_tags || [])
                                .slice(0, 10)
                                .map((tag) => (
                                  <BenchChip key={tag}>{tag}</BenchChip>
                                ))}
                            </div>
                          </section>
                        ) : null}
                        {(activeEntry.primary_outputs || []).length > 0 ? (
                          <section>
                            <div className="text-xs uppercase tracking-[0.18em] text-[#9B9389]">
                              {t.primaryOutputs}
                            </div>
                            <div className="mt-3 flex flex-wrap gap-2">
                              {(activeEntry.primary_outputs || []).map(
                                (item) => (
                                  <BenchChip key={item}>{item}</BenchChip>
                                ),
                              )}
                            </div>
                          </section>
                        ) : null}
                        {(activeEntry.launch_profiles || []).length > 0 ? (
                          <section>
                            <div className="text-xs uppercase tracking-[0.18em] text-[#9B9389]">
                              {t.launchProfiles}
                            </div>
                            <div className="mt-3 space-y-3">
                              {(activeEntry.launch_profiles || []).map(
                                (profile, index) => (
                                  <div
                                    key={`${profile.id || profile.label || "launch"}-${index}`}
                                    className="rounded-[10px] border border-black/8 bg-white/50 px-3 py-3 text-sm leading-7 text-[#544E46]"
                                  >
                                    <div className="font-medium text-[#342F2B]">
                                      {profile.label || profile.id || t.unknown}
                                    </div>
                                    {profile.id ? (
                                      <div className="text-xs uppercase tracking-[0.14em] text-[#9B9389]">
                                        {profile.id}
                                      </div>
                                    ) : null}
                                    {profile.description ? (
                                      <div className="mt-1">
                                        {profile.description}
                                      </div>
                                    ) : null}
                                  </div>
                                ),
                              )}
                            </div>
                          </section>
                        ) : null}
                        {activeEntry.environment?.python ||
                        activeEntry.environment?.cuda ||
                        activeEntry.environment?.pytorch ||
                        activeEntry.environment?.flash_attn ? (
                          <section>
                            <div className="text-xs uppercase tracking-[0.18em] text-[#7A8796]">
                              {t.runtimeEnvironment}
                            </div>
                            <div className="mt-2 grid gap-2 text-sm leading-7 text-[#342F2B] sm:grid-cols-2">
                              {activeEntry.environment?.python ? (
                                <div>
                                  {t.python}: {activeEntry.environment.python}
                                </div>
                              ) : null}
                              {activeEntry.environment?.cuda ? (
                                <div>
                                  {t.cuda}: {activeEntry.environment.cuda}
                                </div>
                              ) : null}
                              {activeEntry.environment?.pytorch ? (
                                <div>
                                  {t.pytorch}: {activeEntry.environment.pytorch}
                                </div>
                              ) : null}
                              {activeEntry.environment?.flash_attn ? (
                                <div>
                                  {t.flashAttn}:{" "}
                                  {activeEntry.environment.flash_attn}
                                </div>
                              ) : null}
                            </div>
                          </section>
                        ) : null}
                        {(activeEntry.environment?.key_packages || []).length >
                        0 ? (
                          <section>
                            <div className="text-xs uppercase tracking-[0.18em] text-[#9B9389]">
                              {t.keyPackages}
                            </div>
                            <div className="mt-3 flex flex-wrap gap-2">
                              {(activeEntry.environment?.key_packages || [])
                                .slice(0, 10)
                                .map((pkg) => (
                                  <BenchChip key={pkg}>{pkg}</BenchChip>
                                ))}
                            </div>
                          </section>
                        ) : null}
                        {(activeEntry.environment?.notes || []).length > 0 ? (
                          <section>
                            <div className="text-xs uppercase tracking-[0.18em] text-[#9B9389]">
                              {t.environmentNotes}
                            </div>
                            <div className="mt-2 space-y-2 text-sm leading-7 text-[#544E46]">
                              {(activeEntry.environment?.notes || []).map(
                                (note) => (
                                  <div key={note}>{note}</div>
                                ),
                              )}
                            </div>
                          </section>
                        ) : null}
                        {activeEntry.dataset_download?.primary_method ||
                        (activeEntry.dataset_download?.sources || []).length >
                          0 ||
                        (activeEntry.dataset_download?.notes || []).length >
                          0 ? (
                          <section>
                            <div className="text-xs uppercase tracking-[0.18em] text-[#9B9389]">
                              {t.datasetRoute}
                            </div>
                            {activeEntry.dataset_download?.primary_method ? (
                              <div className="mt-2 text-sm leading-7 text-[#342F2B]">
                                {t.datasetMethod}:{" "}
                                {activeEntry.dataset_download.primary_method}
                              </div>
                            ) : null}
                            {(activeEntry.dataset_download?.sources || [])
                              .length > 0 ? (
                              <div className="mt-3 space-y-3">
                                {(
                                  activeEntry.dataset_download?.sources || []
                                ).map((source, index) => (
                                  <div
                                    key={`${source.url || source.note || source.kind || "source"}-${index}`}
                                    className="rounded-[10px] border border-black/8 bg-white/50 px-3 py-3 text-sm leading-7 text-[#544E46]"
                                  >
                                    <div className="font-medium text-[#342F2B]">
                                      {[source.kind, source.access]
                                        .filter(Boolean)
                                        .join(" · ") || t.unknown}
                                    </div>
                                    {source.url ? (
                                      <a
                                        href={source.url}
                                        target="_blank"
                                        rel="noreferrer"
                                        className="mt-1 block break-all text-[#4F6971] hover:underline"
                                      >
                                        {source.url}
                                      </a>
                                    ) : null}
                                    {source.note ? (
                                      <div className="mt-1">{source.note}</div>
                                    ) : null}
                                  </div>
                                ))}
                              </div>
                            ) : null}
                            {(activeEntry.dataset_download?.notes || [])
                              .length > 0 ? (
                              <div className="mt-3 space-y-2 text-sm leading-7 text-[#544E46]">
                                <div className="text-xs uppercase tracking-[0.18em] text-[#9B9389]">
                                  {t.datasetNotes}
                                </div>
                                {(
                                  activeEntry.dataset_download?.notes || []
                                ).map((note) => (
                                  <div key={note}>{note}</div>
                                ))}
                              </div>
                            ) : null}
                          </section>
                        ) : null}
                        {activeEntry.credential_requirements?.mode ||
                        (activeEntry.credential_requirements?.items || [])
                          .length > 0 ||
                        (activeEntry.credential_requirements?.notes || [])
                          .length > 0 ? (
                          <section>
                            <div className="text-xs uppercase tracking-[0.18em] text-[#9B9389]">
                              {t.credentialRequirements}
                            </div>
                            {activeEntry.credential_requirements?.mode ? (
                              <div className="mt-2 text-sm leading-7 text-[#342F2B]">
                                {t.credentialMode}:{" "}
                                {credentialModeText(
                                  activeEntry.credential_requirements.mode,
                                  locale,
                                )}
                              </div>
                            ) : null}
                            {(activeEntry.credential_requirements?.items || [])
                              .length > 0 ? (
                              <div className="mt-3">
                                <div className="text-xs uppercase tracking-[0.18em] text-[#9B9389]">
                                  {t.credentialItems}
                                </div>
                                <div className="mt-2 flex flex-wrap gap-2">
                                  {(
                                    activeEntry.credential_requirements
                                      ?.items || []
                                  ).map((item) => (
                                    <BenchChip key={item}>{item}</BenchChip>
                                  ))}
                                </div>
                              </div>
                            ) : null}
                            {(activeEntry.credential_requirements?.notes || [])
                              .length > 0 ? (
                              <div className="mt-3 space-y-2 text-sm leading-7 text-[#544E46]">
                                <div className="text-xs uppercase tracking-[0.18em] text-[#9B9389]">
                                  {t.credentialNotes}
                                </div>
                                {(
                                  activeEntry.credential_requirements?.notes ||
                                  []
                                ).map((note) => (
                                  <div key={note}>{note}</div>
                                ))}
                              </div>
                            ) : null}
                          </section>
                        ) : null}
                        {hasBenchRisk(activeEntry) ? (
                          <section>
                            <div className="text-xs uppercase tracking-[0.18em] text-[#9B9389]">
                              {t.fullRisks}
                            </div>
                            {(activeEntry.risk_flags || []).length > 0 ? (
                              <div className="mt-3">
                                <div className="text-xs uppercase tracking-[0.18em] text-[#9B9389]">
                                  {t.riskFlags}
                                </div>
                                <div className="mt-2 flex flex-wrap gap-2">
                                  {(activeEntry.risk_flags || []).map(
                                    (flag) => (
                                      <BenchChip key={flag}>{flag}</BenchChip>
                                    ),
                                  )}
                                </div>
                              </div>
                            ) : null}
                            {(activeEntry.risk_notes || []).length > 0 ? (
                              <div className="mt-3 space-y-2 text-sm leading-7 text-[#544E46]">
                                <div className="text-xs uppercase tracking-[0.18em] text-[#9B9389]">
                                  {t.riskNotes}
                                </div>
                                {(activeEntry.risk_notes || []).map((note) => (
                                  <div key={note}>{note}</div>
                                ))}
                              </div>
                            ) : null}
                          </section>
                        ) : null}
                        {activeEntry.download?.url ? (
                          <section>
                            <div className="text-xs uppercase tracking-[0.18em] text-[#9B9389]">
                              {t.download}
                            </div>
                            <div className="mt-2 break-all text-sm leading-7 text-[#544E46]">
                              {activeEntry.download.url}
                            </div>
                          </section>
                        ) : null}
                        {activeEntry.source_file ? (
                          <section>
                            <div className="text-xs uppercase tracking-[0.18em] text-[#9B9389]">
                              {t.sourceFile}
                            </div>
                            <div className="mt-2 break-all text-sm leading-7 text-[#544E46]">
                              {activeEntry.source_file}
                            </div>
                          </section>
                        ) : null}
                        {activeEntry.image_path ? (
                          <section>
                            <div className="text-xs uppercase tracking-[0.18em] text-[#9B9389]">
                              {t.imagePath}
                            </div>
                            <div className="mt-2 break-all text-sm leading-7 text-[#544E46]">
                              {activeEntry.image_path}
                            </div>
                          </section>
                        ) : null}
                      </div>
                    </div>
                  ) : null}

                  {paperAuthors.length > 0 ||
                  paperInstitutions.length > 0 ||
                  rawPaper?.license ||
                  rawPaper?.doi ||
                  paperLinks.length > 0 ||
                  paperNotes.length > 0 ? (
                    <div className="mt-6 border-t border-black/6 pt-6">
                      <div className="text-xs uppercase tracking-[0.18em] text-[#9B9389]">
                        {t.paperContext}
                      </div>
                      <div className="mt-4 rounded-[10px] border border-black/8 bg-white/56 px-4 py-4">
                        {paperAuthors.length > 0 ? (
                          <MetadataRow
                            label={t.paperAuthors}
                            value={paperAuthors.join(", ")}
                          />
                        ) : null}
                        {paperInstitutions.length > 0 ? (
                          <MetadataRow
                            label={t.paperInstitutions}
                            value={paperInstitutions.join(" | ")}
                          />
                        ) : null}
                        {rawPaper?.license ? (
                          <MetadataRow
                            label={t.paperLicense}
                            value={String(rawPaper.license)}
                          />
                        ) : null}
                        {rawPaper?.doi ? (
                          <MetadataRow
                            label={t.paperDoi}
                            value={String(rawPaper.doi)}
                          />
                        ) : null}
                        {paperLinks.length > 0 ? (
                          <div className="pt-3">
                            <div className="text-xs uppercase tracking-[0.18em] text-[#9B9389]">
                              {t.paperLinks}
                            </div>
                            <div className="mt-2 flex flex-wrap gap-2">
                              {paperLinks.map((item) => (
                                <Button
                                  key={item.key}
                                  variant="outline"
                                  className="rounded-[12px] border-black/10 bg-white/72 text-[#2D2A26] hover:bg-white"
                                  asChild
                                >
                                  <a
                                    href={item.url}
                                    target="_blank"
                                    rel="noreferrer"
                                  >
                                    {formatCatalogFieldLabel(item.key)}
                                  </a>
                                </Button>
                              ))}
                            </div>
                          </div>
                        ) : null}
                        {paperNotes.length > 0 ? (
                          <div className="pt-3">
                            <div className="space-y-2 text-sm leading-7 text-[#544E46]">
                              {paperNotes.map((note) => (
                                <div key={note}>{note}</div>
                              ))}
                            </div>
                          </div>
                        ) : null}
                      </div>
                    </div>
                  ) : null}

                  {activeEntry.download?.archive_type ||
                  activeEntry.download?.local_dir_name ||
                  packageNotes.length > 0 ? (
                    <div className="mt-6 border-t border-black/6 pt-6">
                      <div className="text-xs uppercase tracking-[0.18em] text-[#9B9389]">
                        {t.packageInfo}
                      </div>
                      <div className="mt-4 rounded-[10px] border border-black/8 bg-white/56 px-4 py-4">
                        {activeEntry.download?.archive_type ? (
                          <MetadataRow
                            label={t.archiveType}
                            value={activeEntry.download.archive_type}
                          />
                        ) : null}
                        {activeEntry.download?.local_dir_name ? (
                          <MetadataRow
                            label={t.localDirName}
                            value={activeEntry.download.local_dir_name}
                          />
                        ) : null}
                        {packageNotes.length > 0 ? (
                          <div className="pt-3">
                            <div className="text-xs uppercase tracking-[0.18em] text-[#9B9389]">
                              {t.packageNotes}
                            </div>
                            <div className="mt-2 space-y-2 text-sm leading-7 text-[#544E46]">
                              {packageNotes.map((note) => (
                                <div key={note}>{note}</div>
                              ))}
                            </div>
                          </div>
                        ) : null}
                      </div>
                    </div>
                  ) : null}

                  {activeEntry.aisb_direction ||
                  activeEntry.schema_version != null ||
                  rawDisplay?.palette_seed ||
                  rawDisplay?.art_style ||
                  rawDisplay?.accent_priority ||
                  displayTags.length > 0 ? (
                    <div className="mt-6 border-t border-black/6 pt-6">
                      <div className="text-xs uppercase tracking-[0.18em] text-[#9B9389]">
                        {t.catalogStyle}
                      </div>
                      <div className="mt-4 rounded-[10px] border border-black/8 bg-white/56 px-4 py-4">
                        {activeEntry.aisb_direction ? (
                          <MetadataRow
                            label={t.directionFilterLabel}
                            value={activeEntry.aisb_direction}
                          />
                        ) : null}
                        {activeEntry.schema_version != null ? (
                          <MetadataRow
                            label={t.schemaVersion}
                            value={String(activeEntry.schema_version)}
                          />
                        ) : null}
                        {rawDisplay?.palette_seed ? (
                          <MetadataRow
                            label={t.paletteSeed}
                            value={String(rawDisplay.palette_seed)}
                          />
                        ) : null}
                        {rawDisplay?.art_style ? (
                          <MetadataRow
                            label={t.artStyle}
                            value={String(rawDisplay.art_style)}
                          />
                        ) : null}
                        {rawDisplay?.accent_priority ? (
                          <MetadataRow
                            label={t.accentPriority}
                            value={String(rawDisplay.accent_priority)}
                          />
                        ) : null}
                        {displayTags.length > 0 ? (
                          <div className="pt-3">
                            <div className="text-xs uppercase tracking-[0.18em] text-[#9B9389]">
                              {t.displayTags}
                            </div>
                            <div className="mt-2 flex flex-wrap gap-2">
                              {displayTags.map((item, index) => (
                                <BenchChip key={`${item}-${index}`}>
                                  {item}
                                </BenchChip>
                              ))}
                            </div>
                          </div>
                        ) : null}
                      </div>
                    </div>
                  ) : null}

                  {additionalCatalogFields.length > 0 ? (
                    <div className="mt-6 border-t border-black/6 pt-6">
                      <div className="text-xs uppercase tracking-[0.18em] text-[#9B9389]">
                        {t.additionalCatalogFields}
                      </div>
                      <div className="mt-4 space-y-4">
                        {additionalCatalogFields.map(([key, value]) => (
                          <section key={key}>
                            <div className="text-xs uppercase tracking-[0.18em] text-[#9B9389]">
                              {formatCatalogFieldLabel(key)}
                            </div>
                            <div className="mt-2">
                              <AutoCatalogValue value={value} locale={locale} />
                            </div>
                          </section>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </section>

                <aside className="space-y-4">
                  <section className="rounded-[10px] bg-white/62 px-5 py-5 shadow-[0_20px_60px_-52px_rgba(44,39,34,0.24)] backdrop-blur-xl">
                    <div className="text-xs uppercase tracking-[0.18em] text-[#9B9389]">
                      {t.reproduction}
                    </div>
                    <MetadataRow label={t.catalogId} value={activeEntry.id} />
                    <MetadataRow
                      label={t.version}
                      value={activeEntry.version || t.unknown}
                    />
                    <MetadataRow
                      label={t.requiresPaper}
                      value={
                        activeEntry.requires_paper == null
                          ? t.unknown
                          : activeEntry.requires_paper
                            ? t.yes
                            : t.no
                      }
                    />
                    <MetadataRow
                      label={t.requiresExecution}
                      value={
                        activeEntry.requires_execution == null
                          ? t.unknown
                          : activeEntry.requires_execution
                            ? t.yes
                            : t.no
                      }
                    />
                    <MetadataRow
                      label={t.snapshotStatus}
                      value={
                        activeEntry.snapshot_status
                          ? humanizeEnum(activeEntry.snapshot_status, locale)
                          : t.unknown
                      }
                    />
                    <MetadataRow
                      label={t.supportLevel}
                      value={
                        activeEntry.support_level
                          ? humanizeEnum(activeEntry.support_level, locale)
                          : t.unknown
                      }
                    />
                    <MetadataRow
                      label={t.modeFilterLabel}
                      value={activeEntry.task_mode || t.unknown}
                    />
                    <MetadataRow
                      label={t.timeBand}
                      value={activeEntry.time_band || t.unknown}
                    />
                    <MetadataRow
                      label={t.costBand}
                      value={activeEntry.cost_band || t.unknown}
                    />
                    <MetadataRow
                      label={t.difficultyFilterLabel}
                      value={activeEntry.difficulty || t.unknown}
                    />
                    <MetadataRow
                      label={t.integrityLevel}
                      value={activeEntry.integrity_level || t.unknown}
                    />
                    <MetadataRow
                      label={t.resourceConfidence}
                      value={resourceConfidenceText(
                        activeEntry.compatibility?.resource_confidence,
                        locale,
                      )}
                    />
                    <MetadataRow
                      label={t.recommendationScore}
                      value={
                        typeof activeEntry.recommendation?.score === "number"
                          ? activeEntry.recommendation.score.toFixed(1)
                          : t.unknown
                      }
                    />
                    <MetadataRow
                      label={t.sortFastest}
                      value={
                        formatTimeUpperHours(
                          activeEntry.recommendation?.time_upper_hours,
                          locale,
                        ) || t.unknown
                      }
                    />
                    <MetadataRow
                      label={t.annualFee}
                      value={
                        formatAnnualFee(activeEntry.commercial?.annual_fee) ||
                        t.unknown
                      }
                    />
                  </section>

                  <section className="rounded-[10px] bg-white/62 px-5 py-5 shadow-[0_20px_60px_-52px_rgba(44,39,34,0.24)] backdrop-blur-xl">
                    <div className="text-xs uppercase tracking-[0.18em] text-[#9B9389]">
                      {t.whyRecommended}
                    </div>
                    <div className="mt-3 space-y-2 text-sm leading-7 text-[#544E46]">
                      {(
                        activeEntry.recommendation?.reasons ||
                        activeEntry.compatibility?.recommended_reasons ||
                        activeEntry.compatibility?.minimum_reasons ||
                        []
                      )
                        .slice(0, 3)
                        .map((reason) => (
                          <div key={reason}>{reason}</div>
                        ))}
                    </div>
                  </section>

                  {formatResourceSpec(activeEntry.resources?.minimum).length >
                    0 ||
                  formatResourceSpec(activeEntry.resources?.recommended)
                    .length > 0 ? (
                    <section className="rounded-[10px] bg-white/62 px-5 py-5 shadow-[0_20px_60px_-52px_rgba(44,39,34,0.24)] backdrop-blur-xl">
                      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-1">
                        <div>
                          <div className="text-xs uppercase tracking-[0.18em] text-[#9B9389]">
                            {t.minimum}
                          </div>
                          <div className="mt-3">
                            {renderSpec(activeEntry.resources?.minimum)}
                          </div>
                        </div>
                        <div>
                          <div className="text-xs uppercase tracking-[0.18em] text-[#9B9389]">
                            {t.recommendedSpec}
                          </div>
                          <div className="mt-3">
                            {renderSpec(activeEntry.resources?.recommended)}
                          </div>
                        </div>
                      </div>
                    </section>
                  ) : null}

                  {activeEntry.paper?.url || activeEntry.source_file ? (
                    <section className="rounded-[10px] bg-white/62 px-5 py-5 shadow-[0_20px_60px_-52px_rgba(44,39,34,0.24)] backdrop-blur-xl">
                      <div className="text-xs uppercase tracking-[0.18em] text-[#9B9389]">
                        {t.links}
                      </div>
                      <div className="mt-3 space-y-3">
                        {activeEntry.paper?.url ? (
                          <Button
                            variant="outline"
                            className="rounded-[12px] border-black/10 bg-white/72 text-[#2D2A26] hover:bg-white"
                            asChild
                          >
                            <a
                              href={activeEntry.paper.url}
                              target="_blank"
                              rel="noreferrer"
                            >
                              {t.paperLink}
                            </a>
                          </Button>
                        ) : null}
                        {activeEntry.source_file ? (
                          <div className="text-sm leading-7 text-[#544E46]">
                            {activeEntry.source_file}
                          </div>
                        ) : null}
                      </div>
                    </section>
                  ) : null}
                </aside>
              </div>
            </div>
          ) : (
            <div className="space-y-5">
              <section className="flex flex-wrap items-center justify-between gap-4 border-b border-black/8 px-1 pb-4">
                <div className="min-w-0">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[#8C8276]">
                    {libraryView === "library" ? t.libraryTab : t.storeTab}
                  </div>
                  <div className="mt-1 text-[24px] font-semibold tracking-[-0.04em] text-[#2E2A25]">
                    {libraryView === "library"
                      ? t.libraryHeading
                      : t.browseShelf}
                  </div>
                  <div className="mt-1 max-w-3xl text-sm leading-7 text-[#6B6257]">
                    {libraryView === "library" ? t.libraryIntro : t.description}
                  </div>
                </div>
                <Button
                  variant="outline"
                  className="rounded-[12px] border-black/10 bg-white/70 px-5 text-[#2D2A26] hover:bg-white"
                  onClick={
                    libraryView === "library" ? openStoreView : openLibraryView
                  }
                >
                  {libraryView === "library" ? t.returnToStore : t.openLibrary}
                </Button>
              </section>

              {libraryView === "library" ? (
                <section className="flex flex-wrap gap-2 pb-1">
                  <BenchLibrarySummaryCard
                    label={t.libraryInstalled}
                    value={libraryStats.installedCount}
                  />
                  <BenchLibrarySummaryCard
                    label={t.linkedQuests}
                    value={libraryStats.linkedQuestTotal}
                  />
                  <BenchLibrarySummaryCard
                    label={t.runningQuestCount}
                    value={libraryStats.runningQuestTotal}
                  />
                  <BenchLibrarySummaryCard
                    label={t.libraryReady}
                    value={libraryStats.readyCount}
                  />
                </section>
              ) : null}

              {libraryView === "store" && featuredEntry ? (
                <section className="overflow-hidden rounded-[10px] border border-black/8 bg-[rgba(252,247,241,0.82)] p-4 shadow-[0_24px_76px_-58px_rgba(44,39,34,0.34)] backdrop-blur-xl">
                  <div className="mb-3 flex items-center justify-between gap-4">
                    <div className="min-w-0 text-[11px] font-semibold uppercase tracking-[0.22em] text-[#8C8276]">
                      {t.featuredHeading}
                    </div>
                    <div className="text-xs text-[#8A8278]">
                      {recommendedEntries.length}
                    </div>
                  </div>

                  <div className="grid gap-4 xl:grid-cols-[minmax(0,1.45fr)_minmax(300px,0.9fr)]">
                    <button
                      type="button"
                      onClick={() => setSelectedEntryId(featuredEntry.id)}
                      className="relative overflow-hidden rounded-[10px] text-left"
                      data-onboarding-id="benchstore-featured-card"
                    >
                      <BenchArtwork
                        entry={featuredEntry}
                        className="h-[320px]"
                      />
                      <div className="pointer-events-none absolute inset-x-4 bottom-4 rounded-[12px] bg-white/24 px-4 py-3 backdrop-blur-md">
                        <div className="flex flex-wrap gap-2">
                          <BenchChip>
                            {compatibilityLabel(
                              featuredEntry.compatibility,
                              locale,
                            )}
                          </BenchChip>
                          {featuredEntry.paper?.year ? (
                            <BenchChip>{featuredEntry.paper.year}</BenchChip>
                          ) : null}
                        </div>
                        <div className="mt-2 max-w-2xl text-sm leading-6 text-[#28241f]">
                          {featuredEntry.one_line ||
                            featuredEntry.task_description ||
                            t.unknown}
                        </div>
                      </div>
                    </button>

                    <div className="rounded-[10px] bg-[linear-gradient(180deg,rgba(22,26,31,0.94),rgba(29,34,41,0.88))] px-5 py-5 text-white shadow-[0_20px_60px_-52px_rgba(13,17,24,0.52)] backdrop-blur-xl">
                      <div className="flex flex-wrap gap-2">
                        <BenchChip>
                          {compatibilityLabel(
                            featuredEntry.compatibility,
                            locale,
                          )}
                        </BenchChip>
                        {featuredEntry.install_state?.status === "installed" ? (
                          <BenchChip>{t.installedState}</BenchChip>
                        ) : null}
                      </div>
                      <div className="mt-3 text-[28px] font-semibold leading-[1.08] tracking-[-0.04em]">
                        {featuredEntry.name}
                      </div>
                      <div className="mt-3 text-sm leading-7 text-white/78">
                        {featuredEntry.one_line ||
                          featuredEntry.task_description ||
                          t.unknown}
                      </div>
                      <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-white/60">
                        <span>
                          {featuredEntry.paper?.venue ||
                            featuredEntry.task_mode ||
                            t.unknown}
                        </span>
                        {featuredEntry.time_band ? (
                          <span>{featuredEntry.time_band}</span>
                        ) : null}
                        {featuredEntry.difficulty ? (
                          <span>{featuredEntry.difficulty}</span>
                        ) : null}
                      </div>
                      <div className="mt-4 space-y-2 text-sm leading-7 text-white/74">
                        {(
                          featuredEntry.recommendation?.reasons ||
                          featuredEntry.compatibility?.recommended_reasons ||
                          featuredEntry.compatibility?.minimum_reasons ||
                          []
                        )
                          .slice(0, 2)
                          .map((reason) => (
                            <div key={reason}>{reason}</div>
                          ))}
                      </div>
                      <div className="mt-6 flex flex-wrap gap-3">
                        <Button
                          className="rounded-[12px] bg-[linear-gradient(135deg,#D0A886,#B8C7CF)] px-6 text-[#211D19] hover:opacity-95"
                          onClick={() => setSelectedEntryId(featuredEntry.id)}
                        >
                          {t.openDetail}
                        </Button>
                        {featuredEntry.install_state?.status === "installed" ? (
                          <Button
                            variant="outline"
                            className="rounded-[12px] border-white/20 bg-white/10 text-white hover:bg-white/16"
                            onClick={async () => {
                              setActionError(null);
                              try {
                                const payload = await getBenchStoreSetupPacket(
                                  featuredEntry.id,
                                  locale,
                                );
                                await onStartWithSetupPacket?.(
                                  payload.setup_packet,
                                );
                              } catch (caught) {
                                setActionError(
                                  caught instanceof Error
                                    ? caught.message
                                    : String(caught),
                                );
                              }
                            }}
                          >
                            {t.startAction}
                          </Button>
                        ) : null}
                      </div>
                    </div>
                  </div>

                  {actionError ? (
                    <div className="mt-3 text-sm text-[#955F56]">
                      {actionError}
                    </div>
                  ) : null}
                </section>
              ) : null}

              <div className="rounded-[10px] border border-black/8 bg-[rgba(250,246,240,0.76)] p-4 shadow-[0_18px_52px_-44px_rgba(44,39,34,0.26)] backdrop-blur-xl">
                <div
                  className={cn(
                    "grid gap-3",
                    libraryView === "library"
                      ? "xl:grid-cols-[minmax(0,1fr)_220px]"
                      : "xl:grid-cols-[minmax(0,1fr)_220px_220px_auto]",
                  )}
                >
                  <label className="relative block">
                    <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-[#8D867C]" />
                    <input
                      value={query}
                      onChange={(event) => setQuery(event.target.value)}
                      placeholder={t.searchPlaceholder}
                      className="h-12 w-full rounded-[12px] border border-black/10 bg-white/70 pl-11 pr-4 text-sm text-[#2D2A26] outline-none transition focus:border-black/15 focus:bg-white"
                    />
                  </label>
                  {libraryView === "store" ? (
                    <select
                      value={fitFilter}
                      onChange={(event) =>
                        setFitFilter(event.target.value as FitFilter)
                      }
                      className="h-12 rounded-[12px] border border-black/10 bg-white/70 px-4 text-sm text-[#2D2A26] outline-none transition focus:border-black/15 focus:bg-white"
                    >
                      <option value="all">
                        {t.fitFilterLabel}: {t.fitFilterAll}
                      </option>
                      <option value="best_match">
                        {t.fitFilterLabel}: {t.fitFilterBest}
                      </option>
                      <option value="runnable">
                        {t.fitFilterLabel}: {t.fitFilterRunnable}
                      </option>
                      <option value="installed">
                        {t.fitFilterLabel}: {t.fitFilterInstalled}
                      </option>
                      <option value="hide_unsupported">
                        {t.fitFilterLabel}: {t.fitFilterHideUnsupported}
                      </option>
                    </select>
                  ) : null}
                  <select
                    value={sortMode}
                    onChange={(event) =>
                      setSortMode(event.target.value as SortMode)
                    }
                    className="h-12 rounded-[12px] border border-black/10 bg-white/70 px-4 text-sm text-[#2D2A26] outline-none transition focus:border-black/15 focus:bg-white"
                  >
                    <option value="recommended">{t.sortRecommended}</option>
                    <option value="recommended_spec">
                      {t.sortRecommendedSpec}
                    </option>
                    <option value="minimum_spec">{t.sortMinimumSpec}</option>
                    <option value="fastest">{t.sortFastest}</option>
                    <option value="easiest">{t.sortEasiest}</option>
                    <option value="name">{t.sortName}</option>
                    <option value="year">{t.sortYear}</option>
                  </select>
                  {libraryView === "store" ? (
                    <Button
                      variant="outline"
                      className="h-12 rounded-[12px] border-black/10 bg-white/70 px-5 text-[#2D2A26] hover:bg-white"
                      onClick={() =>
                        setShowExtendedFilters((current) => !current)
                      }
                    >
                      {showExtendedFilters ? t.fewerFilters : t.moreFilters}
                    </Button>
                  ) : null}
                </div>
                {libraryView === "store" && showExtendedFilters ? (
                  <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                    <select
                      value={modeFilter}
                      onChange={(event) => setModeFilter(event.target.value)}
                      className="h-12 rounded-[12px] border border-black/10 bg-white/70 px-4 text-sm text-[#2D2A26] outline-none transition focus:border-black/15 focus:bg-white"
                    >
                      <option value="all">
                        {t.modeFilterLabel}: {t.fitFilterAll}
                      </option>
                      {(catalog?.filter_options?.task_mode || []).map(
                        (value) => (
                          <option key={value} value={value}>
                            {t.modeFilterLabel}: {value}
                          </option>
                        ),
                      )}
                    </select>
                    <select
                      value={trackFilter}
                      onChange={(event) => setTrackFilter(event.target.value)}
                      className="h-12 rounded-[12px] border border-black/10 bg-white/70 px-4 text-sm text-[#2D2A26] outline-none transition focus:border-black/15 focus:bg-white"
                    >
                      <option value="all">
                        {t.trackFilterLabel}: {t.fitFilterAll}
                      </option>
                      {(catalog?.filter_options?.track_fit || []).map(
                        (value) => (
                          <option key={value} value={value}>
                            {t.trackFilterLabel}: {value}
                          </option>
                        ),
                      )}
                    </select>
                    <select
                      value={accessFilter}
                      onChange={(event) => setAccessFilter(event.target.value)}
                      className="h-12 rounded-[12px] border border-black/10 bg-white/70 px-4 text-sm text-[#2D2A26] outline-none transition focus:border-black/15 focus:bg-white"
                    >
                      <option value="all">
                        {t.accessFilterLabel}: {t.fitFilterAll}
                      </option>
                      {(catalog?.filter_options?.data_access || []).map(
                        (value) => (
                          <option key={value} value={value}>
                            {t.accessFilterLabel}: {value}
                          </option>
                        ),
                      )}
                    </select>
                    <select
                      value={costFilter}
                      onChange={(event) => setCostFilter(event.target.value)}
                      className="h-12 rounded-[12px] border border-black/10 bg-white/70 px-4 text-sm text-[#2D2A26] outline-none transition focus:border-black/15 focus:bg-white"
                    >
                      <option value="all">
                        {t.costFilterLabel}: {t.fitFilterAll}
                      </option>
                      {(catalog?.filter_options?.cost_band || []).map(
                        (value) => (
                          <option key={value} value={value}>
                            {t.costFilterLabel}: {value}
                          </option>
                        ),
                      )}
                    </select>
                    <select
                      value={difficultyFilter}
                      onChange={(event) =>
                        setDifficultyFilter(event.target.value)
                      }
                      className="h-12 rounded-[12px] border border-black/10 bg-white/70 px-4 text-sm text-[#2D2A26] outline-none transition focus:border-black/15 focus:bg-white"
                    >
                      <option value="all">
                        {t.difficultyFilterLabel}: {t.fitFilterAll}
                      </option>
                      {(catalog?.filter_options?.difficulty || []).map(
                        (value) => (
                          <option key={value} value={value}>
                            {t.difficultyFilterLabel}: {value}
                          </option>
                        ),
                      )}
                    </select>
                    <select
                      value={executionFilter}
                      onChange={(event) =>
                        setExecutionFilter(event.target.value as BooleanFilter)
                      }
                      className="h-12 rounded-[12px] border border-black/10 bg-white/70 px-4 text-sm text-[#2D2A26] outline-none transition focus:border-black/15 focus:bg-white"
                    >
                      <option value="all">
                        {t.executionFilterLabel}:{" "}
                        {booleanFilterText("all", locale)}
                      </option>
                      {(catalog?.filter_options?.requires_execution || []).map(
                        (value) => (
                          <option key={value} value={value}>
                            {t.executionFilterLabel}:{" "}
                            {booleanFilterText(value as BooleanFilter, locale)}
                          </option>
                        ),
                      )}
                    </select>
                    <select
                      value={paperFilter}
                      onChange={(event) =>
                        setPaperFilter(event.target.value as BooleanFilter)
                      }
                      className="h-12 rounded-[12px] border border-black/10 bg-white/70 px-4 text-sm text-[#2D2A26] outline-none transition focus:border-black/15 focus:bg-white"
                    >
                      <option value="all">
                        {t.paperFilterLabel}: {booleanFilterText("all", locale)}
                      </option>
                      {(catalog?.filter_options?.requires_paper || []).map(
                        (value) => (
                          <option key={value} value={value}>
                            {t.paperFilterLabel}:{" "}
                            {booleanFilterText(value as BooleanFilter, locale)}
                          </option>
                        ),
                      )}
                    </select>
                  </div>
                ) : null}
              </div>

              <section className="space-y-4">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-sm font-semibold uppercase tracking-[0.18em] text-[#7E8B97]">
                    {libraryView === "library"
                      ? t.libraryHeading
                      : t.browseShelf}
                  </div>
                  <div className="text-xs text-[#8A8278]">
                    {filteredEntries.length}
                  </div>
                </div>
                {loading ? (
                  <div className="rounded-[10px] border border-black/10 bg-white/45 px-5 py-10 text-center text-sm text-[#7F776D]">
                    Loading BenchStore...
                  </div>
                ) : error ? (
                  <div className="rounded-[10px] border border-black/10 bg-white/45 px-5 py-10 text-center text-sm text-[#7F776D]">
                    {error}
                  </div>
                ) : filteredEntries.length === 0 ? (
                  <div className="rounded-[10px] border border-dashed border-black/10 bg-white/45 px-5 py-10 text-center text-sm text-[#7F776D]">
                    {query.trim()
                      ? t.noResults
                      : libraryView === "library"
                        ? t.libraryEmpty
                        : t.empty}
                  </div>
                ) : (
                  <>
                    {libraryView === "library" ? (
                      <div className="space-y-4">
                        {browseEntries.map((entry) => (
                          <BenchLibraryCard
                            key={entry.id}
                            entry={entry}
                            locale={locale}
                            linkedQuests={linkedQuestMap.get(entry.id) || []}
                            onOpen={() => setSelectedEntryId(entry.id)}
                            onOpenQuest={(questId) => {
                              onClose();
                              navigate(`/projects/${questId}`);
                            }}
                          />
                        ))}
                      </div>
                    ) : (
                      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                        {browseEntries.map((entry) => (
                          <BenchCard
                            key={entry.id}
                            entry={entry}
                            locale={locale}
                            linkedQuestCount={
                              linkedQuestMap.get(entry.id)?.length || 0
                            }
                            activeQuestCount={
                              (linkedQuestMap.get(entry.id) || []).filter(
                                (quest) => isQuestRunning(quest),
                              ).length
                            }
                            onOpen={() => setSelectedEntryId(entry.id)}
                          />
                        ))}
                      </div>
                    )}
                    {filteredEntries.length > 12 ? (
                      <div className="flex justify-center">
                        <Button
                          variant="outline"
                          className="rounded-[12px] border-black/10 bg-white/70 px-5 text-[#2D2A26] hover:bg-white"
                          onClick={() =>
                            setShowAllBrowse((current) => !current)
                          }
                        >
                          {showAllBrowse
                            ? t.showLess
                            : `${t.showAll} (${filteredEntries.length})`}
                        </Button>
                      </div>
                    ) : null}
                  </>
                )}
              </section>
            </div>
          )}
        </div>
        <div
          data-onboarding-id="benchstore-assistant-surface"
          className="feed-scrollbar modal-scrollbar min-h-0 overflow-y-scroll overscroll-contain px-3 pb-3 pr-4 pt-3 sm:px-4 sm:pb-4 sm:pr-5 sm:pt-5"
          onWheel={(event) => event.stopPropagation()}
        >
          {setupQuestId ? (
            <SetupAgentQuestPanel questId={setupQuestId} locale={locale} />
          ) : (
            <SetupAgentRail
              locale={locale}
              setupPacket={null}
              loading={setupQuestCreating}
              error={null}
              assistantLabel={`${runnerLabel(activeRunnerName)} · SetupAgent`}
              onStartAssist={async (message) => {
                let setupPacket: BenchSetupPacket | null = null;
                if (
                  activeEntry?.id &&
                  activeEntry.install_state?.status === "installed"
                ) {
                  try {
                    const payload = await getBenchStoreSetupPacket(
                      activeEntry.id,
                      locale,
                    );
                    setupPacket = payload.setup_packet;
                  } catch {
                    setupPacket = null;
                  }
                }
                await onRequestSetupAgent?.({
                  message,
                  entry: activeEntry,
                  setupPacket,
                });
              }}
            />
          )}
        </div>
      </div>
    </OverlayDialog>
  );
}

export default BenchStoreDialog;
