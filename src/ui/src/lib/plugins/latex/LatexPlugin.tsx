"use client";

import * as React from "react";
import dynamic from "next/dynamic";
import {
  FileText,
  Save,
  Loader2,
  Play,
  AlertTriangle,
  Download,
  ZoomIn,
  ZoomOut,
  Link2,
  AtSign,
  History,
  RotateCcw,
  GitCompare,
} from "lucide-react";
import type { PluginComponentProps } from "@/lib/types/plugin";
import { cn } from "@/lib/utils";
import { client as questClient } from "@/lib/api";
import {
  listFiles,
  getFileContent,
  getFileContentSnapshot,
  updateFileContent,
  type FileContentSnapshot,
} from "@/lib/api/files";
import { useFileTreeStore } from "@/lib/stores/file-tree";
import { ProjectSyncClient } from "@/lib/plugins/notebook/lib/project-sync";
import { useAuthStore } from "@/lib/stores/auth";
import { checkProjectAccess } from "@/lib/api/projects";
import { configureMonacoLoader } from "@/lib/monaco";
import type { PDFDocumentProxy } from "pdfjs-dist";
import {
  PdfHighlighter,
  PdfLoader,
  type IHighlight,
  type ScaledPosition,
  type Content,
} from "@/lib/plugins/pdf-viewer/react-pdf-highlighter";
import { PAGE_DIMENSIONS, ZOOM_LEVELS } from "@/lib/plugins/pdf-viewer/types";
import { PDF_CMAP_URL, PDF_WORKER_SRC } from "@/lib/plugins/pdf-viewer/lib/pdf-utils";
import {
  compileLatex,
  compareLatexVersions,
  createLatexVersion,
  getLatexManifest,
  getLatexBuild,
  getLatexBuildLogText,
  getLatexBuildPdfBlob,
  listLatexBuilds,
  listLatexVersions,
  restoreLatexVersion,
  syncTexEditLatexBuild,
  type LatexCompiler,
  type LatexBuildStatus,
  type LatexBuildError,
  type LatexLogItem,
  type LatexSyncTexSelection,
  type LatexVersionCompareResponse,
  type LatexVersionSummary,
} from "@/lib/api/latex";
import { useI18n } from "@/lib/i18n/useI18n";
import { useWorkspaceSurfaceStore } from "@/lib/stores/workspace-surface";
import { toFilesResourcePath } from "@/lib/utils/resource-paths";
import { supportsSocketIo } from "@/lib/runtime/quest-runtime";
import {
  BIBTEX_LANGUAGE_ID,
  LATEX_LANGUAGE_ID,
  ensureMonacoLatexLanguages,
} from "@/lib/monaco-latex";
import {
  LATEX_OPEN_FILE_EVENT,
  consumeLatexOpenFileRequests,
  type LatexOpenFileRequest,
} from "@/lib/latex/open-queue";

const MonacoEditor = dynamic(() => import("@monaco-editor/react"), { ssr: false });
configureMonacoLoader();

type LatexTabContext = {
  projectId?: string;
  latexFolderId?: string;
  mainFileId?: string | null;
  openFileId?: string | null;
  readOnly?: boolean;
};

function useIsDarkMode(): boolean {
  const [isDark, setIsDark] = React.useState<boolean>(() => {
    if (typeof document === "undefined") return false;
    return document.documentElement.classList.contains("dark");
  });

  React.useEffect(() => {
    const el = document.documentElement;
    const observer = new MutationObserver(() => {
      setIsDark(el.classList.contains("dark"));
    });
    observer.observe(el, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, []);

  return isDark;
}

type PdfSurfaceProps = {
  pdfDocument: PDFDocumentProxy;
  zoomFactor: number;
  highlights: IHighlight[];
  onPageWidth: (width: number) => void;
  onPointDoubleClick?: (point: PdfSourcePoint) => void;
};

type PdfWordBox = {
  left: number;
  top: number;
  right: number;
  bottom: number;
  width?: number;
  height?: number;
};

type PdfSourcePoint = {
  page: number;
  x: number;
  y: number;
  word?: string | null;
  contextWords?: string[] | null;
  contextIndex?: number | null;
  wordBBox?: PdfWordBox | null;
  wordCenter?: { x: number; y: number } | null;
};

type LatexFileMeta = {
  id: string;
  name: string;
  path?: string;
  relativePath?: string;
  role?: string;
  editable?: boolean;
};

type LatexSaveState = "idle" | "saving" | "error";
type LatexSaveTrigger = "manual" | "auto" | "lifecycle" | "compile";
type PendingJumpLocation = {
  fileId: string | null;
  line: number;
  column?: number | null;
  word?: string | null;
  selection?: LatexSyncTexSelection | null;
};

function getLatexIssueIdentity(issue: {
  resourcePath?: string | null;
  resourceName?: string | null;
  line?: number | null;
  message: string;
  severity: "error" | "warning";
}) {
  return [
    issue.resourcePath || issue.resourceName || "",
    issue.line || 0,
    issue.severity,
    issue.message,
  ].join("::");
}

type CitationEntry = {
  key: string;
  title?: string;
  author?: string;
  sourceFile: string;
};

type LabelEntry = {
  key: string;
  sourceFile: string;
};

type LatexExternalConflict = {
  fileId: string;
  remoteContent: string;
  remoteRevision?: string | null;
  remoteUpdatedAt?: string | null;
  reason: "poll" | "focus" | "visibility" | "diff" | "save_conflict";
};

type BibSnippet = {
  id: string;
  labelKey: string;
  snippet: string;
};

type LatexCompletionSnippet = {
  label: string;
  insertText: string;
  detail: string;
  documentation?: string;
  filterText?: string;
};

const normalizeBuildErrors = (
  errors?: LatexBuildError[] | null,
  logItems?: LatexLogItem[] | null
): LatexBuildError[] => {
  if (Array.isArray(logItems) && logItems.length > 0) {
    return logItems.map((item) => ({
      path: item.file ?? null,
      line: typeof item.line === "number" ? item.line : null,
      message: item.message,
      severity: item.severity === "warning" ? "warning" : "error",
    }));
  }
  return Array.isArray(errors) ? errors : [];
};

const LATEX_COMPILER_OPTIONS: LatexCompiler[] = ["pdflatex", "xelatex", "lualatex"];
const LATEX_AUTOSAVE_DELAY_MS = 1000;
const LATEX_EXTERNAL_CHECK_INTERVAL_MS = 4000;
const LATEX_AUTO_VERSION_INTERVAL_MS = 5 * 60 * 1000;
const LATEX_AUTO_COMPILE_ON_SAVE_STORAGE_PREFIX = "ds:latex:auto-compile-on-save";
const BIB_SNIPPETS: BibSnippet[] = [
  {
    id: "article",
    labelKey: "bib_snippet_article",
    snippet:
      "@article{key,\n  title = {},\n  author = {},\n  journal = {},\n  year = {},\n}\n",
  },
  {
    id: "inproceedings",
    labelKey: "bib_snippet_inproceedings",
    snippet:
      "@inproceedings{key,\n  title = {},\n  author = {},\n  booktitle = {},\n  year = {},\n}\n",
  },
  {
    id: "misc",
    labelKey: "bib_snippet_misc",
    snippet:
      "@misc{key,\n  title = {},\n  author = {},\n  year = {},\n  note = {},\n}\n",
  },
];

const LATEX_ENVIRONMENT_SNIPPETS: LatexCompletionSnippet[] = [
  {
    label: "begin{comment}",
    filterText: "\\begin{comment}",
    detail: "comment environment",
    insertText: "\\begin{comment}\n\t$0\n\\end{comment}",
    documentation: "Insert a complete comment environment.",
  },
  {
    label: "begin{figure}",
    filterText: "\\begin{figure}",
    detail: "figure environment",
    insertText: "\\begin{figure}[${1:htbp}]\n\t\\centering\n\t$0\n\t\\caption{${2:Caption}}\n\t\\label{fig:${3:label}}\n\\end{figure}",
  },
  {
    label: "begin{table}",
    filterText: "\\begin{table}",
    detail: "table environment",
    insertText: "\\begin{table}[${1:htbp}]\n\t\\centering\n\t$0\n\t\\caption{${2:Caption}}\n\t\\label{tab:${3:label}}\n\\end{table}",
  },
  {
    label: "begin{equation}",
    filterText: "\\begin{equation}",
    detail: "equation environment",
    insertText: "\\begin{equation}\n\t$0\n\\end{equation}",
  },
  {
    label: "begin{align}",
    filterText: "\\begin{align}",
    detail: "align environment",
    insertText: "\\begin{align}\n\t$0\n\\end{align}",
  },
  {
    label: "begin{itemize}",
    filterText: "\\begin{itemize}",
    detail: "itemize environment",
    insertText: "\\begin{itemize}\n\t\\item $0\n\\end{itemize}",
  },
  {
    label: "begin{enumerate}",
    filterText: "\\begin{enumerate}",
    detail: "enumerate environment",
    insertText: "\\begin{enumerate}\n\t\\item $0\n\\end{enumerate}",
  },
];

const LATEX_COMMAND_SNIPPETS: LatexCompletionSnippet[] = [
  {
    label: "\\begin",
    detail: "LaTeX environment",
    insertText: "\\begin{${1:environment}}\n\t$0\n\\end{${1:environment}}",
  },
  {
    label: "\\section",
    detail: "section heading",
    insertText: "\\section{${1:Title}}",
  },
  {
    label: "\\subsection",
    detail: "subsection heading",
    insertText: "\\subsection{${1:Title}}",
  },
  {
    label: "\\label",
    detail: "label",
    insertText: "\\label{${1:key}}",
  },
  {
    label: "\\ref",
    detail: "reference",
    insertText: "\\ref{${1:key}}",
  },
  {
    label: "\\eqref",
    detail: "equation reference",
    insertText: "\\eqref{${1:key}}",
  },
  {
    label: "\\cite",
    detail: "citation",
    insertText: "\\cite{${1:key}}",
  },
  {
    label: "\\textbf",
    detail: "bold text",
    insertText: "\\textbf{${1:text}}",
  },
  {
    label: "\\emph",
    detail: "emphasized text",
    insertText: "\\emph{${1:text}}",
  },
];

function normalizeCompiler(value?: string | null): LatexCompiler {
  if (value === "xelatex" || value === "lualatex") return value;
  return "pdflatex";
}

function latexAutoCompileOnSaveStorageKey(projectId?: string, folderId?: string) {
  return [
    LATEX_AUTO_COMPILE_ON_SAVE_STORAGE_PREFIX,
    projectId || "unknown-project",
    folderId || "unknown-folder",
  ].join(":");
}

function normalizeLatexPath(value?: string | null) {
  return String(value || "")
    .trim()
    .replace(/\\/g, "/")
    .replace(/^\.\/+/, "")
    .replace(/^\/+/, "")
    .toLowerCase();
}

function parseBibEntries(text: string, sourceFile: string): CitationEntry[] {
  const entries: CitationEntry[] = [];
  const source = String(text || "");
  const entryRegex = /@([a-zA-Z]+)\s*\{\s*([^,\s]+)\s*,([\s\S]*?)\n\}/g;
  let match: RegExpExecArray | null = null;
  while ((match = entryRegex.exec(source))) {
    const body = match[3] || "";
    const title = body.match(/title\s*=\s*[\{"']([^}"']+)/i)?.[1]?.trim();
    const author = body.match(/author\s*=\s*[\{"']([^}"']+)/i)?.[1]?.trim();
    entries.push({
      key: match[2].trim(),
      title,
      author,
      sourceFile,
    });
  }
  return entries;
}

function parseLatexLabels(text: string, sourceFile: string): LabelEntry[] {
  const entries: LabelEntry[] = [];
  const source = String(text || "");
  const regex = /\\label\{([^}]+)\}/g;
  let match: RegExpExecArray | null = null;
  while ((match = regex.exec(source))) {
    entries.push({
      key: match[1].trim(),
      sourceFile,
    });
  }
  return entries;
}

function resolveLatexFileId(files: LatexFileMeta[], rawPath?: string | null) {
  const normalized = normalizeLatexPath(rawPath);
  if (!normalized) return null;

  const exact = files.find(
    (file) =>
      normalizeLatexPath(file.path) === normalized ||
      normalizeLatexPath(file.relativePath) === normalized ||
      normalizeLatexPath(file.name) === normalized
  );
  if (exact) return exact.id;

  const basename = normalized.split("/").filter(Boolean).pop();
  if (!basename) return null;

  const byBasename = files.find((file) =>
    [file.path, file.relativePath, file.name].some((value) =>
      normalizeLatexPath(value).endsWith(`/${basename}`)
    )
  );
  if (byBasename) return byBasename.id;

  const simpleName = files.find((file) => file.name.toLowerCase() === basename);
  return simpleName?.id ?? null;
}

function latexFileDisplayPath(file?: LatexFileMeta | null) {
  return file?.relativePath || file?.path || file?.name || "";
}

function isEditableLatexManifestFile(file: LatexFileMeta) {
  if (file.editable === true) return true;
  const lower = (file.name || file.path || "").toLowerCase();
  return (
    lower.endsWith(".tex") ||
    lower.endsWith(".bib") ||
    lower.endsWith(".cls") ||
    lower.endsWith(".sty") ||
    lower.endsWith(".bst") ||
    lower.endsWith(".bbx") ||
    lower.endsWith(".cbx")
  );
}

function resolveLatexOpenRequestFileId(files: LatexFileMeta[], request: LatexOpenFileRequest) {
  if (request.fileId && files.some((file) => file.id === request.fileId)) {
    return request.fileId;
  }
  return resolveLatexFileId(files, request.filePath);
}

function latexWordCharacter(char: string) {
  return /[\p{L}\p{N}_:-]/u.test(char);
}

type PdfWordHit = {
  word: string;
  clientBox: PdfWordBox;
  contextWords?: string[];
  contextIndex?: number;
};

function rectDistanceToPoint(rect: DOMRect | PdfWordBox, x: number, y: number) {
  const dx = x < rect.left ? rect.left - x : x > rect.right ? x - rect.right : 0;
  const dy = y < rect.top ? rect.top - y : y > rect.bottom ? y - rect.bottom : 0;
  return Math.hypot(dx, dy);
}

function rectContainsPoint(rect: DOMRect | PdfWordBox, x: number, y: number, tolerance = 0) {
  return (
    x >= rect.left - tolerance &&
    x <= rect.right + tolerance &&
    y >= rect.top - tolerance &&
    y <= rect.bottom + tolerance
  );
}

function rangeBoundingBox(range: Range): PdfWordBox | null {
  const rects = Array.from(range.getClientRects()).filter((rect) => rect.width > 0 && rect.height > 0);
  if (rects.length === 0) return null;
  const left = Math.min(...rects.map((rect) => rect.left));
  const top = Math.min(...rects.map((rect) => rect.top));
  const right = Math.max(...rects.map((rect) => rect.right));
  const bottom = Math.max(...rects.map((rect) => rect.bottom));
  return {
    left,
    top,
    right,
    bottom,
    width: right - left,
    height: bottom - top,
  };
}

function firstTextNode(element: Element): Text | null {
  const walker = element.ownerDocument.createTreeWalker(element, NodeFilter.SHOW_TEXT);
  let node = walker.nextNode();
  while (node) {
    if (node.nodeType === Node.TEXT_NODE && (node.textContent || "").trim()) {
      return node as Text;
    }
    node = walker.nextNode();
  }
  return null;
}

function textLayerWordEntries(doc: Document, textLayer: Element) {
  const entries: Array<{ word: string; clientBox: PdfWordBox }> = [];
  for (const element of Array.from(textLayer.querySelectorAll("span, div"))) {
    const textNode = firstTextNode(element);
    const source = textNode?.textContent || "";
    if (!textNode || !source.trim()) continue;
    let index = 0;
    while (index < source.length) {
      if (!latexWordCharacter(source[index])) {
        index += 1;
        continue;
      }
      const start = index;
      index += 1;
      while (index < source.length && latexWordCharacter(source[index])) index += 1;
      const word = source.slice(start, index).trim();
      if (!word) continue;
      const range = doc.createRange();
      try {
        range.setStart(textNode, start);
        range.setEnd(textNode, index);
        const clientBox = rangeBoundingBox(range);
        if (clientBox) entries.push({ word, clientBox });
      } finally {
        range.detach?.();
      }
    }
  }
  return entries;
}

function hitTestPdfTextLayerWord(
  event: React.MouseEvent<HTMLDivElement>,
  pageElement: HTMLElement
): PdfWordHit | null {
  const doc = event.currentTarget.ownerDocument;
  const textLayer = pageElement.querySelector(".textLayer");
  if (!textLayer) return null;

  const clientX = event.clientX;
  const clientY = event.clientY;
  const entries = textLayerWordEntries(doc, textLayer)
    .map((entry) => ({
      ...entry,
      score:
        (rectContainsPoint(entry.clientBox, clientX, clientY, 2) ? 100000 : 0) -
        rectDistanceToPoint(entry.clientBox, clientX, clientY),
    }))
    .sort((a, b) => b.score - a.score);

  const best = entries[0];
  if (!best || best.score < -12) return null;
  const centerY = (best.clientBox.top + best.clientBox.bottom) / 2;
  const tolerance = Math.max(Number(best.clientBox.height || 0) * 0.9, 6);
  const lineEntries = entries
    .filter((entry) => {
      const entryCenterY = (entry.clientBox.top + entry.clientBox.bottom) / 2;
      return Math.abs(entryCenterY - centerY) <= tolerance;
    })
    .sort((a, b) => a.clientBox.left - b.clientBox.left);
  const lineIndex = lineEntries.findIndex((entry) => entry === best);
  const contextStart = Math.max(0, lineIndex - 5);
  const contextEnd = Math.min(lineEntries.length, lineIndex + 6);
  const contextSlice = lineEntries.slice(contextStart, contextEnd);
  return {
    word: best.word,
    clientBox: best.clientBox,
    contextWords: contextSlice.map((entry) => entry.word),
    contextIndex: Math.max(0, lineIndex - contextStart),
  };
}

function PdfSurface({ pdfDocument, zoomFactor, highlights, onPageWidth, onPointDoubleClick }: PdfSurfaceProps) {
  React.useEffect(() => {
    let cancelled = false;
    pdfDocument
      .getPage(1)
      .then((page) => {
        if (cancelled) return;
        const viewport = page.getViewport({ scale: 1 });
        if (viewport?.width) {
          onPageWidth(viewport.width);
        }
      })
      .catch(() => {
        if (!cancelled) onPageWidth(PAGE_DIMENSIONS.A4_WIDTH);
      });
    return () => {
      cancelled = true;
    };
  }, [onPageWidth, pdfDocument]);

  const safeZoomFactor = Number.isFinite(zoomFactor) && zoomFactor > 0 ? zoomFactor : 1;
  const pdfScaleValue =
    Math.abs(safeZoomFactor - 1) < 0.001 ? "page-width" : `page-width:${safeZoomFactor}`;

  return (
    <div
      className="relative h-full w-full"
      onDoubleClickCapture={(event) => {
        if (!onPointDoubleClick) return;
        const target = event.target;
        if (!(target instanceof Element)) return;
        const pageElement = target.closest(".page[data-page-number]") as HTMLElement | null;
        if (!pageElement) return;
        const pageNumber = Number(pageElement.dataset.pageNumber || "");
        if (!Number.isFinite(pageNumber) || pageNumber < 1) return;
        const pageRect = pageElement.getBoundingClientRect();
        if (!pageRect.width || !pageRect.height) return;
        const localX = event.clientX - pageRect.left;
        const localY = event.clientY - pageRect.top;
        if (localX < 0 || localY < 0 || localX > pageRect.width || localY > pageRect.height) return;
        event.preventDefault();
        event.stopPropagation();
        const wordHit = hitTestPdfTextLayerWord(event, pageElement);
        void pdfDocument
          .getPage(pageNumber)
          .then((page) => {
            const viewport = page.getViewport({ scale: 1 });
            const scaleX = viewport.width / pageRect.width;
            const scaleY = viewport.height / pageRect.height;
            const toPdfX = (clientX: number) => (clientX - pageRect.left) * scaleX;
            const toPdfY = (clientY: number) => (clientY - pageRect.top) * scaleY;
            const wordBBox = wordHit?.clientBox
              ? {
                  left: toPdfX(wordHit.clientBox.left),
                  top: toPdfY(wordHit.clientBox.top),
                  right: toPdfX(wordHit.clientBox.right),
                  bottom: toPdfY(wordHit.clientBox.bottom),
                  width: wordHit.clientBox.width ? wordHit.clientBox.width * scaleX : undefined,
                  height: wordHit.clientBox.height ? wordHit.clientBox.height * scaleY : undefined,
                }
              : null;
            const wordCenter = wordBBox
              ? {
                  x: (wordBBox.left + wordBBox.right) / 2,
                  y: (wordBBox.top + wordBBox.bottom) / 2,
                }
              : null;
            const x = wordCenter?.x ?? localX * scaleX;
            const y = wordCenter?.y ?? localY * scaleY;
            onPointDoubleClick({
              page: pageNumber,
              x,
              y,
              word: wordHit?.word ?? null,
              contextWords: wordHit?.contextWords ?? null,
              contextIndex: wordHit?.contextIndex ?? null,
              wordBBox,
              wordCenter,
            });
          })
          .catch(() => {
            onPointDoubleClick({
              page: pageNumber,
              x: localX,
              y: localY,
              word: wordHit?.word ?? null,
              contextWords: wordHit?.contextWords ?? null,
              contextIndex: wordHit?.contextIndex ?? null,
            });
          });
      }}
    >
      <PdfHighlighter<IHighlight>
        pdfDocument={pdfDocument}
        pdfScaleValue={pdfScaleValue}
        highlights={highlights}
        highlightTransform={() => <></>}
        onScrollChange={() => {}}
        scrollRef={() => {}}
        onSelectionFinished={(
          _position: ScaledPosition,
          _content: Content,
          _hideTipAndSelection: () => void,
          _transformSelection: () => void
        ) => null}
        enableAreaSelection={() => false}
      />
    </div>
  );
}

export default function LatexPlugin({ context, tabId, setDirty, setTitle }: PluginComponentProps) {
  const custom = (context.customData ?? {}) as LatexTabContext;
  const projectId = custom.projectId ?? undefined;
  const latexFolderId = custom.latexFolderId ?? context.resourceId ?? undefined;
  const viewReadOnly = Boolean(custom.readOnly);
  const user = useAuthStore((s) => s.user);
  const { t, language } = useI18n("latex");
  const updateWorkspaceTabState = useWorkspaceSurfaceStore((state) => state.updateTabState);
  const setWorkspaceActiveIssue = useWorkspaceSurfaceStore((state) => state.setActiveIssue);
  const [roleWritable, setRoleWritable] = React.useState<boolean | null>(null);

  const isDark = useIsDarkMode();

  const updateFileMeta = useFileTreeStore((s) => s.updateFileMeta);

  const [files, setFiles] = React.useState<LatexFileMeta[]>([]);
  const [manifestRefreshNonce, setManifestRefreshNonce] = React.useState(0);
  const initialFileId = custom.openFileId ?? custom.mainFileId ?? null;
  const [activeFileId, setActiveFileId] = React.useState<string | null>(initialFileId);
  const [activeFileName, setActiveFileName] = React.useState<string>("main.tex");
  const [manifestMainFileId, setManifestMainFileId] = React.useState<string | null>(
    custom.mainFileId ?? null
  );
  const compileMainFileId = React.useMemo(() => {
    if (custom.mainFileId) return custom.mainFileId;
    if (manifestMainFileId) return manifestMainFileId;
    return files.find((file) => file.role === "main")?.id ??
      files.find((file) => file.name.toLowerCase() === "main.tex")?.id ??
      null;
  }, [custom.mainFileId, files, manifestMainFileId]);
  const [initialText, setInitialText] = React.useState<string>("");
  const [syncState, setSyncState] = React.useState<"idle" | "loading" | "ready" | "error">("idle");
  const [saveState, setSaveState] = React.useState<LatexSaveState>("idle");
  const [saveTrigger, setSaveTrigger] = React.useState<LatexSaveTrigger>("manual");
  const [saveError, setSaveError] = React.useState<string | null>(null);
  const [externalConflict, setExternalConflict] = React.useState<LatexExternalConflict | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [isDirty, setIsDirty] = React.useState(false);
  const [dirtyVersion, setDirtyVersion] = React.useState(0);
  const [buildId, setBuildId] = React.useState<string | null>(null);
  const [buildStatus, setBuildStatus] = React.useState<LatexBuildStatus | "idle">("idle");
  const [buildError, setBuildError] = React.useState<string | null>(null);
  const [buildErrors, setBuildErrors] = React.useState<LatexBuildError[]>([]);
  const [synctexReady, setSynctexReady] = React.useState(false);
  const [synctexBusy, setSynctexBusy] = React.useState(false);
  const [synctexError, setSynctexError] = React.useState<string | null>(null);
  const [compiler, setCompiler] = React.useState<LatexCompiler>("pdflatex");
  const [autoCompileOnSave, setAutoCompileOnSave] = React.useState(true);
  const [currentBranch, setCurrentBranch] = React.useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = React.useState(false);
  const [latexVersions, setLatexVersions] = React.useState<LatexVersionSummary[]>([]);
  const [latexVersionsHead, setLatexVersionsHead] = React.useState<string | null>(null);
  const [selectedVersionId, setSelectedVersionId] = React.useState<string | null>(null);
  const [historyLoading, setHistoryLoading] = React.useState(false);
  const [historyActionBusy, setHistoryActionBusy] = React.useState(false);
  const [historyError, setHistoryError] = React.useState<string | null>(null);
  const [historyCompare, setHistoryCompare] = React.useState<LatexVersionCompareResponse | null>(null);
  const [historyLabel, setHistoryLabel] = React.useState("");
  const [historyDescription, setHistoryDescription] = React.useState("");
  const [pdfObjectUrl, setPdfObjectUrl] = React.useState<string | null>(null);
  const [logText, setLogText] = React.useState<string | null>(null);
  const [zoomScale, setZoomScale] = React.useState<number>(1);
  const [pdfPageWidth, setPdfPageWidth] = React.useState<number>(PAGE_DIMENSIONS.A4_WIDTH);
  const [pdfPaneWidth, setPdfPaneWidth] = React.useState<number>(0);
  const [splitRatio, setSplitRatio] = React.useState<number>(0.58);
  const [isResizing, setIsResizing] = React.useState(false);
  const [isWideLayout, setIsWideLayout] = React.useState(false);
  const [referencePanelOpen, setReferencePanelOpen] = React.useState(false);
  const [bibPanelOpen, setBibPanelOpen] = React.useState(false);
  const [assistQuery, setAssistQuery] = React.useState("");
  const [citationIndex, setCitationIndex] = React.useState<CitationEntry[]>([]);
  const [labelIndex, setLabelIndex] = React.useState<LabelEntry[]>([]);
  const emptyHighlights = React.useMemo(() => [] as IHighlight[], []);

  const lastSavedRef = React.useRef<string>("");
  const isDirtyRef = React.useRef(false);
  const saveStateRef = React.useRef<LatexSaveState>("idle");
  const buildStatusRef = React.useRef<LatexBuildStatus | "idle">("idle");
  const activeFileIdRef = React.useRef<string | null>(activeFileId);
  const saveInFlightRef = React.useRef<{ fileId: string; promise: Promise<boolean> } | null>(null);
  const failedSaveTextRef = React.useRef<string | null>(null);
  const lastSaveTriggerRef = React.useRef<LatexSaveTrigger>("manual");
  const savedRevisionRef = React.useRef<string | null>(null);
  const loadedRevisionRef = React.useRef<string | null>(null);
  const externalConflictRef = React.useRef<LatexExternalConflict | null>(null);
  const externalCheckInFlightRef = React.useRef(false);
  const lastAutoVersionAtRef = React.useRef(0);
  const aiVersionTimerRef = React.useRef<number | null>(null);
  const yDocRef = React.useRef<any>(null);
  const yTextRef = React.useRef<any>(null);
  const syncRef = React.useRef<ProjectSyncClient | null>(null);
  const remoteOriginRef = React.useRef<string>("");
  const pendingUpdatesRef = React.useRef<Uint8Array[]>([]);
  const flushTimerRef = React.useRef<number | null>(null);
  const bindingCleanupRef = React.useRef<null | (() => void)>(null);
  const applyingRemoteRef = React.useRef(false);
  const lastResetTimestampRef = React.useRef<number>(0);
  const forceSeedRef = React.useRef<boolean>(false);
  const [resetNonce, setResetNonce] = React.useState(0);
  const pdfUrlRef = React.useRef<string | null>(null);
  const lastLoadedPdfBuildIdRef = React.useRef<string | null>(null);
  const splitContainerRef = React.useRef<HTMLDivElement | null>(null);
  const pdfPaneRef = React.useRef<HTMLDivElement | null>(null);
  const editorRef = React.useRef<any>(null);
  const boundEditorFileIdRef = React.useRef<string | null>(null);
  const pendingJumpRef = React.useRef<PendingJumpLocation | null>(null);
  const citationIndexRef = React.useRef<CitationEntry[]>([]);
  const labelIndexRef = React.useRef<LabelEntry[]>([]);
  const latexCompletionDisposablesRef = React.useRef<Array<{ dispose?: () => void }>>([]);

  const effectiveReadOnly = viewReadOnly || roleWritable === false;
  const socketAuthMode = "user";
  const canUseRealtimeSync = supportsSocketIo();
  const isBibFile = activeFileName.toLowerCase().endsWith(".bib");

  React.useEffect(() => {
    activeFileIdRef.current = activeFileId;
  }, [activeFileId]);

  React.useEffect(() => {
    isDirtyRef.current = isDirty;
  }, [isDirty]);

  React.useEffect(() => {
    saveStateRef.current = saveState;
  }, [saveState]);

  React.useEffect(() => {
    buildStatusRef.current = buildStatus;
  }, [buildStatus]);

  React.useEffect(() => {
    if (typeof window === "undefined") return;
    const stored = window.localStorage.getItem(
      latexAutoCompileOnSaveStorageKey(projectId, latexFolderId)
    );
    // Default-on: only an explicit "0" disables manual-save auto compile.
    setAutoCompileOnSave(stored !== "0");
  }, [latexFolderId, projectId]);

  const updateAutoCompileOnSave = React.useCallback(
    (enabled: boolean) => {
      setAutoCompileOnSave(enabled);
      if (typeof window === "undefined") return;
      window.localStorage.setItem(
        latexAutoCompileOnSaveStorageKey(projectId, latexFolderId),
        enabled ? "1" : "0"
      );
    },
    [latexFolderId, projectId]
  );

  const setEditorDirty = React.useCallback(
    (nextDirty: boolean) => {
      isDirtyRef.current = nextDirty;
      setIsDirty(nextDirty);
      setDirty(nextDirty);
    },
    [setDirty]
  );

  const markDirty = React.useCallback(() => {
    failedSaveTextRef.current = null;
    setSaveError(null);
    setEditorDirty(true);
    setDirtyVersion((version) => version + 1);
    if (saveStateRef.current === "error") {
      saveStateRef.current = "idle";
      setSaveState("idle");
    }
  }, [setEditorDirty]);

  const getCurrentText = React.useCallback(() => {
    const ytext = yTextRef.current;
    return ytext ? String(ytext.toString?.() ?? "") : "";
  }, []);

  const setExternalConflictState = React.useCallback((conflict: LatexExternalConflict | null) => {
    externalConflictRef.current = conflict;
    setExternalConflict(conflict);
  }, []);

  const applyFileSnapshotToEditor = React.useCallback(
    (fileId: string, snapshot: Pick<FileContentSnapshot, "content" | "revision" | "updated_at" | "size" | "mime_type">) => {
      const content = String(snapshot.content ?? "");
      const revision = snapshot.revision ?? null;
      const ydoc = yDocRef.current;
      const ytext = yTextRef.current;
      let origin = remoteOriginRef.current;
      if (!origin) {
        origin = `ds-external:${projectId || "project"}:${fileId}:${Date.now()}`;
        remoteOriginRef.current = origin;
      }

      applyingRemoteRef.current = true;
      try {
        if (ydoc && ytext) {
          ydoc.transact(() => {
            const length = Number(ytext.length || 0);
            if (length) ytext.delete(0, length);
            if (content) ytext.insert(0, content);
          }, origin);
        }

        const editor = editorRef.current;
        const model = editor?.getModel?.();
        if (model && typeof model.getValue === "function" && model.getValue() !== content) {
          model.setValue(content);
        }
      } finally {
        applyingRemoteRef.current = false;
      }

      setInitialText(content);
      lastSavedRef.current = content;
      loadedRevisionRef.current = revision;
      savedRevisionRef.current = revision;
      failedSaveTextRef.current = null;
      setSaveError(null);
      saveStateRef.current = "idle";
      setSaveState("idle");
      setEditorDirty(false);
      setExternalConflictState(null);
      if (fileId) {
        updateFileMeta(fileId, {
          updatedAt: snapshot.updated_at ?? undefined,
          size: typeof snapshot.size === "number" ? snapshot.size : undefined,
          mimeType: snapshot.mime_type ?? undefined,
        });
      }
    },
    [projectId, setEditorDirty, setExternalConflictState, updateFileMeta]
  );

  const checkExternalSnapshot = React.useCallback(
    async (reason: LatexExternalConflict["reason"] = "poll") => {
      const fileId = activeFileIdRef.current;
      if (!fileId || syncState !== "ready") return;
      if (saveStateRef.current === "saving") return;
      if (externalCheckInFlightRef.current) return;

      externalCheckInFlightRef.current = true;
      try {
        const snapshot = await getFileContentSnapshot(fileId);
        if (activeFileIdRef.current !== fileId) return;
        const remoteRevision = snapshot.revision ?? null;
        const knownRevision = savedRevisionRef.current;
        const changed = remoteRevision && knownRevision
          ? remoteRevision !== knownRevision
          : String(snapshot.content ?? "") !== lastSavedRef.current;
        if (!changed) return;

        if (isDirtyRef.current) {
          setExternalConflictState({
            fileId,
            remoteContent: String(snapshot.content ?? ""),
            remoteRevision,
            remoteUpdatedAt: snapshot.updated_at ?? null,
            reason,
          });
          return;
        }

        applyFileSnapshotToEditor(fileId, snapshot);
      } catch (e) {
        console.warn("[LatexPlugin] External LaTeX refresh check failed:", e);
      } finally {
        externalCheckInFlightRef.current = false;
      }
    },
    [applyFileSnapshotToEditor, setExternalConflictState, syncState]
  );

  const selectedLatexVersion = React.useMemo(
    () => latexVersions.find((version) => version.version_id === selectedVersionId || version.commit === selectedVersionId) ?? latexVersions[0] ?? null,
    [latexVersions, selectedVersionId]
  );

  const loadLatexVersionHistory = React.useCallback(async () => {
    if (!projectId || !latexFolderId) return;
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const payload = await listLatexVersions(projectId, latexFolderId, 50);
      const versions = Array.isArray(payload.versions) ? payload.versions : [];
      setLatexVersions(versions);
      setLatexVersionsHead(payload.head ?? null);
      setSelectedVersionId((current) => {
        if (current && versions.some((version) => version.version_id === current || version.commit === current)) {
          return current;
        }
        return versions[0]?.version_id ?? null;
      });
    } catch (e) {
      setHistoryError(e instanceof Error ? e.message : t("version_history_load_failed"));
    } finally {
      setHistoryLoading(false);
    }
  }, [latexFolderId, projectId, t]);

  const createAutoLatexVersion = React.useCallback(
    async (source: "auto" | "ai", label: string, description: string) => {
      if (!projectId || !latexFolderId || viewReadOnly) return;
      try {
        const result = await createLatexVersion(projectId, latexFolderId, {
          label,
          description,
          source,
          author: source === "ai" ? "ai" : "system",
          allow_empty: false,
        });
        if (result.ok && historyOpen) {
          void loadLatexVersionHistory();
        }
      } catch (e) {
        console.warn("[LatexPlugin] Failed to create automatic LaTeX version:", e);
      }
    },
    [historyOpen, latexFolderId, loadLatexVersionHistory, projectId, viewReadOnly]
  );

  const maybeCreateTimedAutoVersion = React.useCallback(() => {
    const now = Date.now();
    if (now - lastAutoVersionAtRef.current < LATEX_AUTO_VERSION_INTERVAL_MS) return;
    lastAutoVersionAtRef.current = now;
    void createAutoLatexVersion(
      "auto",
      t("version_auto_label"),
      t("version_auto_description")
    );
  }, [createAutoLatexVersion, t]);

  const createManualLatexVersion = React.useCallback(async () => {
    if (!projectId || !latexFolderId || viewReadOnly) return;
    if (externalConflictRef.current) {
      setHistoryError(t("version_resolve_external_change"));
      return;
    }
    if (isDirtyRef.current) {
      const inFlightSave = saveInFlightRef.current?.promise;
      const saved = inFlightSave ? await inFlightSave : false;
      if (!saved && isDirtyRef.current) {
        setHistoryError(t("version_save_before_create"));
        return;
      }
    }
    setHistoryActionBusy(true);
    setHistoryError(null);
    try {
      const result = await createLatexVersion(projectId, latexFolderId, {
        label: historyLabel.trim() || t("version_manual_label"),
        description: historyDescription.trim() || null,
        source: "manual",
        author: "user",
        allow_empty: true,
      });
      if (!result.ok) {
        setHistoryError(result.message || t("version_create_failed"));
        return;
      }
      setHistoryLabel("");
      setHistoryDescription("");
      await loadLatexVersionHistory();
    } catch (e) {
      setHistoryError(e instanceof Error ? e.message : t("version_create_failed"));
    } finally {
      setHistoryActionBusy(false);
    }
  }, [historyDescription, historyLabel, latexFolderId, loadLatexVersionHistory, projectId, t, viewReadOnly]);

  const compareSelectedLatexVersion = React.useCallback(async () => {
    if (!projectId || !latexFolderId || !selectedLatexVersion) return;
    setHistoryActionBusy(true);
    setHistoryError(null);
    try {
      const result = await compareLatexVersions(
        projectId,
        latexFolderId,
        selectedLatexVersion.version_id || selectedLatexVersion.commit,
        latexVersionsHead || "HEAD"
      );
      setHistoryCompare(result);
    } catch (e) {
      setHistoryError(e instanceof Error ? e.message : t("version_compare_failed"));
    } finally {
      setHistoryActionBusy(false);
    }
  }, [latexFolderId, latexVersionsHead, projectId, selectedLatexVersion, t]);

  const restoreSelectedLatexVersion = React.useCallback(
    async (mode: "file" | "folder") => {
      if (!projectId || !latexFolderId || !selectedLatexVersion) return;
      if (viewReadOnly) return;
      if (externalConflictRef.current || isDirtyRef.current) {
        setHistoryError(t("version_restore_dirty_blocked"));
        return;
      }
      const activeMeta = files.find((file) => file.id === activeFileIdRef.current) ?? null;
      const restorePath = mode === "file" ? activeMeta?.path : null;
      if (mode === "file" && !restorePath) {
        setHistoryError(t("version_restore_file_missing"));
        return;
      }
      const confirmed = window.confirm(
        mode === "file"
          ? t("version_restore_file_confirm")
          : t("version_restore_folder_confirm")
      );
      if (!confirmed) return;
      setHistoryActionBusy(true);
      setHistoryError(null);
      try {
        const result = await restoreLatexVersion(projectId, latexFolderId, selectedLatexVersion.version_id, {
          mode,
          path: restorePath,
          expected_head: latexVersionsHead ?? undefined,
          conflict_policy: "fail",
        });
        if (!result.ok) {
          setHistoryError(result.message || t("version_restore_failed"));
          return;
        }
        setManifestRefreshNonce((value) => value + 1);
        await loadLatexVersionHistory();
        if (activeFileIdRef.current) {
          try {
            const snapshot = await getFileContentSnapshot(activeFileIdRef.current);
            applyFileSnapshotToEditor(activeFileIdRef.current, snapshot);
          } catch {
            // The restored folder may have removed the active file. Manifest refresh will choose another file.
          }
        }
      } catch (e) {
        setHistoryError(e instanceof Error ? e.message : t("version_restore_failed"));
      } finally {
        setHistoryActionBusy(false);
      }
    },
    [applyFileSnapshotToEditor, files, latexFolderId, latexVersionsHead, loadLatexVersionHistory, projectId, selectedLatexVersion, t, viewReadOnly]
  );

  React.useEffect(() => {
    if (!historyOpen) return;
    void loadLatexVersionHistory();
  }, [historyOpen, loadLatexVersionHistory]);

  React.useEffect(() => {
    const activeFileMeta =
      files.find((file) => file.id === activeFileId) ??
      files.find((file) => file.name === activeFileName) ??
      null;
    updateWorkspaceTabState(tabId, {
      contentKind: "latex",
      documentMode: "source",
      resourceName: activeFileMeta?.name || activeFileName || context.resourceName || "main.tex",
      resourcePath: activeFileMeta?.path ? toFilesResourcePath(activeFileMeta.path) : undefined,
      isReadOnly: effectiveReadOnly,
      compileState:
        buildStatus === "queued" || buildStatus === "running"
          ? "compiling"
          : saveState === "saving"
            ? "saving"
            : saveState === "error" || saveError || buildStatus === "error"
              ? "error"
              : "idle",
      diagnostics: {
        errors: buildErrors.filter((err) => err.severity !== "warning").length,
        warnings: buildErrors.filter((err) => err.severity === "warning").length,
      },
    });
  }, [
    activeFileId,
    activeFileName,
    buildErrors,
    buildStatus,
    context.resourceName,
    effectiveReadOnly,
    files,
    saveError,
    saveState,
    tabId,
    updateWorkspaceTabState,
  ]);

  React.useEffect(() => {
    setTitle(context.resourceName || t("title"));
  }, [context.resourceName, setTitle, t]);

  // Resolve project write permission (owner/admin/editor).
  React.useEffect(() => {
    if (!projectId) return;
    if (viewReadOnly) {
      setRoleWritable(null);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const access = await checkProjectAccess(projectId);
        if (cancelled) return;
        const role = String(access?.role ?? "");
        setRoleWritable(role === "owner" || role === "admin" || role === "editor");
      } catch {
        if (cancelled) return;
        // If we can't resolve, keep UI permissive but backend will enforce.
        setRoleWritable(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [projectId, viewReadOnly]);

  React.useEffect(() => {
    if (!projectId) {
      setCurrentBranch(null);
      return;
    }
    let cancelled = false;
    void questClient
      .session(projectId)
      .then((payload) => {
        if (cancelled) return;
        const snapshot = payload?.snapshot;
        const branch =
          typeof snapshot?.current_workspace_branch === "string" && snapshot.current_workspace_branch.trim()
            ? snapshot.current_workspace_branch.trim()
            : typeof snapshot?.branch === "string" && snapshot.branch.trim()
              ? snapshot.branch.trim()
              : null;
        setCurrentBranch(branch);
      })
      .catch(() => {
        if (!cancelled) {
          setCurrentBranch(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  // Load the LaTeX project manifest. The manifest is recursive so multi-file
  // papers (sections, shared .bib/.sty files, etc.) are managed in one editor.
  React.useEffect(() => {
    if (!projectId || !latexFolderId) return;
    let cancelled = false;

    const resolveInitialFile = (candidates: LatexFileMeta[], mainFileId?: string | null) => {
      const queuedRequests = consumeLatexOpenFileRequests(projectId, latexFolderId);
      for (const request of queuedRequests.slice().reverse()) {
        const requested = resolveLatexOpenRequestFileId(candidates, request);
        if (requested) {
          if (request.line) {
            pendingJumpRef.current = {
              fileId: requested,
              line: Math.max(1, Number(request.line || 1)),
              column: request.column ?? null,
              word: request.word ?? null,
            };
          }
          return requested;
        }
      }
      const active = activeFileIdRef.current;
      if (active && candidates.some((file) => file.id === active)) return active;
      if (initialFileId && candidates.some((file) => file.id === initialFileId)) return initialFileId;
      if (mainFileId && candidates.some((file) => file.id === mainFileId)) return mainFileId;
      return (
        candidates.find((file) => file.role === "main")?.id ??
        candidates.find((file) => file.name.toLowerCase() === "main.tex")?.id ??
        candidates.find((file) => file.name.toLowerCase().endsWith(".tex"))?.id ??
        candidates[0]?.id ??
        null
      );
    };

    (async () => {
      try {
        const manifest = await getLatexManifest(projectId, latexFolderId);
        if (cancelled) return;
        const candidates = manifest.files
          .map((file) => ({
            id: file.id,
            name: file.name,
            path: file.path || undefined,
            relativePath: file.relative_path || undefined,
            role: file.role,
            editable: file.editable,
          }))
          .filter(isEditableLatexManifestFile)
          .sort((a, b) => {
            if (a.role === "main" && b.role !== "main") return -1;
            if (a.role !== "main" && b.role === "main") return 1;
            return latexFileDisplayPath(a).localeCompare(latexFileDisplayPath(b));
          });
        setFiles(candidates);
        setManifestMainFileId(manifest.main_file_id ?? null);
        setCompiler(normalizeCompiler(manifest.compiler));

        const nextActiveId = resolveInitialFile(candidates, manifest.main_file_id ?? null);
        if (nextActiveId) {
          const meta = candidates.find((file) => file.id === nextActiveId);
          setActiveFileId(nextActiveId);
          setActiveFileName(meta?.name || "main.tex");
        }
      } catch (manifestError) {
        try {
          const items = await listFiles(projectId, latexFolderId);
          if (cancelled) return;
          const candidates = items
            .filter((x) => x.type === "file")
            .map((x) => ({ id: x.id, name: x.name, path: x.path || undefined }))
            .filter(isEditableLatexManifestFile)
            .sort((a, b) => a.name.localeCompare(b.name));
          setFiles(candidates);
          setManifestMainFileId(custom.mainFileId ?? null);

          const nextActiveId = resolveInitialFile(candidates, custom.mainFileId ?? null);
          if (nextActiveId) {
            const meta = candidates.find((file) => file.id === nextActiveId);
            setActiveFileId(nextActiveId);
            setActiveFileName(meta?.name || "main.tex");
          }
        } catch (fallbackError) {
          console.error("[LatexPlugin] Failed to load files:", fallbackError);
          setError(
            fallbackError instanceof Error
              ? fallbackError.message
              : manifestError instanceof Error
                ? manifestError.message
                : t("load_files_failed")
          );
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [custom.mainFileId, initialFileId, latexFolderId, manifestRefreshNonce, projectId, t]);

  React.useEffect(() => {
    if (!activeFileId) return;
    const meta = files.find((file) => file.id === activeFileId);
    if (!meta) return;
    setActiveFileName(meta.name);
  }, [activeFileId, files]);

  React.useEffect(() => {
    citationIndexRef.current = citationIndex;
  }, [citationIndex]);

  React.useEffect(() => {
    labelIndexRef.current = labelIndex;
  }, [labelIndex]);

  React.useEffect(() => {
    return () => {
      latexCompletionDisposablesRef.current.forEach((disposable) => {
        try {
          disposable?.dispose?.();
        } catch {
          // ignore
        }
      });
      latexCompletionDisposablesRef.current = [];
    };
  }, []);

  React.useEffect(() => {
    if (!projectId || files.length === 0) {
      setCitationIndex([]);
      setLabelIndex([]);
      return;
    }
    let cancelled = false;
    const candidateFiles = files.filter(
      (file) => file.name.toLowerCase().endsWith(".bib") || file.name.toLowerCase().endsWith(".tex")
    );

    (async () => {
      try {
        const loaded = await Promise.all(
          candidateFiles.map(async (file) => {
            try {
              const content = await getFileContent(file.id);
              return { file, content };
            } catch {
              return { file, content: "" };
            }
          })
        );

        if (cancelled) return;

        const nextCitationIndex = loaded
          .filter((item) => item.file.name.toLowerCase().endsWith(".bib"))
          .flatMap((item) => parseBibEntries(item.content, latexFileDisplayPath(item.file) || item.file.name))
          .sort((a, b) => a.key.localeCompare(b.key));

        const nextLabelIndex = loaded
          .filter((item) => item.file.name.toLowerCase().endsWith(".tex"))
          .flatMap((item) => parseLatexLabels(item.content, latexFileDisplayPath(item.file) || item.file.name))
          .sort((a, b) => a.key.localeCompare(b.key));

        setCitationIndex(nextCitationIndex);
        setLabelIndex(nextLabelIndex);
      } catch {
        if (!cancelled) {
          setCitationIndex([]);
          setLabelIndex([]);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [files, projectId]);

  // Clean up bindings on file switch/unmount.
  React.useEffect(() => {
    return () => {
      try {
        bindingCleanupRef.current?.();
      } finally {
        bindingCleanupRef.current = null;
        if (boundEditorFileIdRef.current === activeFileId) {
          boundEditorFileIdRef.current = null;
        }
      }
    };
  }, [activeFileId]);

  // Sync LaTeX doc (Yjs) via space:* protocol (notebook-style).
  React.useEffect(() => {
    if (!projectId || !activeFileId) return;

    let cancelled = false;
    let cleanup: null | (() => void) = null;

    setSyncState("loading");
    saveStateRef.current = "idle";
    setSaveState("idle");
    lastSaveTriggerRef.current = "manual";
    setSaveTrigger("manual");
    failedSaveTextRef.current = null;
    savedRevisionRef.current = null;
    loadedRevisionRef.current = null;
    setExternalConflictState(null);
    setSaveError(null);
    setError(null);

    (async () => {
      const { Doc, applyUpdate, encodeStateVector, encodeStateAsUpdate, mergeUpdates } =
        await import("yjs");

      const ydoc = new Doc();
      const ytext = ydoc.getText("content");
      yDocRef.current = ydoc;
      yTextRef.current = ytext;

      if (!canUseRealtimeSync) {
        const remoteOrigin = `ds-external:${projectId || "project"}:${activeFileId}:${Date.now()}`;
        remoteOriginRef.current = remoteOrigin;
        const seedSnapshot = await getFileContentSnapshot(activeFileId);
        const seed = seedSnapshot.content;
        ydoc.transact(() => {
          const length = ytext.length || 0;
          if (length) ytext.delete(0, length);
          if (seed) ytext.insert(0, seed);
        }, remoteOrigin);

        const textNow = ytext.toString();
        setInitialText(textNow);
        lastSavedRef.current = textNow;
        loadedRevisionRef.current = seedSnapshot.revision ?? null;
        savedRevisionRef.current = seedSnapshot.revision ?? null;
        setEditorDirty(false);
        setSyncState("ready");

        cleanup = () => {
          try {
            bindingCleanupRef.current?.();
          } finally {
            bindingCleanupRef.current = null;
            if (yDocRef.current === ydoc) yDocRef.current = null;
            if (yTextRef.current === ytext) yTextRef.current = null;
          }
        };
        return;
      }

      const sync = new ProjectSyncClient(projectId, {
        authMode: socketAuthMode,
        docKind: "latex",
      });
      syncRef.current = sync;
      await sync.connect();

      const remoteOrigin = `ds-remote:${projectId}:${activeFileId}:${Date.now()}`;
      remoteOriginRef.current = remoteOrigin;

      const diff = await sync.loadDoc(activeFileId, encodeStateVector(ydoc));
      if (diff?.missing) {
        applyUpdate(ydoc, diff.missing, remoteOrigin);
      }

      if (forceSeedRef.current) {
        const seedSnapshot = await getFileContentSnapshot(activeFileId);
        const seed = seedSnapshot.content;
        ydoc.transact(() => {
          const length = ytext.length || 0;
          if (length) ytext.delete(0, length);
          if (seed) ytext.insert(0, seed);
        }, "ds-reset");
        loadedRevisionRef.current = seedSnapshot.revision ?? null;
        savedRevisionRef.current = seedSnapshot.revision ?? null;
        if (!effectiveReadOnly) {
          const resetUpdate = encodeStateAsUpdate(ydoc);
          await sync.pushDocUpdate(activeFileId, resetUpdate);
        }
        forceSeedRef.current = false;
      }

      if (!diff) {
        const seedSnapshot = await getFileContentSnapshot(activeFileId);
        const seed = seedSnapshot.content;
        ydoc.transact(() => {
          ytext.insert(0, seed);
        }, "ds-seed");
        loadedRevisionRef.current = seedSnapshot.revision ?? null;
        savedRevisionRef.current = seedSnapshot.revision ?? null;
        if (!effectiveReadOnly) {
          const initUpdate = encodeStateAsUpdate(ydoc);
          await sync.pushDocUpdate(activeFileId, initUpdate);
        }
      } else {
        try {
          const baselineSnapshot = await getFileContentSnapshot(activeFileId);
          loadedRevisionRef.current = baselineSnapshot.revision ?? null;
          savedRevisionRef.current = baselineSnapshot.revision ?? null;
        } catch {
          // Keep editing usable even when revision metadata cannot be refreshed.
        }
      }

      const unsubscribeRemote = sync.onDocUpdate((msg) => {
        if (msg.docId !== activeFileId) return;
        applyUpdate(ydoc, msg.update, remoteOrigin);
      });

      const unsubscribeReset = sync.onDocReset((msg) => {
        if (msg.docId !== activeFileId) return;
        const ts = Number(msg.timestamp || 0);
        if (ts && ts === lastResetTimestampRef.current) return;
        lastResetTimestampRef.current = ts || Date.now();
        if (cancelled) return;
        forceSeedRef.current = true;
        setResetNonce((v) => v + 1);
      });

      const scheduleFlush = () => {
        if (flushTimerRef.current != null) {
          window.clearTimeout(flushTimerRef.current);
        }
        flushTimerRef.current = window.setTimeout(async () => {
          flushTimerRef.current = null;
          const pending = pendingUpdatesRef.current;
          if (!pending.length) return;
          pendingUpdatesRef.current = [];
          try {
            const merged = pending.length === 1 ? pending[0] : mergeUpdates(pending);
            await sync.pushDocUpdate(activeFileId, merged);
          } catch (e) {
            console.error("[LatexPlugin] Failed to push update:", e);
          }
        }, 300);
      };

      const handleLocalUpdate = (update: Uint8Array, origin: any) => {
        if (origin === remoteOrigin) return;
        if (effectiveReadOnly) return;
        pendingUpdatesRef.current.push(update);
        scheduleFlush();
      };
      ydoc.on("update", handleLocalUpdate);

      // Awareness (best-effort). Only for writable sessions.
      let awareness: any = null;
      let unsubscribeAwarenessUpdate: null | (() => void) = null;
      let unsubscribeAwarenessCollect: null | (() => void) = null;
      let handleAwarenessChange: null | ((changes: any, origin: any) => void) = null;

      if (!effectiveReadOnly) {
        try {
          const { Awareness, encodeAwarenessUpdate, applyAwarenessUpdate } = await import(
            "y-protocols/awareness"
          );
          awareness = new Awareness(ydoc);
          awareness.setLocalStateField("user", {
            id: user?.id ?? null,
            name: user?.username ?? "User",
          });

          await sync.joinAwareness(activeFileId);

          const localAwarenessOrigin = `ds-awareness:${projectId}:${activeFileId}:${Date.now()}`;
          unsubscribeAwarenessUpdate = sync.onAwarenessUpdate(activeFileId, (update) => {
            applyAwarenessUpdate(awareness, update, localAwarenessOrigin);
          });
          unsubscribeAwarenessCollect = sync.onAwarenessCollect(activeFileId, () => {
            const update = encodeAwarenessUpdate(awareness, [awareness.clientID]);
            void sync.broadcastAwareness(activeFileId, update);
          });
          handleAwarenessChange = (changes: any, origin: any) => {
            if (origin === localAwarenessOrigin) return;
            const changedClients: number[] = [
              ...(changes?.added ?? []),
              ...(changes?.updated ?? []),
              ...(changes?.removed ?? []),
            ];
            const update = encodeAwarenessUpdate(awareness, changedClients);
            void sync.broadcastAwareness(activeFileId, update);
          };
          awareness.on("change", handleAwarenessChange);
          sync.requestAwarenesses(activeFileId);
        } catch (e) {
          console.warn("[LatexPlugin] Awareness init failed:", e);
        }
      }

      // Ready for editor binding.
      const textNow = ytext.toString();
      setInitialText(textNow);
      lastSavedRef.current = textNow;
      setEditorDirty(false);
      setSyncState("ready");

      cleanup = () => {
        try {
          try {
            bindingCleanupRef.current?.();
          } finally {
            bindingCleanupRef.current = null;
          }
          unsubscribeRemote?.();
          unsubscribeReset?.();
          try {
            ydoc.off("update", handleLocalUpdate);
          } catch {
            // ignore
          }
          if (flushTimerRef.current != null) {
            window.clearTimeout(flushTimerRef.current);
            flushTimerRef.current = null;
          }
          pendingUpdatesRef.current = [];
          if (unsubscribeAwarenessUpdate) unsubscribeAwarenessUpdate();
          if (unsubscribeAwarenessCollect) unsubscribeAwarenessCollect();
          if (awareness && handleAwarenessChange) {
            try {
              awareness.off("change", handleAwarenessChange);
            } catch {
              // ignore
            }
          }
          if (!effectiveReadOnly) {
            try {
              sync.leaveAwareness(activeFileId);
            } catch {
              // ignore
            }
          }
        } finally {
          try {
            sync.disconnect();
          } catch {
            // ignore
          }
          if (syncRef.current === sync) syncRef.current = null;
          if (yDocRef.current === ydoc) yDocRef.current = null;
          if (yTextRef.current === ytext) yTextRef.current = null;
        }
      };
    })()
      .catch((e) => {
        console.error("[LatexPlugin] Sync init failed:", e);
        if (cancelled) return;
        setSyncState("error");
        setError(e instanceof Error ? e.message : t("collaboration_failed"));
      });

    return () => {
      cancelled = true;
      cleanup?.();
    };
  }, [activeFileId, canUseRealtimeSync, effectiveReadOnly, projectId, resetNonce, setEditorDirty, setExternalConflictState, socketAuthMode, t, user?.id, user?.username]);

  const revealEditorRange = React.useCallback(
    (
      editor: any,
      range: {
        startLineNumber: number;
        startColumn: number;
        endLineNumber: number;
        endColumn: number;
      }
    ) => {
      const reveal = () => {
        try {
          editor.revealRangeInCenter?.(range, 0);
          return;
        } catch {
          // Fall back to position-based reveal below.
        }
        try {
          editor.revealPositionInCenter?.({
            lineNumber: range.startLineNumber,
            column: range.startColumn,
          });
        } catch {
          // ignore
        }
      };

      reveal();
      if (typeof window !== "undefined") {
        window.requestAnimationFrame(() => {
          reveal();
          window.requestAnimationFrame(reveal);
        });
        window.setTimeout(reveal, 80);
      }
    },
    []
  );

  const jumpEditorToLocation = React.useCallback((location: PendingJumpLocation) => {
    const editor = editorRef.current;
    if (!editor) return false;
    const model = editor.getModel?.();
    if (!model) return false;

    const maxLine = Math.max(1, Number(model.getLineCount?.() ?? 1));
    const preciseSelection = location.selection;
    if (
      preciseSelection &&
      typeof preciseSelection.start_line === "number" &&
      typeof preciseSelection.start_column === "number" &&
      typeof preciseSelection.end_line === "number" &&
      typeof preciseSelection.end_column === "number"
    ) {
      const startLine = Math.min(Math.max(1, Math.round(preciseSelection.start_line)), maxLine);
      const endLine = Math.min(Math.max(startLine, Math.round(preciseSelection.end_line)), maxLine);
      const startMaxColumn = Math.max(1, Number(model.getLineMaxColumn?.(startLine) ?? 1));
      const endMaxColumn = Math.max(1, Number(model.getLineMaxColumn?.(endLine) ?? 1));
      const startColumn = Math.min(Math.max(1, Math.round(preciseSelection.start_column)), startMaxColumn);
      const endColumn = Math.min(Math.max(1, Math.round(preciseSelection.end_column)), endMaxColumn);
      const selectionEndColumn = startLine === endLine ? Math.max(startColumn, endColumn) : endColumn;
      const editorSelection = {
        startLineNumber: startLine,
        startColumn,
        endLineNumber: endLine,
        endColumn: selectionEndColumn,
      };
      editor.setPosition?.({ lineNumber: startLine, column: startColumn });
      editor.setSelection?.(editorSelection);
      editor.focus?.();
      revealEditorRange(editor, editorSelection);
      return true;
    }

    const safeLine = Math.min(Math.max(1, Math.round(location.line || 1)), maxLine);
    const maxColumn = Math.max(1, Number(model.getLineMaxColumn?.(safeLine) ?? 1));
    const requestedColumn =
      typeof location.column === "number" && Number.isFinite(location.column)
        ? Math.round(location.column)
        : 1;
    const safeColumn = Math.min(Math.max(1, requestedColumn), maxColumn);

    let selection: {
      startLineNumber: number;
      startColumn: number;
      endLineNumber: number;
      endColumn: number;
    } | null = null;

    const rawWord = String(location.word || "").trim();
    const lineContent = String(model.getLineContent?.(safeLine) ?? "");
    if (rawWord && rawWord.length <= 120 && lineContent) {
      const lowerLine = lineContent.toLocaleLowerCase();
      const lowerWord = rawWord.toLocaleLowerCase();
      const matches: number[] = [];
      let index = lowerLine.indexOf(lowerWord);
      while (index >= 0) {
        matches.push(index);
        index = lowerLine.indexOf(lowerWord, index + Math.max(1, lowerWord.length));
      }
      if (matches.length > 0) {
        const nearest = matches.reduce((best, next) => {
          const bestDistance = Math.abs(best + 1 - safeColumn);
          const nextDistance = Math.abs(next + 1 - safeColumn);
          return nextDistance < bestDistance ? next : best;
        }, matches[0]);
        selection = {
          startLineNumber: safeLine,
          startColumn: nearest + 1,
          endLineNumber: safeLine,
          endColumn: Math.min(maxColumn, nearest + rawWord.length + 1),
        };
      }
    }

    if (!selection) {
      const wordAtPosition = model.getWordAtPosition?.({
        lineNumber: safeLine,
        column: safeColumn,
      });
      if (
        wordAtPosition &&
        typeof wordAtPosition.startColumn === "number" &&
        typeof wordAtPosition.endColumn === "number" &&
        wordAtPosition.endColumn > wordAtPosition.startColumn
      ) {
        selection = {
          startLineNumber: safeLine,
          startColumn: wordAtPosition.startColumn,
          endLineNumber: safeLine,
          endColumn: wordAtPosition.endColumn,
        };
      }
    }

    const targetColumn = selection?.startColumn ?? safeColumn;
    if (selection) {
      editor.setPosition?.({ lineNumber: selection.startLineNumber, column: selection.startColumn });
      editor.setSelection?.(selection);
      editor.focus?.();
      revealEditorRange(editor, selection);
    } else {
      const cursorSelection = {
        startLineNumber: safeLine,
        startColumn: safeColumn,
        endLineNumber: safeLine,
        endColumn: safeColumn,
      };
      editor.setSelection?.(cursorSelection);
      editor.setPosition?.({ lineNumber: safeLine, column: targetColumn });
      editor.focus?.();
      revealEditorRange(editor, cursorSelection);
    }
    return true;
  }, [revealEditorRange]);

  const flushPendingJump = React.useCallback(() => {
    const pending = pendingJumpRef.current;
    if (!pending) return;
    if (pending.fileId && pending.fileId !== activeFileId) return;
    if (!activeFileId || boundEditorFileIdRef.current !== activeFileId) return;
    if (jumpEditorToLocation(pending)) {
      pendingJumpRef.current = null;
    }
  }, [activeFileId, jumpEditorToLocation]);

  const insertAtCursor = React.useCallback((text: string) => {
    const editor = editorRef.current;
    if (!editor || effectiveReadOnly) return;
    const selection = editor.getSelection?.();
    if (!selection) return;
    editor.executeEdits?.("ds-latex-assist", [
      {
        range: selection,
        text,
        forceMoveMarkers: true,
      },
    ]);
    editor.focus?.();
    markDirty();
  }, [effectiveReadOnly, markDirty]);

  const insertCitation = React.useCallback(
    (entry: CitationEntry, command = "\\cite") => {
      const editor = editorRef.current;
      const model = editor?.getModel?.();
      const position = editor?.getPosition?.();
      if (!editor || !model || !position) {
        insertAtCursor(`${command}{${entry.key}}`);
        return;
      }
      const linePrefix = model.getValueInRange({
        startLineNumber: position.lineNumber,
        startColumn: 1,
        endLineNumber: position.lineNumber,
        endColumn: position.column,
      });
      const insideCitation = /\\(?:cite|citet|citep|autocite|parencite)\{[^}]*$/i.test(linePrefix);
      insertAtCursor(insideCitation ? entry.key : `${command}{${entry.key}}`);
      setReferencePanelOpen(false);
      setAssistQuery("");
    },
    [insertAtCursor]
  );

  const insertLabelReference = React.useCallback(
    (entry: LabelEntry, command = "\\ref") => {
      const editor = editorRef.current;
      const model = editor?.getModel?.();
      const position = editor?.getPosition?.();
      if (!editor || !model || !position) {
        insertAtCursor(`${command}{${entry.key}}`);
        return;
      }
      const linePrefix = model.getValueInRange({
        startLineNumber: position.lineNumber,
        startColumn: 1,
        endLineNumber: position.lineNumber,
        endColumn: position.column,
      });
      const insideRef = /\\(?:ref|eqref)\{[^}]*$/i.test(linePrefix);
      insertAtCursor(insideRef ? entry.key : `${command}{${entry.key}}`);
      setReferencePanelOpen(false);
      setAssistQuery("");
    },
    [insertAtCursor]
  );

  const insertBibSnippet = React.useCallback(
    (snippet: string) => {
      insertAtCursor(snippet);
      setBibPanelOpen(false);
      setAssistQuery("");
    },
    [insertAtCursor]
  );

  const filteredCitationIndex = React.useMemo(() => {
    const query = assistQuery.trim().toLowerCase();
    if (!query) return citationIndex.slice(0, 12);
    return citationIndex
      .filter((entry) =>
        [entry.key, entry.title, entry.author, entry.sourceFile].some((value) =>
          String(value || "").toLowerCase().includes(query)
        )
      )
      .slice(0, 12);
  }, [assistQuery, citationIndex]);

  const filteredLabelIndex = React.useMemo(() => {
    const query = assistQuery.trim().toLowerCase();
    if (!query) return labelIndex.slice(0, 10);
    return labelIndex
      .filter((entry) =>
        [entry.key, entry.sourceFile].some((value) =>
          String(value || "").toLowerCase().includes(query)
        )
      )
      .slice(0, 10);
  }, [assistQuery, labelIndex]);

  const showAssistPanel = referencePanelOpen || bibPanelOpen;

  const bindEditor = React.useCallback(
    (editor: any, monaco: any) => {
      editorRef.current = editor;
      const ytext = yTextRef.current;
      const ydoc = yDocRef.current;
      const remoteOrigin = remoteOriginRef.current;
      if (!ytext || !ydoc) return;

      const model = editor.getModel?.();
      if (!model) return;

      ensureMonacoLatexLanguages(monaco);
      monaco.editor.setModelLanguage(model, isBibFile ? BIBTEX_LANGUAGE_ID : LATEX_LANGUAGE_ID);

      latexCompletionDisposablesRef.current.forEach((disposable) => {
        try {
          disposable?.dispose?.();
        } catch {
          // ignore
        }
      });
      latexCompletionDisposablesRef.current = [
        monaco.languages.registerCompletionItemProvider(LATEX_LANGUAGE_ID, {
          triggerCharacters: ["\\", "{", "}"],
          provideCompletionItems: (targetModel: any, position: any) => {
            const linePrefix = targetModel.getValueInRange({
              startLineNumber: position.lineNumber,
              startColumn: 1,
              endLineNumber: position.lineNumber,
              endColumn: position.column,
            });
            const word = targetModel.getWordUntilPosition(position);
            const range = new monaco.Range(
              position.lineNumber,
              word.startColumn,
              position.lineNumber,
              word.endColumn
            );
            const beginMatch = linePrefix.match(/\\begin\{([A-Za-z*]*)\}?$/);
            if (beginMatch) {
              const replaceRange = new monaco.Range(
                position.lineNumber,
                position.column - beginMatch[0].length,
                position.lineNumber,
                position.column
              );
              const envPrefix = beginMatch[1].toLowerCase();
              return {
                suggestions: LATEX_ENVIRONMENT_SNIPPETS.filter((item) =>
                  item.label.toLowerCase().startsWith(`begin{${envPrefix}`)
                ).map((item) => ({
                  label: item.label,
                  kind: monaco.languages.CompletionItemKind.Snippet,
                  insertText: item.insertText,
                  insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
                  detail: item.detail,
                  documentation: item.documentation,
                  filterText: item.filterText,
                  range: replaceRange,
                })),
              };
            }

            if (/\\(?:cite|citet|citep|autocite|parencite)\{[^}]*$/i.test(linePrefix)) {
              return {
                suggestions: citationIndexRef.current.slice(0, 40).map((entry) => ({
                  label: entry.key,
                  kind: monaco.languages.CompletionItemKind.Reference,
                  insertText: entry.key,
                  detail: entry.title || entry.author || entry.sourceFile,
                  documentation: [entry.author, entry.title].filter(Boolean).join(" · "),
                  range,
                })),
              };
            }

            if (/\\(?:ref|eqref)\{[^}]*$/i.test(linePrefix)) {
              return {
                suggestions: labelIndexRef.current.slice(0, 40).map((entry) => ({
                  label: entry.key,
                  kind: monaco.languages.CompletionItemKind.Reference,
                  insertText: entry.key,
                  detail: entry.sourceFile,
                  range,
                })),
              };
            }

            const commandMatch = linePrefix.match(/\\[A-Za-z]*$/);
            const commandRange = commandMatch
              ? new monaco.Range(
                  position.lineNumber,
                  position.column - commandMatch[0].length,
                  position.lineNumber,
                  position.column
                )
              : range;

            return {
              suggestions: LATEX_COMMAND_SNIPPETS.map((item) => ({
                label: item.label,
                kind: monaco.languages.CompletionItemKind.Snippet,
                insertText: item.insertText,
                insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
                detail: item.detail,
                documentation: item.documentation,
                filterText: item.filterText,
                range: commandRange,
              })),
            };
          },
        }),
        monaco.languages.registerCompletionItemProvider(BIBTEX_LANGUAGE_ID, {
          triggerCharacters: ["@"],
          provideCompletionItems: (_targetModel: any, position: any) => {
            const range = new monaco.Range(
              position.lineNumber,
              position.column,
              position.lineNumber,
              position.column
            );
            return {
              suggestions: BIB_SNIPPETS.map((item) => ({
                label: item.id,
                kind: monaco.languages.CompletionItemKind.Snippet,
                insertText: item.snippet,
                insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
                documentation: t(item.labelKey),
                range,
              })),
            };
          },
        }),
      ];

      // Dispose any previous binding.
      bindingCleanupRef.current?.();

      // Ensure editor matches Yjs state.
      applyingRemoteRef.current = true;
      try {
        model.setValue(ytext.toString());
      } finally {
        applyingRemoteRef.current = false;
      }
      boundEditorFileIdRef.current = activeFileId;

      // Remote delta -> Monaco edits
      const applyDelta = (delta: any[]) => {
        if (!Array.isArray(delta) || delta.length === 0) return;
        const edits: any[] = [];
        let index = 0;
        for (const op of delta) {
          const retain = typeof op?.retain === "number" ? op.retain : 0;
          if (retain) index += retain;

          const ins = typeof op?.insert === "string" ? op.insert : null;
          if (ins != null) {
            const pos = model.getPositionAt(index);
            edits.push({
              range: new monaco.Range(pos.lineNumber, pos.column, pos.lineNumber, pos.column),
              text: ins,
              forceMoveMarkers: true,
            });
            index += ins.length;
          }

          const del = typeof op?.delete === "number" ? op.delete : 0;
          if (del) {
            const start = model.getPositionAt(index);
            const end = model.getPositionAt(index + del);
            edits.push({
              range: new monaco.Range(start.lineNumber, start.column, end.lineNumber, end.column),
              text: "",
              forceMoveMarkers: true,
            });
          }
        }

        if (!edits.length) return;
        applyingRemoteRef.current = true;
        try {
          model.applyEdits(edits);
        } finally {
          applyingRemoteRef.current = false;
        }
      };

      const yObserver = (event: any) => {
        const origin = event?.transaction?.origin;
        if (origin !== remoteOrigin) return;
        applyDelta(event.delta ?? []);
        if (!effectiveReadOnly) {
          markDirty();
        }
      };
      ytext.observe(yObserver);

      // Local Monaco edits -> Y.Text
      const disposable = model.onDidChangeContent((e: any) => {
        if (applyingRemoteRef.current) return;
        if (effectiveReadOnly) return;
        const changes = Array.isArray(e?.changes) ? e.changes : [];
        if (!changes.length) return;
        ydoc.transact(() => {
          // Apply descending offsets to keep rangeOffset stable.
          const sorted = [...changes].sort((a: any, b: any) => (b.rangeOffset ?? 0) - (a.rangeOffset ?? 0));
          for (const ch of sorted) {
            const offset = Number(ch.rangeOffset ?? 0);
            const length = Number(ch.rangeLength ?? 0);
            const text = String(ch.text ?? "");
            if (length) ytext.delete(offset, length);
            if (text) ytext.insert(offset, text);
          }
        }, "ds-monaco");
        markDirty();
      });

      bindingCleanupRef.current = () => {
        try {
          disposable?.dispose?.();
        } catch {
          // ignore
        }
        try {
          ytext.unobserve(yObserver);
        } catch {
          // ignore
        }
      };

      window.requestAnimationFrame(() => {
        flushPendingJump();
      });
    },
    [activeFileId, effectiveReadOnly, flushPendingJump, isBibFile, markDirty, t]
  );

  React.useEffect(() => {
    if (syncState !== "ready") return;
    flushPendingJump();
  }, [activeFileId, flushPendingJump, resetNonce, syncState]);

  const save = React.useCallback(async (
    trigger: LatexSaveTrigger = "manual",
    opts: { overwriteExternal?: boolean } = {}
  ) => {
    if (!activeFileId) return false;
    if (effectiveReadOnly) return false;
    const ytext = yTextRef.current;
    if (!ytext) return false;
    const externalConflictForSave = externalConflictRef.current;
    const overwriteExternal = opts.overwriteExternal === true;
    if (externalConflictForSave && !overwriteExternal) {
      failedSaveTextRef.current = String(ytext.toString?.() ?? "");
      saveStateRef.current = "error";
      setSaveError(t("external_change_save_blocked"));
      setSaveState("error");
      setEditorDirty(true);
      return false;
    }

    const activeInFlight = saveInFlightRef.current;
    if (activeInFlight && activeInFlight.fileId === activeFileId) {
      lastSaveTriggerRef.current = trigger;
      setSaveTrigger(trigger);
      return activeInFlight.promise;
    }

    const fileId = activeFileId;
    const textToSave = String(ytext.toString?.() ?? "");
    lastSaveTriggerRef.current = trigger;
    setSaveTrigger(trigger);

    let promise: Promise<boolean>;
    promise = (async () => {
      try {
        saveStateRef.current = "saving";
        failedSaveTextRef.current = null;
        setSaveError(null);
        setSaveState("saving");
        const expectedRevision = overwriteExternal
          ? externalConflictForSave?.remoteRevision ?? savedRevisionRef.current
          : savedRevisionRef.current;
        const res = await updateFileContent(fileId, textToSave, {
          revision: expectedRevision,
          force: overwriteExternal && !expectedRevision,
        });

        if (res?.updated_at) {
          updateFileMeta(fileId, {
            updatedAt: res.updated_at,
            size: typeof res.size === "number" ? res.size : undefined,
            mimeType: res.mime_type,
          });
        }

        if (activeFileIdRef.current !== fileId) {
          return true;
        }

        const currentYText = yTextRef.current;
        const currentText = currentYText ? String(currentYText.toString?.() ?? "") : "";
        const nextRevision = typeof res?.revision === "string" ? res.revision : null;
        savedRevisionRef.current = nextRevision;
        loadedRevisionRef.current = nextRevision;
        lastSavedRef.current = textToSave;
        setExternalConflictState(null);
        saveStateRef.current = "idle";
        setSaveState("idle");

        if (currentText === textToSave) {
          setEditorDirty(false);
          if (trigger === "auto") {
            maybeCreateTimedAutoVersion();
          }
          return true;
        }

        setEditorDirty(true);
        return false;
      } catch (e) {
        console.error("[LatexPlugin] Save failed:", e);
        if (activeFileIdRef.current === fileId) {
          const maybeConflict = e as Error & {
            conflict?: boolean;
            currentRevision?: string | null;
            updatedPayload?: {
              content?: string;
              revision?: string;
              updated_at?: string;
            };
          };
          if (maybeConflict.conflict && maybeConflict.updatedPayload) {
            setExternalConflictState({
              fileId,
              remoteContent: String(maybeConflict.updatedPayload.content ?? ""),
              remoteRevision: maybeConflict.updatedPayload.revision ?? maybeConflict.currentRevision ?? null,
              remoteUpdatedAt: maybeConflict.updatedPayload.updated_at ?? null,
              reason: "save_conflict",
            });
          }
          failedSaveTextRef.current = textToSave;
          saveStateRef.current = "error";
          setSaveError(
            maybeConflict.conflict
              ? t("external_change_save_blocked")
              : e instanceof Error
                ? e.message
                : t("save_request_failed")
          );
          setSaveState("error");
          setEditorDirty(true);
        }
        return false;
      } finally {
        if (saveInFlightRef.current?.promise === promise) {
          saveInFlightRef.current = null;
        }
      }
    })();

    saveInFlightRef.current = { fileId, promise };
    return promise;
  }, [activeFileId, effectiveReadOnly, maybeCreateTimedAutoVersion, setEditorDirty, setExternalConflictState, t, updateFileMeta]);

  const reloadExternalVersion = React.useCallback(() => {
    const conflict = externalConflictRef.current;
    if (!conflict) return;
    applyFileSnapshotToEditor(conflict.fileId, {
      content: conflict.remoteContent,
      revision: conflict.remoteRevision ?? null,
      updated_at: conflict.remoteUpdatedAt ?? null,
    });
  }, [applyFileSnapshotToEditor]);

  const overwriteExternalVersion = React.useCallback(() => {
    void save("manual", { overwriteExternal: true });
  }, [save]);

  const switchToLatexFile = React.useCallback(
    async (
      fileId: string | null | undefined,
      opts?: {
        line?: number | null;
        column?: number | null;
        word?: string | null;
        selection?: LatexSyncTexSelection | null;
            }
    ) => {
      if (!fileId) return false;
      const targetMeta = files.find((file) => file.id === fileId);
      if (!targetMeta) return false;

      if (!effectiveReadOnly && (isDirtyRef.current || saveStateRef.current === "saving")) {
        const saved = await save("lifecycle");
        if (!saved && isDirtyRef.current) return false;
      }

      setActiveFileName(targetMeta.name);
      setReferencePanelOpen(false);
      setBibPanelOpen(false);
      setAssistQuery("");

      if (opts?.line) {
        pendingJumpRef.current = {
          fileId,
          line: Math.max(1, Number(opts.line || 1)),
          column: opts.column ?? null,
          word: opts.word ?? null,
          selection: opts.selection ?? null,
        };
      }

      if (fileId !== activeFileIdRef.current) {
        boundEditorFileIdRef.current = null;
        setSyncState("loading");
        setInitialText("");
        setActiveFileId(fileId);
        return true;
      }

      flushPendingJump();
      return true;
    },
    [effectiveReadOnly, files, flushPendingJump, save]
  );

  const handleLatexOpenRequest = React.useCallback(
    (request: LatexOpenFileRequest) => {
      const targetFileId = resolveLatexOpenRequestFileId(files, request);
      if (!targetFileId) return false;
      void switchToLatexFile(targetFileId, {
        line: request.line ?? null,
        column: request.column ?? null,
        word: request.word ?? null,
      });
      return true;
    },
    [files, switchToLatexFile]
  );

  React.useEffect(() => {
    if (!projectId || !latexFolderId || files.length === 0) return;

    for (const request of consumeLatexOpenFileRequests(projectId, latexFolderId)) {
      handleLatexOpenRequest(request);
    }

    const listener = (event: Event) => {
      const detail = (event as CustomEvent<LatexOpenFileRequest>).detail;
      if (!detail) return;
      if (detail.latexFolderId !== latexFolderId) return;
      if (detail.projectId && detail.projectId !== projectId) return;
      handleLatexOpenRequest(detail);
    };

    window.addEventListener(LATEX_OPEN_FILE_EVENT, listener as EventListener);
    return () => {
      window.removeEventListener(LATEX_OPEN_FILE_EVENT, listener as EventListener);
    };
  }, [files.length, handleLatexOpenRequest, latexFolderId, projectId]);

  React.useEffect(() => {
    if (!activeFileId) return;
    if (effectiveReadOnly) return;
    if (syncState !== "ready") return;
    if (!isDirty) return;
    if (externalConflictRef.current) return;
    if (saveState === "saving") return;

    const currentText = getCurrentText();
    if (saveState === "error" && failedSaveTextRef.current === currentText) {
      return;
    }

    const timer = window.setTimeout(() => {
      if (!activeFileIdRef.current) return;
      if (!isDirtyRef.current) return;
      if (externalConflictRef.current) return;
      if (saveStateRef.current === "saving") return;
      const latestText = getCurrentText();
      if (saveStateRef.current === "error" && failedSaveTextRef.current === latestText) {
        return;
      }
      void save("auto");
    }, LATEX_AUTOSAVE_DELAY_MS);

    return () => {
      window.clearTimeout(timer);
    };
  }, [activeFileId, dirtyVersion, effectiveReadOnly, getCurrentText, isDirty, save, saveState, syncState]);

  React.useEffect(() => {
    if (!activeFileId) return;
    if (syncState !== "ready") return;
    const interval = window.setInterval(() => {
      void checkExternalSnapshot("poll");
    }, LATEX_EXTERNAL_CHECK_INTERVAL_MS);

    const handleFocus = () => {
      void checkExternalSnapshot("focus");
    };
    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        void checkExternalSnapshot("visibility");
      }
    };

    window.addEventListener("focus", handleFocus);
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      window.clearInterval(interval);
      window.removeEventListener("focus", handleFocus);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [activeFileId, checkExternalSnapshot, syncState]);

  React.useEffect(() => {
    if (!activeFileId) return;
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<{
        fileId?: string;
        filePath?: string;
        projectId?: string;
      }>).detail;
      if (!detail) return;
      if (detail.projectId && projectId && detail.projectId !== projectId) return;
      const activeMeta = files.find((file) => file.id === activeFileId) ?? null;
      const filePath = String(detail.filePath || "").replace(/^\/+/, "");
      const matchedFileId =
        (detail.fileId && files.some((file) => file.id === detail.fileId) ? detail.fileId : null) ||
        (filePath ? resolveLatexFileId(files, filePath) : null);
      const matches =
        detail.fileId === activeFileId ||
        matchedFileId === activeFileId ||
        (filePath && activeMeta && [activeMeta.path, activeMeta.relativePath].filter(Boolean).includes(filePath));
      if (matches) {
        void checkExternalSnapshot("diff");
      }
      if (matchedFileId && !viewReadOnly) {
        if (aiVersionTimerRef.current != null) {
          window.clearTimeout(aiVersionTimerRef.current);
        }
        aiVersionTimerRef.current = window.setTimeout(() => {
          aiVersionTimerRef.current = null;
          void createAutoLatexVersion(
            "ai",
            t("version_ai_label"),
            t("version_ai_description")
          );
        }, 1200);
      }
    };
    window.addEventListener("ds:file:diff", handler as EventListener);
    return () => {
      window.removeEventListener("ds:file:diff", handler as EventListener);
      if (aiVersionTimerRef.current != null) {
        window.clearTimeout(aiVersionTimerRef.current);
        aiVersionTimerRef.current = null;
      }
    };
  }, [activeFileId, checkExternalSnapshot, createAutoLatexVersion, files, projectId, t, viewReadOnly]);

  React.useEffect(() => {
    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      if (!isDirtyRef.current) return;
      event.preventDefault();
      event.returnValue = "";
      return "";
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState !== "hidden") return;
      if (!isDirtyRef.current) return;
      void save("lifecycle").then((saved) => {
        if (saved) return;
        if (!isDirtyRef.current) return;
        if (saveStateRef.current === "saving") return;
        void save("lifecycle");
      });
    };

    window.addEventListener("beforeunload", handleBeforeUnload);
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      window.removeEventListener("beforeunload", handleBeforeUnload);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [save]);

  const compile = React.useCallback(
    async (opts?: { auto?: boolean }) => {
      if (!projectId || !latexFolderId) return;
      if (viewReadOnly) return;
      if (buildStatusRef.current === "queued" || buildStatusRef.current === "running") return;
      if (!effectiveReadOnly && (isDirtyRef.current || saveStateRef.current === "saving")) {
        const saved = await save("compile");
        if (!saved) return;
      }

      try {
        setBuildError(null);
        setBuildErrors([]);
        setSynctexError(null);
        setSynctexReady(false);
        setLogText(null);
        buildStatusRef.current = "queued";
        setBuildStatus("queued");
        const res = await compileLatex(projectId, latexFolderId, {
          compiler,
          main_file_id: compileMainFileId,
          auto: Boolean(opts?.auto),
          stop_on_first_error: false,
        });
        setBuildId(res.build_id);
        setCompiler(normalizeCompiler(res.compiler));
        setSynctexReady(Boolean(res.synctex_ready));
        buildStatusRef.current = res.status ?? "queued";
        setBuildStatus(res.status ?? "queued");
        if (historyOpen) {
          void loadLatexVersionHistory();
        }
      } catch (e) {
        console.error("[LatexPlugin] Compile failed:", e);
        setBuildError(e instanceof Error ? e.message : t("compile_request_failed"));
        setSynctexReady(false);
        buildStatusRef.current = "error";
        setBuildStatus("error");
      }
    },
    [compiler, compileMainFileId, effectiveReadOnly, historyOpen, latexFolderId, loadLatexVersionHistory, projectId, save, t, viewReadOnly]
  );

  const triggerManualSave = React.useCallback(async () => {
    const targetFileId = activeFileIdRef.current;
    if (!targetFileId || effectiveReadOnly) return;

    let saved = await save("manual");
    // A manual save may have joined an in-flight autosave that captured older text.
    // Retry once so Ctrl/Cmd+S means "save the text I see now", then compile.
    if (!saved && isDirtyRef.current && activeFileIdRef.current === targetFileId) {
      saved = await save("manual");
    }

    if (!saved) return;
    if (isDirtyRef.current) return;
    if (activeFileIdRef.current !== targetFileId) return;
    if (!autoCompileOnSave) return;
    if (viewReadOnly) return;
    if (buildStatusRef.current === "queued" || buildStatusRef.current === "running") return;

    void compile({ auto: true });
  }, [autoCompileOnSave, compile, effectiveReadOnly, save, viewReadOnly]);

  React.useEffect(() => {
    if (!activeFileId || effectiveReadOnly) return;
    const handler = (event: KeyboardEvent) => {
      const isSave = (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s";
      if (!isSave) return;
      event.preventDefault();
      void triggerManualSave();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [activeFileId, effectiveReadOnly, triggerManualSave]);

  React.useEffect(() => {
    if (!projectId || !latexFolderId) return;
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<{
        projectId?: string;
        folderId?: string;
        buildId?: string | null;
        status?: LatexBuildStatus;
        errorMessage?: string | null;
      }>).detail;
      if (!detail) return;
      if (detail.projectId !== projectId || detail.folderId !== latexFolderId) return;
      if (detail.buildId) {
        setBuildId(detail.buildId);
      }
      setBuildStatus(detail.status ?? "queued");
      setBuildError(detail.errorMessage ?? null);
      setBuildErrors([]);
      setSynctexReady(false);
      setSynctexError(null);
      setLogText(null);
    };

    window.addEventListener("ds:latex-build", handler as EventListener);
    return () => {
      window.removeEventListener("ds:latex-build", handler as EventListener);
    };
  }, [latexFolderId, projectId]);

  // Load the latest build even in read-only tabs where compile is unavailable.
  React.useEffect(() => {
    if (!projectId || !latexFolderId) return;
    if (buildId) return;
    let cancelled = false;
    (async () => {
      try {
        const builds = await listLatexBuilds(projectId, latexFolderId, 1);
        if (cancelled) return;
        const latest = builds?.[0];
        if (latest?.build_id) {
          setBuildId(latest.build_id);
          setCompiler(normalizeCompiler(latest.compiler));
          setBuildStatus(latest.status ?? "idle");
          setBuildError(latest.error_message ?? null);
          setBuildErrors(normalizeBuildErrors(latest.errors, latest.log_items));
          setSynctexReady(Boolean(latest.synctex_ready));
        }
      } catch {
        // ignore
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [buildId, latexFolderId, projectId]);

  // Poll build status and refresh preview.
  React.useEffect(() => {
    if (!projectId || !latexFolderId || !buildId) return;
    let cancelled = false;
    let timer: number | null = null;

    const poll = async () => {
      try {
        const res = await getLatexBuild(projectId, latexFolderId, buildId);
        if (cancelled) return;
        setCompiler(normalizeCompiler(res.compiler));
        setBuildStatus(res.status);
        setBuildError(res.error_message ?? null);
        setBuildErrors(normalizeBuildErrors(res.errors, res.log_items));
        setSynctexReady(Boolean(res.synctex_ready));

        if (res.status === "success" && res.pdf_ready) {
          if (lastLoadedPdfBuildIdRef.current !== buildId) {
            try {
              const blob = await getLatexBuildPdfBlob(projectId, latexFolderId, buildId);
              if (cancelled) return;
              const nextUrl = URL.createObjectURL(blob);
              if (pdfUrlRef.current) {
                try {
                  URL.revokeObjectURL(pdfUrlRef.current);
                } catch {
                  // ignore
                }
              }
              pdfUrlRef.current = nextUrl;
              setPdfObjectUrl(nextUrl);
              lastLoadedPdfBuildIdRef.current = buildId;
            } catch (e) {
              console.warn("[LatexPlugin] Failed to fetch PDF:", e);
            }
          }
        }

        if (res.status === "error" && res.log_ready && !logText) {
          try {
            const txt = await getLatexBuildLogText(projectId, latexFolderId, buildId);
            if (cancelled) return;
            setLogText(txt);
          } catch (e) {
            console.warn("[LatexPlugin] Failed to fetch log:", e);
          }
        }

        if (res.status === "queued" || res.status === "running") {
          timer = window.setTimeout(poll, 1000);
        }
      } catch (e) {
        if (cancelled) return;
        timer = window.setTimeout(poll, 1500);
      }
    };

    poll();
    return () => {
      cancelled = true;
      if (timer != null) window.clearTimeout(timer);
    };
  }, [buildId, latexFolderId, logText, projectId]);

  // Cleanup blob URL.
  React.useEffect(() => {
    return () => {
      if (pdfUrlRef.current) {
        try {
          URL.revokeObjectURL(pdfUrlRef.current);
        } catch {
          // ignore
        }
        pdfUrlRef.current = null;
      }
    };
  }, []);

  React.useEffect(() => {
    setDirty(isDirty);
  }, [isDirty, setDirty]);

  React.useEffect(() => {
    if (typeof window === "undefined") return;
    const media = window.matchMedia("(min-width: 1024px)");
    const legacyMedia = media as MediaQueryList & {
      addListener?: (listener: () => void) => void;
      removeListener?: (listener: () => void) => void;
    };
    const handleChange = () => setIsWideLayout(media.matches);
    handleChange();
    if (typeof media.addEventListener === "function") {
      media.addEventListener("change", handleChange);
      return () => media.removeEventListener("change", handleChange);
    }
    legacyMedia.addListener?.(handleChange);
    return () => legacyMedia.removeListener?.(handleChange);
  }, []);

  React.useEffect(() => {
    const el = pdfPaneRef.current;
    if (!el) return;
    let rafId: number | null = null;
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      if (rafId != null) window.cancelAnimationFrame(rafId);
      rafId = window.requestAnimationFrame(() => {
        setPdfPaneWidth(entry.contentRect.width);
      });
    });
    observer.observe(el);
    return () => {
      if (rafId != null) window.cancelAnimationFrame(rafId);
      observer.disconnect();
    };
  }, []);

  const pdfFileName = React.useMemo(() => {
    const base = activeFileName ? activeFileName.replace(/\.tex$/i, "") : "document";
    return `${base}.pdf`;
  }, [activeFileName]);
  const warningItems = React.useMemo(
    () => buildErrors.filter((err) => err.severity === "warning"),
    [buildErrors]
  );
  const compilerLabel = React.useMemo(() => {
    return t(`compiler_${compiler}`);
  }, [compiler, t]);
  const statusBadge = React.useMemo(() => {
    if (effectiveReadOnly) {
      return {
        label: t("status_read_only"),
        className:
          "border-black/10 bg-white/60 text-muted-foreground dark:bg-white/[0.04] dark:border-white/10",
      };
    }
    if (buildStatus === "queued" || buildStatus === "running") {
      return {
        label: t("status_compiling"),
        className:
          "border-[#8FA3B8]/30 bg-[#8FA3B8]/10 text-[#52667a] dark:bg-[#8FA3B8]/12 dark:text-[#c8d4df]",
      };
    }
    if (externalConflict) {
      return {
        label: t("status_external_changed"),
        className:
          "border-amber-400/40 bg-amber-50/90 text-amber-700 dark:bg-amber-500/10 dark:text-amber-200",
      };
    }
    if (saveState === "saving") {
      const autosaveLike = saveTrigger === "auto" || saveTrigger === "lifecycle";
      return {
        label: autosaveLike ? t("status_autosaving") : t("status_saving"),
        className:
          "border-[#A6B0B6]/30 bg-[#A6B0B6]/12 text-[#5c666b] dark:bg-[#A6B0B6]/12 dark:text-[#d8dde0]",
      };
    }
    if (saveError || saveState === "error") {
      return {
        label: t("status_save_failed"),
        className:
          "border-red-400/30 bg-red-50/80 text-red-600 dark:bg-red-500/10 dark:text-red-200",
      };
    }
    if (isDirty) {
      return {
        label: t("status_unsaved"),
        className:
          "border-[#B7A59A]/30 bg-[#B7A59A]/12 text-[#7e695d] dark:bg-[#B7A59A]/12 dark:text-[#eadfd8]",
      };
    }
    if (buildStatus === "error") {
      return {
        label: t("status_compile_failed"),
        className:
          "border-red-400/30 bg-red-50/80 text-red-600 dark:bg-red-500/10 dark:text-red-200",
      };
    }
    return {
      label: t("status_saved"),
      className:
        "border-[#9AA79A]/30 bg-[#9AA79A]/12 text-[#5f6b5f] dark:bg-[#9AA79A]/12 dark:text-[#dbe4db]",
    };
  }, [buildStatus, effectiveReadOnly, externalConflict, isDirty, saveError, saveState, saveTrigger, t]);

  const buildFocusedIssue = React.useCallback(
    (issue: LatexBuildError) => {
      const targetFileId =
        resolveLatexFileId(files, issue.path) ??
        activeFileId ??
        files.find((file) => file.name.toLowerCase() === "main.tex")?.id ??
        files[0]?.id ??
        null;
      const targetMeta = targetFileId ? files.find((file) => file.id === targetFileId) ?? null : null;
      const resourceName = targetMeta?.name || issue.path || activeFileName || "main.tex";
      const normalizedPath = targetMeta?.path
        ? toFilesResourcePath(targetMeta.path)
        : issue.path
          ? toFilesResourcePath(issue.path)
          : "";
      const severity: "error" | "warning" =
        issue.severity === "warning" ? "warning" : "error";
      return {
        kind: "latex_error" as const,
        tabId,
        fileId: targetFileId || undefined,
        resourceId: targetFileId || undefined,
        resourcePath:
          normalizedPath && normalizedPath !== "/FILES" ? normalizedPath : undefined,
        resourceName,
        line: typeof issue.line === "number" ? Math.max(1, Number(issue.line || 1)) : undefined,
        message: issue.message,
        severity,
        excerpt:
          issue.path || issue.line
            ? `${issue.path || resourceName}${issue.line ? `:${issue.line}` : ""}`
            : undefined,
        createdAt: new Date().toISOString(),
      };
    },
    [activeFileId, activeFileName, files, tabId]
  );

  const focusBuildIssue = React.useCallback(
    (issue: LatexBuildError) => {
      const focusedIssue = buildFocusedIssue(issue);
      setWorkspaceActiveIssue(tabId, focusedIssue);
      return focusedIssue;
    },
    [buildFocusedIssue, setWorkspaceActiveIssue, tabId]
  );

  React.useEffect(() => {
    if (buildStatus === "success") {
      setWorkspaceActiveIssue(tabId, null);
      return;
    }
    if (buildErrors.length === 0) {
      if (buildStatus === "error") {
        setWorkspaceActiveIssue(tabId, null);
      }
      return;
    }

    const preferredIssue =
      buildErrors.find((issue) => issue.severity !== "warning") ?? buildErrors[0] ?? null;
    if (!preferredIssue) return;

    const currentFocusedIssue = useWorkspaceSurfaceStore.getState().activeIssueByTabId[tabId];
    const matchingIssue =
      currentFocusedIssue?.kind === "latex_error"
        ? buildErrors.find(
            (issue) =>
              getLatexIssueIdentity(buildFocusedIssue(issue)) ===
              getLatexIssueIdentity(currentFocusedIssue)
          ) ?? null
        : null;
    const nextFocusedIssue = buildFocusedIssue(matchingIssue ?? preferredIssue);

    if (
      currentFocusedIssue &&
      getLatexIssueIdentity(currentFocusedIssue) === getLatexIssueIdentity(nextFocusedIssue)
    ) {
      return;
    }

    setWorkspaceActiveIssue(tabId, nextFocusedIssue);
  }, [buildErrors, buildFocusedIssue, buildStatus, setWorkspaceActiveIssue, tabId]);

  const handleBuildIssueClick = React.useCallback(
    (issue: LatexBuildError) => {
      const focusedIssue = focusBuildIssue(issue);
      const targetFileId =
        focusedIssue?.fileId ??
        resolveLatexFileId(files, issue.path) ??
        activeFileId ??
        files.find((file) => file.name.toLowerCase() === "main.tex")?.id ??
        files[0]?.id ??
        null;
      if (!targetFileId) return;

      void switchToLatexFile(targetFileId, {
        line: Math.max(1, Number(issue.line || 1)),
      });
    },
    [activeFileId, files, focusBuildIssue, switchToLatexFile]
  );

  const handleAskDeepScientistForIssue = React.useCallback(
    (issue: LatexBuildError) => {
      const focusedIssue = focusBuildIssue(issue);
      const severityLabel =
        issue.severity === "warning" ? t("warning_badge") : t("error_badge");
      const issueLocation =
        focusedIssue?.line && focusedIssue.resourceName
          ? `${focusedIssue.resourceName}:${focusedIssue.line}`
          : focusedIssue?.resourceName || issue.path || activeFileName || "main.tex";
      const fileLabel =
        focusedIssue?.resourcePath ||
        focusedIssue?.resourceName ||
        issue.path ||
        activeFileName ||
        "main.tex";
      const lineLabel =
        typeof focusedIssue?.line === "number" && Number.isFinite(focusedIssue.line)
          ? String(Math.max(1, focusedIssue.line))
          : t("issue_unknown_line");
      const prompt = t("issue_action_prompt", {
        severity: severityLabel,
        branch: currentBranch || t("issue_unknown_branch"),
        file: fileLabel,
        line: lineLabel,
        location: issueLocation,
        message: issue.message,
      });
      window.dispatchEvent(
        new CustomEvent("ds:copilot:prefill", {
          detail: {
            text: prompt,
            focus: true,
          },
        })
      );
    },
    [activeFileName, currentBranch, focusBuildIssue, t]
  );

  const renderBuildIssueRow = React.useCallback(
    (issue: LatexBuildError, idx: number, scope: "error" | "warning") => {
      const canJump = Boolean(issue.path || issue.line) && Boolean(activeFileId || files.length);
      const key = `${issue.path ?? scope}-${issue.line ?? "0"}-${idx}`;
      const issueContent = (
        <>
          <span
            className={cn(
              "px-1.5 py-0.5 rounded-full text-[10px] uppercase border",
              issue.severity === "warning"
                ? "text-amber-700 border-amber-400/40 bg-amber-50/70 dark:bg-amber-500/10"
                : "text-red-600 border-red-400/40 bg-red-50/70 dark:bg-red-500/10"
            )}
          >
            {issue.severity === "warning" ? t("warning_badge") : t("error_badge")}
          </span>
          <span className="text-muted-foreground font-mono">
            {issue.path || "main.tex"}
            {issue.line ? `:${issue.line}` : ""}
          </span>
          <span className="text-muted-foreground break-words">{issue.message}</span>
          {canJump ? (
            <span className="ml-auto shrink-0 text-[10px] text-muted-foreground/80">
              {t("issue_hint_clickable")}
            </span>
          ) : null}
        </>
      );

      return (
        <div key={key} className="flex items-start gap-2">
          {canJump ? (
            <button
              type="button"
              onClick={() => handleBuildIssueClick(issue)}
              className="min-w-0 flex flex-1 items-start gap-2 rounded-lg px-2 py-1.5 text-left hover:bg-black/5 dark:hover:bg-white/[0.04]"
              title={
                issue.line
                  ? t("issue_jump_to_line", { line: issue.line })
                  : t("issue_jump_to_file", { file: issue.path || "main.tex" })
              }
            >
              {issueContent}
            </button>
          ) : (
            <div className="min-w-0 flex flex-1 items-start gap-2 px-2 py-1.5">{issueContent}</div>
          )}
          <div className="flex shrink-0 items-center gap-1 pt-1">
            <button
              type="button"
              onClick={() => handleAskDeepScientistForIssue(issue)}
              className="rounded-md border border-black/10 dark:border-white/10 bg-white/70 dark:bg-white/[0.05] px-2 py-1 text-[11px] font-medium text-muted-foreground hover:bg-black/5 dark:hover:bg-white/[0.08]"
              title={t("issue_action_ask_deepscientist")}
            >
              {t("issue_action_ask_deepscientist")}
            </button>
          </div>
        </div>
      );
    },
    [
      activeFileId,
      files,
      handleAskDeepScientistForIssue,
      handleBuildIssueClick,
      t,
    ]
  );

  const zoomOutDisabled = !pdfObjectUrl || zoomScale <= ZOOM_LEVELS[0];
  const zoomInDisabled = !pdfObjectUrl || zoomScale >= ZOOM_LEVELS[ZOOM_LEVELS.length - 1];

  const handleZoomOut = () => {
    const currentIndex = ZOOM_LEVELS.findIndex((z) => z >= zoomScale);
    const safeIndex = currentIndex === -1 ? ZOOM_LEVELS.length - 1 : currentIndex;
    if (safeIndex <= 0) return;
    setZoomScale(ZOOM_LEVELS[safeIndex - 1]);
  };

  const handleZoomIn = () => {
    const currentIndex = ZOOM_LEVELS.findIndex((z) => z >= zoomScale);
    const safeIndex = currentIndex === -1 ? ZOOM_LEVELS.length - 1 : currentIndex;
    if (safeIndex >= ZOOM_LEVELS.length - 1) return;
    setZoomScale(ZOOM_LEVELS[safeIndex + 1]);
  };

  const fitScale = React.useMemo(() => {
    if (!pdfPaneWidth || !pdfPageWidth) return 1;
    const paddedWidth = Math.max(pdfPaneWidth - 32, 120);
    return Math.max(paddedWidth / pdfPageWidth, 0.2);
  }, [pdfPaneWidth, pdfPageWidth]);

  const renderScale = fitScale * zoomScale;
  const handlePageWidth = React.useCallback((width: number) => {
    setPdfPageWidth(width || PAGE_DIMENSIONS.A4_WIDTH);
  }, []);

  const handlePdfPointDoubleClick = React.useCallback(
    async (point: PdfSourcePoint) => {
      if (!projectId || !latexFolderId || !buildId) return;
      setSynctexError(null);

      if (!synctexReady) {
        setSynctexError(t("synctex_unavailable_hint"));
        return;
      }

      setSynctexBusy(true);
      try {
        const result = await syncTexEditLatexBuild(projectId, latexFolderId, buildId, {
          page: point.page,
          x: point.x,
          y: point.y,
          pdf_word: point.word ?? null,
          pdf_context_words: point.contextWords ?? null,
          pdf_context_index: point.contextIndex ?? null,
          pdf_word_bbox: point.wordBBox ?? null,
          pdf_word_center: point.wordCenter ?? null,
        });
        if (!result.ok) {
          setSynctexError(result.message || t("synctex_not_found"));
          return;
        }
        const targetFileId =
          resolveLatexFileId(files, result.file_path) ??
          (result.file_id && files.some((file) => file.id === result.file_id) ? result.file_id : null);
        if (!targetFileId) {
          setSynctexError(t("synctex_source_not_loaded"));
          return;
        }
        const switched = await switchToLatexFile(targetFileId, {
          line: result.line ?? 1,
          column: result.column ?? null,
          word: result.pdf_word ?? point.word ?? null,
          selection: result.selection ?? null,
        });
        if (!switched) {
          setSynctexError(t("synctex_switch_failed"));
        }
      } catch (e) {
        console.error("[LatexPlugin] SyncTeX reverse sync failed:", e);
        setSynctexError(e instanceof Error ? e.message : t("synctex_failed"));
      } finally {
        setSynctexBusy(false);
      }
    },
    [buildId, files, latexFolderId, projectId, switchToLatexFile, synctexReady, t]
  );

  const handleResizeStart = React.useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (!isWideLayout || !splitContainerRef.current) return;
      if (event.button !== 0) return;
      event.preventDefault();
      const container = splitContainerRef.current;
      const rect = container.getBoundingClientRect();
      const startX = event.clientX;
      const startLeft = rect.width * splitRatio;
      const minLeft = 360;
      const minRight = 320;
      const maxLeft = Math.max(rect.width - minRight, minLeft);
      const prevCursor = document.body.style.cursor;
      const prevSelect = document.body.style.userSelect;
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
      setIsResizing(true);
      let rafId: number | null = null;

      const onMove = (moveEvent: PointerEvent) => {
        const nextLeft = startLeft + (moveEvent.clientX - startX);
        const clamped = Math.min(Math.max(nextLeft, minLeft), maxLeft);
        const nextRatio = clamped / rect.width;
        if (rafId != null) window.cancelAnimationFrame(rafId);
        rafId = window.requestAnimationFrame(() => {
          setSplitRatio(nextRatio);
        });
      };

      const onUp = () => {
        if (rafId != null) window.cancelAnimationFrame(rafId);
        setIsResizing(false);
        document.body.style.cursor = prevCursor;
        document.body.style.userSelect = prevSelect;
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onUp);
      };

      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
    },
    [isWideLayout, splitRatio]
  );

  return (
    <div className="h-full flex flex-col bg-white/70 dark:bg-black/30">
      <div
        ref={splitContainerRef}
        className="flex-1 min-h-0 flex flex-col lg:flex-row"
      >
        <div
          className={cn(
            "min-h-0 flex flex-col min-w-0",
            isWideLayout ? "lg:border-r-0" : "border-b border-black/5 dark:border-white/10",
            isResizing ? "transition-none" : "transition-[flex-basis] duration-200 ease-out"
          )}
          style={
            isWideLayout
              ? {
                  flexBasis: `${splitRatio * 100}%`,
                  flexGrow: 0,
                  flexShrink: 0,
                }
              : undefined
          }
        >
          <div className="flex h-10 shrink-0 flex-nowrap items-center gap-1 overflow-x-auto border-b border-black/5 px-2 py-1 dark:border-white/10">
            <div className="flex min-w-0 shrink items-center gap-1">
              <FileText className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
              <select
                className={cn(
                  "h-7 rounded-md px-2 text-xs bg-white/70 border border-black/10",
                  "dark:bg-white/[0.04] dark:border-white/10",
                  "min-w-[140px] max-w-[220px] truncate",
                  effectiveReadOnly && "opacity-70"
                )}
	                value={activeFileId ?? ""}
	                onChange={(e) => {
	                  void switchToLatexFile(e.target.value || null);
	                }}
	                disabled={files.length === 0}
	                aria-label={t("file_label")}
	                title={latexFileDisplayPath(files.find((file) => file.id === activeFileId)) || activeFileName}
	              >
	                {files.map((f) => (
	                  <option key={f.id} value={f.id}>
	                    {latexFileDisplayPath(f)}
	                  </option>
	                ))}
	              </select>
	            </div>

            <div className="flex shrink-0 items-center gap-1">
              <span className="sr-only">{t("compiler_label")}</span>
              <select
                className={cn(
                  "h-7 rounded-md px-2 text-xs bg-white/70 border border-black/10",
                  "dark:bg-white/[0.04] dark:border-white/10",
                  "min-w-[104px]",
                  buildStatus === "queued" || buildStatus === "running" ? "opacity-70" : ""
                )}
                value={compiler}
                onChange={(event) => setCompiler(normalizeCompiler(event.target.value))}
                disabled={buildStatus === "queued" || buildStatus === "running"}
                aria-label={t("compiler_label")}
                title={compilerLabel}
              >
                {LATEX_COMPILER_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {t(`compiler_${option}`)}
                  </option>
                ))}
              </select>
            </div>

            <label
              className={cn(
                "h-7 shrink-0 whitespace-nowrap px-2 rounded-md text-xs border inline-flex items-center gap-1",
                "bg-white/70 border-black/10 text-muted-foreground",
                "dark:bg-white/[0.04] dark:border-white/10",
                viewReadOnly && "opacity-70"
              )}
              title={t("auto_compile_on_save_hint")}
            >
              <input
                type="checkbox"
                className="h-3.5 w-3.5 accent-[#8FA3B8]"
                checked={autoCompileOnSave}
                disabled={viewReadOnly}
                onChange={(event) => updateAutoCompileOnSave(event.target.checked)}
              />
              <span className="hidden xl:inline">{t("auto_compile_on_save")}</span>
            </label>

            {!isBibFile ? (
              <button
                type="button"
                onClick={() => {
                  setReferencePanelOpen((current) => {
                    const next = !current;
                    if (next) setBibPanelOpen(false);
                    if (!next) setAssistQuery("");
                    return next;
                  });
                }}
                className={cn(
                  "h-7 shrink-0 whitespace-nowrap px-2 rounded-md text-xs border inline-flex items-center gap-1",
                  "bg-white/70 border-black/10 hover:bg-white/90",
                  "dark:bg-white/[0.04] dark:border-white/10 dark:hover:bg-white/[0.08]",
                  referencePanelOpen && "border-[#8FA3B8]/28 bg-[#8FA3B8]/12 text-[#405267]"
                )}
                aria-label={t("assist_references")}
                title={t("assist_references")}
              >
                <Link2 className="h-3.5 w-3.5" />
                <span className="hidden xl:inline">{t("assist_references")}</span>
              </button>
            ) : null}

            {isBibFile ? (
              <button
                type="button"
                onClick={() => {
                  setBibPanelOpen((current) => {
                    const next = !current;
                    if (next) setReferencePanelOpen(false);
                    if (!next) setAssistQuery("");
                    return next;
                  });
                }}
                className={cn(
                  "h-7 shrink-0 whitespace-nowrap px-2 rounded-md text-xs border inline-flex items-center gap-1",
                  "bg-white/70 border-black/10 hover:bg-white/90",
                  "dark:bg-white/[0.04] dark:border-white/10 dark:hover:bg-white/[0.08]",
                  bibPanelOpen && "border-[#A99EBE]/28 bg-[#A99EBE]/12 text-[#564f6a]"
                )}
                aria-label={t("assist_bibtex")}
                title={t("assist_bibtex")}
              >
                <AtSign className="h-3.5 w-3.5" />
                <span className="hidden xl:inline">{t("assist_bibtex")}</span>
              </button>
            ) : null}

            <div className="ml-auto flex shrink-0 items-center gap-1">
              <button
                type="button"
                onClick={() => setHistoryOpen((value) => !value)}
                className={cn(
                  "h-7 shrink-0 whitespace-nowrap px-2 rounded-md text-xs border inline-flex items-center gap-1",
                  "bg-white/70 border-black/10 hover:bg-white/90",
                  "dark:bg-white/[0.04] dark:border-white/10 dark:hover:bg-white/[0.08]",
                  historyOpen && "border-[#8FA3B8]/28 bg-[#8FA3B8]/12 text-[#405267]"
                )}
                title={t("version_history")}
              >
                <History className="h-3.5 w-3.5" />
                <span className="hidden xl:inline">{t("version_history")}</span>
              </button>

              <span
                className={cn(
                  "inline-flex h-6 items-center whitespace-nowrap text-[11px] px-1.5 rounded-full border",
                  statusBadge.className
                )}
              >
                {statusBadge.label}
              </span>

              <button
                type="button"
                onClick={() => void triggerManualSave()}
                disabled={effectiveReadOnly || saveState === "saving"}
                className={cn(
                  "h-7 whitespace-nowrap px-2 rounded-md text-xs font-medium border",
                  "bg-white/70 border-black/10 hover:bg-white/90",
                  "dark:bg-white/[0.04] dark:border-white/10 dark:hover:bg-white/[0.08]",
                  "disabled:opacity-50 disabled:cursor-not-allowed",
                  isDirty && !effectiveReadOnly && "border-black/20"
                )}
              >
                {saveState === "saving" ? (
                  <span className="flex items-center gap-1">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    {t("button_saving")}
                  </span>
                ) : (
                  <span className="flex items-center gap-1">
                    <Save className="h-3.5 w-3.5" />
                    {t("button_save")}
                  </span>
                )}
              </button>

              <button
                type="button"
                onClick={() => void compile({ auto: false })}
                disabled={
                  viewReadOnly ||
                  saveState === "saving" ||
                  buildStatus === "queued" ||
                  buildStatus === "running"
                }
                className={cn(
                  "h-7 whitespace-nowrap px-2 rounded-md text-xs font-medium border",
                  "bg-[#8FA3B8]/14 border-[#8FA3B8]/28 text-[#405267] hover:bg-[#8FA3B8]/20",
                  "dark:bg-[#8FA3B8]/14 dark:border-[#8FA3B8]/22 dark:text-[#dbe6ef] dark:hover:bg-[#8FA3B8]/20",
                  "disabled:opacity-50 disabled:cursor-not-allowed"
                )}
                title={
                  viewReadOnly
                    ? t("compile_disabled_read_only")
                    : isDirty && !effectiveReadOnly
                      ? t("button_save_and_compile")
                      : t("button_compile")
                }
              >
                {buildStatus === "queued" || buildStatus === "running" ? (
                  <span className="flex items-center gap-1">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    {t("button_compiling")}
                  </span>
                ) : (
                  <span className="flex items-center gap-1">
                    <Play className="h-3.5 w-3.5" />
                    {isDirty && !effectiveReadOnly ? t("button_save_and_compile") : t("button_compile")}
                  </span>
                )}
	              </button>
	            </div>
		          </div>

            {historyOpen ? (
              <div className="border-b border-black/5 bg-[#f8fafc]/80 px-3 py-3 text-sm dark:border-white/10 dark:bg-white/[0.025]">
                <div className="flex flex-col gap-3 xl:flex-row">
                  <div className="min-w-[260px] xl:w-[320px] xl:shrink-0">
                    <div className="flex items-center justify-between gap-2">
                      <div>
                        <div className="text-sm font-medium text-foreground">{t("version_history_title")}</div>
                        <div className="text-xs text-muted-foreground">
                          {latexVersionsHead ? `${t("version_current_head")}: ${latexVersionsHead.slice(0, 8)}` : t("version_history_hint")}
                        </div>
                      </div>
                      <button
                        type="button"
                        className="inline-flex h-7 items-center gap-1 rounded-md border border-black/10 bg-white/75 px-2 text-xs hover:bg-white dark:border-white/10 dark:bg-white/[0.05]"
                        onClick={() => void loadLatexVersionHistory()}
                        disabled={historyLoading}
                      >
                        {historyLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
                        {t("version_refresh")}
                      </button>
                    </div>

                    <div className="mt-3 space-y-2">
                      <input
                        value={historyLabel}
                        onChange={(event) => setHistoryLabel(event.target.value)}
                        placeholder={t("version_label_placeholder")}
                        className="h-8 w-full rounded-lg border border-black/10 bg-white/80 px-3 text-xs dark:border-white/10 dark:bg-white/[0.05]"
                      />
                      <input
                        value={historyDescription}
                        onChange={(event) => setHistoryDescription(event.target.value)}
                        placeholder={t("version_description_placeholder")}
                        className="h-8 w-full rounded-lg border border-black/10 bg-white/80 px-3 text-xs dark:border-white/10 dark:bg-white/[0.05]"
                      />
                      <button
                        type="button"
                        onClick={() => void createManualLatexVersion()}
                        disabled={viewReadOnly || historyActionBusy}
                        className="inline-flex h-8 w-full items-center justify-center gap-1 rounded-lg border border-[#8FA3B8]/30 bg-[#8FA3B8]/12 px-3 text-xs font-medium text-[#405267] hover:bg-[#8FA3B8]/18 disabled:opacity-50 dark:text-[#dbe6ef]"
                      >
                        {historyActionBusy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <History className="h-3.5 w-3.5" />}
                        {t("version_create")}
                      </button>
                    </div>

                    <div className="mt-3 max-h-56 space-y-1 overflow-auto pr-1">
                      {latexVersions.length > 0 ? (
                        latexVersions.map((version) => {
                          const selected = selectedLatexVersion?.version_id === version.version_id;
                          return (
                            <button
                              type="button"
                              key={version.version_id || version.commit}
                              onClick={() => {
                                setSelectedVersionId(version.version_id || version.commit);
                                setHistoryCompare(null);
                              }}
                              className={cn(
                                "w-full rounded-lg border px-3 py-2 text-left transition-colors",
                                selected
                                  ? "border-[#8FA3B8]/40 bg-[#8FA3B8]/14"
                                  : "border-black/5 bg-white/60 hover:bg-white/90 dark:border-white/10 dark:bg-white/[0.03]"
                              )}
                            >
                              <div className="flex items-center justify-between gap-2">
                                <span className="truncate text-xs font-medium text-foreground">{version.label}</span>
                                <span className="shrink-0 rounded-full border border-black/10 px-1.5 py-0.5 text-[10px] text-muted-foreground dark:border-white/10">
                                  {version.source}
                                </span>
                              </div>
                              <div className="mt-1 flex flex-wrap items-center gap-2 text-[10px] text-muted-foreground">
                                <span>{version.short_commit || version.commit?.slice(0, 7)}</span>
                                <span>{version.created_at ? new Date(version.created_at).toLocaleString(language) : ""}</span>
                                {typeof version.file_count === "number" ? <span>{version.file_count} {t("version_files_changed")}</span> : null}
                                {typeof version.added === "number" ? <span className="text-emerald-700 dark:text-emerald-300">+{version.added}</span> : null}
                                {typeof version.removed === "number" ? <span className="text-rose-700 dark:text-rose-300">-{version.removed}</span> : null}
                              </div>
                            </button>
                          );
                        })
                      ) : (
                        <div className="rounded-lg border border-dashed border-black/10 px-3 py-4 text-xs text-muted-foreground dark:border-white/10">
                          {historyLoading ? t("version_loading") : t("version_empty")}
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="min-w-0 flex-1 rounded-xl border border-black/5 bg-white/65 p-3 dark:border-white/10 dark:bg-white/[0.03]">
                    {selectedLatexVersion ? (
                      <div className="space-y-3">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="break-words text-sm font-medium text-foreground">{selectedLatexVersion.label}</div>
                            <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                              <span>{selectedLatexVersion.short_commit || selectedLatexVersion.commit.slice(0, 8)}</span>
                              <span>{selectedLatexVersion.source}</span>
                              {selectedLatexVersion.author ? <span>{selectedLatexVersion.author}</span> : null}
                              {selectedLatexVersion.build_id ? <span>{t("version_build")}: {selectedLatexVersion.build_id}</span> : null}
                            </div>
                            {selectedLatexVersion.description ? (
                              <div className="mt-2 text-xs text-muted-foreground">{selectedLatexVersion.description}</div>
                            ) : null}
                          </div>
                          <div className="flex flex-wrap items-center gap-2">
                            <button
                              type="button"
                              onClick={() => void compareSelectedLatexVersion()}
                              disabled={historyActionBusy || !latexVersionsHead}
                              className="inline-flex h-8 items-center gap-1 rounded-md border border-black/10 bg-white/80 px-2.5 text-xs hover:bg-white disabled:opacity-50 dark:border-white/10 dark:bg-white/[0.05]"
                            >
                              <GitCompare className="h-3.5 w-3.5" />
                              {t("version_compare_current")}
                            </button>
                            <button
                              type="button"
                              onClick={() => void restoreSelectedLatexVersion("file")}
                              disabled={viewReadOnly || historyActionBusy}
                              className="inline-flex h-8 items-center gap-1 rounded-md border border-amber-400/30 bg-white/80 px-2.5 text-xs text-amber-700 hover:bg-white disabled:opacity-50 dark:bg-white/[0.05] dark:text-amber-200"
                            >
                              <RotateCcw className="h-3.5 w-3.5" />
                              {t("version_restore_file")}
                            </button>
                            <button
                              type="button"
                              onClick={() => void restoreSelectedLatexVersion("folder")}
                              disabled={viewReadOnly || historyActionBusy}
                              className="inline-flex h-8 items-center gap-1 rounded-md border border-red-400/30 bg-white/80 px-2.5 text-xs text-red-700 hover:bg-white disabled:opacity-50 dark:bg-white/[0.05] dark:text-red-200"
                            >
                              <RotateCcw className="h-3.5 w-3.5" />
                              {t("version_restore_project")}
                            </button>
                          </div>
                        </div>

                        {historyCompare ? (
                          <div className="rounded-lg border border-black/5 bg-black/[0.02] p-3 dark:border-white/10 dark:bg-white/[0.03]">
                            <div className="mb-2 text-xs font-medium text-muted-foreground">
                              {t("version_compare_summary")}: {historyCompare.file_count ?? historyCompare.files?.length ?? 0} {t("version_files_changed")}
                            </div>
                            <div className="max-h-40 space-y-1 overflow-auto">
                              {(historyCompare.files || []).length > 0 ? (
                                historyCompare.files.map((file) => (
                                  <div key={`${file.path}:${file.status}`} className="flex items-center justify-between gap-3 rounded-md bg-white/60 px-2 py-1 text-xs dark:bg-white/[0.04]">
                                    <span className="min-w-0 truncate font-mono">{file.path}</span>
                                    <span className="shrink-0 text-muted-foreground">
                                      {file.status || "M"} · +{file.added ?? 0} / -{file.removed ?? 0}
                                    </span>
                                  </div>
                                ))
                              ) : (
                                <div className="text-xs text-muted-foreground">{t("version_compare_empty")}</div>
                              )}
                            </div>
                          </div>
                        ) : null}

                        {selectedLatexVersion.changed_paths && selectedLatexVersion.changed_paths.length > 0 ? (
                          <div>
                            <div className="mb-2 text-xs font-medium text-muted-foreground">{t("version_changed_files")}</div>
                            <div className="max-h-32 space-y-1 overflow-auto">
                              {selectedLatexVersion.changed_paths.map((path) => (
                                <div key={path} className="truncate rounded-md bg-black/[0.03] px-2 py-1 font-mono text-xs dark:bg-white/[0.04]">
                                  {path}
                                </div>
                              ))}
                            </div>
                          </div>
                        ) : null}
                      </div>
                    ) : (
                      <div className="flex h-full min-h-[160px] items-center justify-center text-xs text-muted-foreground">
                        {t("version_select_hint")}
                      </div>
                    )}
                  </div>
                </div>

                {historyError ? (
                  <div className="mt-3 flex items-start gap-2 rounded-lg border border-red-400/20 bg-red-50/80 px-3 py-2 text-xs text-red-700 dark:bg-red-500/10 dark:text-red-200">
                    <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                    <span>{historyError}</span>
                  </div>
                ) : null}
              </div>
            ) : null}

            {showAssistPanel ? (
              <div className="border-b border-black/5 dark:border-white/10 bg-black/[0.02] dark:bg-white/[0.02] px-3 py-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-foreground">
                      {referencePanelOpen ? t("assist_references_title") : t("assist_bibtex_title")}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {referencePanelOpen ? t("assist_reference_hint") : t("assist_bibtex_hint")}
                    </div>
                  </div>
                  {referencePanelOpen ? (
                    <input
                      value={assistQuery}
                      onChange={(event) => setAssistQuery(event.target.value)}
                      placeholder={t("assist_search_placeholder")}
                      className={cn(
                        "h-8 w-full rounded-lg border border-black/10 bg-white/80 px-3 text-sm",
                        "sm:w-[280px] dark:border-white/10 dark:bg-white/[0.05]"
                      )}
                    />
                  ) : null}
                </div>

                {referencePanelOpen ? (
                  <div className="mt-3 grid gap-3 lg:grid-cols-2">
                    <div className="rounded-xl border border-black/5 bg-white/70 p-3 dark:border-white/10 dark:bg-white/[0.03]">
                      <div className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                        {t("assist_citations")}
                      </div>
                      <div className="space-y-2">
                        {filteredCitationIndex.length > 0 ? (
                          filteredCitationIndex.map((entry) => (
                            <button
                              key={`${entry.sourceFile}:${entry.key}`}
                              type="button"
                              onClick={() => insertCitation(entry)}
                              className="w-full rounded-lg border border-black/5 bg-black/[0.02] px-3 py-2 text-left hover:bg-black/[0.04] dark:border-white/10 dark:bg-white/[0.03] dark:hover:bg-white/[0.05]"
                              title={entry.title || entry.key}
                            >
                              <div className="flex items-center justify-between gap-3">
                                <span className="font-mono text-xs text-foreground">{entry.key}</span>
                                <span className="text-[10px] text-muted-foreground">
                                  {t("assist_insert_citation")}
                                </span>
                              </div>
                              {entry.title ? (
                                <div className="mt-1 truncate text-xs text-muted-foreground">{entry.title}</div>
                              ) : null}
                              <div className="mt-1 truncate text-[10px] text-muted-foreground/80">
                                {entry.author || entry.sourceFile}
                              </div>
                            </button>
                          ))
                        ) : (
                          <div className="rounded-lg border border-dashed border-black/10 px-3 py-4 text-xs text-muted-foreground dark:border-white/10">
                            {t("assist_empty_citations")}
                          </div>
                        )}
                      </div>
                    </div>

                    <div className="rounded-xl border border-black/5 bg-white/70 p-3 dark:border-white/10 dark:bg-white/[0.03]">
                      <div className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                        {t("assist_labels")}
                      </div>
                      <div className="space-y-2">
                        {filteredLabelIndex.length > 0 ? (
                          filteredLabelIndex.map((entry) => (
                            <button
                              key={`${entry.sourceFile}:${entry.key}`}
                              type="button"
                              onClick={() => insertLabelReference(entry)}
                              className="w-full rounded-lg border border-black/5 bg-black/[0.02] px-3 py-2 text-left hover:bg-black/[0.04] dark:border-white/10 dark:bg-white/[0.03] dark:hover:bg-white/[0.05]"
                              title={entry.key}
                            >
                              <div className="flex items-center justify-between gap-3">
                                <span className="font-mono text-xs text-foreground">{entry.key}</span>
                                <span className="text-[10px] text-muted-foreground">
                                  {t("assist_insert_reference")}
                                </span>
                              </div>
                              <div className="mt-1 truncate text-[10px] text-muted-foreground/80">
                                {entry.sourceFile}
                              </div>
                            </button>
                          ))
                        ) : (
                          <div className="rounded-lg border border-dashed border-black/10 px-3 py-4 text-xs text-muted-foreground dark:border-white/10">
                            {t("assist_empty_labels")}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="mt-3 grid gap-2 md:grid-cols-3">
                    {BIB_SNIPPETS.length > 0 ? (
                      BIB_SNIPPETS.map((item) => (
                        <button
                          key={item.id}
                          type="button"
                          onClick={() => insertBibSnippet(item.snippet)}
                          className="rounded-xl border border-black/5 bg-white/70 px-3 py-3 text-left hover:bg-white/90 dark:border-white/10 dark:bg-white/[0.03] dark:hover:bg-white/[0.05]"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="font-mono text-sm text-foreground">@{item.id}</span>
                            <span className="text-[10px] text-muted-foreground">
                              {t("assist_insert_snippet")}
                            </span>
                          </div>
                          <div className="mt-2 text-xs text-muted-foreground">{t(item.labelKey)}</div>
                        </button>
                      ))
                    ) : (
                      <div className="rounded-lg border border-dashed border-black/10 px-3 py-4 text-xs text-muted-foreground dark:border-white/10">
                        {t("assist_empty_bib")}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ) : null}

	          <div className="flex-1 min-h-0">
	            {syncState === "loading" ? (
	              <div className="h-full flex items-center justify-center text-muted-foreground">
                <Loader2 className="h-5 w-5 animate-spin mr-2" />
                {t("connecting")}
              </div>
            ) : syncState === "error" ? (
              <div className="h-full flex items-center justify-center text-sm text-red-600">
                {error ?? t("load_files_failed")}
              </div>
            ) : (
              <MonacoEditor
                key={`${activeFileId ?? "latex"}:${resetNonce}`}
                defaultValue={initialText}
                language={isBibFile ? BIBTEX_LANGUAGE_ID : LATEX_LANGUAGE_ID}
                theme={isDark ? "vs-dark" : "light"}
                beforeMount={(monaco) => {
                  try {
                    ensureMonacoLatexLanguages(monaco);
                  } catch (e) {
                    console.error("[LatexPlugin] Failed to configure LaTeX language:", e);
                  }
                }}
                onMount={(editor, monaco) => {
                  try {
                    bindEditor(editor, monaco);
                  } catch (e) {
                    console.error("[LatexPlugin] Failed to bind editor:", e);
                  }
                }}
                options={{
                  readOnly: effectiveReadOnly,
                  automaticLayout: true,
                  minimap: { enabled: false },
                  wordWrap: "on",
                  fontSize: 13,
                  scrollBeyondLastLine: false,
                  tabCompletion: "on",
                  quickSuggestions: { other: true, comments: false, strings: false },
                  suggestOnTriggerCharacters: true,
                  acceptSuggestionOnCommitCharacter: true,
                  renderWhitespace: "selection",
                  selectionHighlight: false,
                  occurrencesHighlight: "off",
                  tabSize: 2,
                  insertSpaces: true,
                }}
              />
            )}
          </div>

        {externalConflict ? (
          <div className="border-t border-amber-300/30 bg-amber-50/80 dark:bg-amber-500/10 dark:border-amber-300/20 p-4 text-sm">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="flex min-w-0 items-start gap-2 text-amber-800 dark:text-amber-100">
                <AlertTriangle className="h-4 w-4 mt-0.5 flex-shrink-0" />
                <div className="min-w-0">
                  <div className="font-medium">{t("external_change_title")}</div>
                  <div className="text-xs opacity-90 break-words">
                    {t("external_change_dirty_message")}
                  </div>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2 sm:justify-end">
                <button
                  type="button"
                  className="inline-flex items-center rounded-md border border-amber-400/40 bg-white/80 px-2.5 py-1.5 text-xs font-medium text-amber-800 hover:bg-white dark:bg-white/[0.06] dark:text-amber-100 dark:hover:bg-white/[0.1]"
                  onClick={reloadExternalVersion}
                >
                  {t("external_change_reload")}
                </button>
                <button
                  type="button"
                  className="inline-flex items-center rounded-md border border-red-400/30 bg-white/80 px-2.5 py-1.5 text-xs font-medium text-red-700 hover:bg-white dark:bg-white/[0.06] dark:text-red-200 dark:hover:bg-white/[0.1]"
                  onClick={overwriteExternalVersion}
                >
                  {t("external_change_overwrite")}
                </button>
              </div>
            </div>
          </div>
        ) : null}

        {saveError ? (
          <div className="border-t border-black/5 dark:border-white/10 p-4 text-sm">
            <div className="flex items-start gap-2 text-red-600">
              <AlertTriangle className="h-4 w-4 mt-0.5" />
              <div className="min-w-0">
                <div className="font-medium">{t("save_failed_title")}</div>
                <div className="text-xs opacity-90 break-words">
                  {saveError}
                </div>
              </div>
            </div>
          </div>
        ) : null}

        {buildStatus === "error" ? (
          <div className="border-t border-black/5 dark:border-white/10 p-4 text-sm max-h-[35vh] overflow-auto">
            <div className="flex items-start gap-2 text-red-600">
              <AlertTriangle className="h-4 w-4 mt-0.5" />
              <div className="min-w-0">
                <div className="font-medium">{t("compile_failed_title")}</div>
                <div className="text-xs opacity-90 break-words">
                  {buildError ?? t("compile_failed_fallback")}
                </div>
              </div>
            </div>
            {buildErrors.length > 0 ? (
              <div className="mt-3 space-y-2 text-xs">
                {buildErrors.slice(0, 12).map((err, idx) => renderBuildIssueRow(err, idx, "error"))}
                {buildErrors.length > 12 ? (
                  <div className="text-muted-foreground">
                    {t("more_items", { count: buildErrors.length - 12 })}
                  </div>
                ) : null}
              </div>
            ) : null}
            {logText ? (
              <pre className="mt-3 text-xs whitespace-pre-wrap break-words text-muted-foreground max-h-[40vh] overflow-auto rounded-lg border border-black/10 dark:border-white/10 bg-white/60 dark:bg-white/[0.03] p-3">
                {logText.slice(0, 8000)}
              </pre>
            ) : null}
          </div>
        ) : null}
        {buildStatus !== "error" && warningItems.length > 0 ? (
          <div className="border-t border-black/5 dark:border-white/10 p-4 text-sm max-h-[35vh] overflow-auto">
            <div className="flex items-start gap-2 text-amber-700">
              <AlertTriangle className="h-4 w-4 mt-0.5" />
              <div className="min-w-0">
                <div className="font-medium">{t("warnings_title")}</div>
                <div className="text-xs opacity-90 break-words">
                  {t("warnings_reported", {
                    count: warningItems.length,
                    suffix: language === "zh-CN" || warningItems.length === 1 ? "" : "s",
                  })}
                </div>
              </div>
            </div>
            <div className="mt-3 space-y-2 text-xs">
              {warningItems.slice(0, 12).map((err, idx) => renderBuildIssueRow(err, idx, "warning"))}
              {warningItems.length > 12 ? (
                <div className="text-muted-foreground">
                  {t("more_items", { count: warningItems.length - 12 })}
                </div>
              ) : null}
            </div>
          </div>
        ) : null}
        </div>

        {isWideLayout ? (
          <div
            className={cn(
              "hidden lg:flex w-3 relative items-stretch cursor-col-resize",
              isResizing ? "bg-primary/10" : "hover:bg-black/5 dark:hover:bg-white/[0.06]"
            )}
            onPointerDown={handleResizeStart}
            role="separator"
            aria-orientation="vertical"
            aria-label={t("resize_panels_aria")}
          >
            <div
              className={cn(
                "absolute inset-y-0 left-1/2 w-px",
                isResizing ? "bg-primary/60" : "bg-black/10 dark:bg-white/10"
              )}
            />
          </div>
        ) : null}

        <div className="min-h-0 flex flex-1 flex-col min-w-0">
          <div ref={pdfPaneRef} className="relative flex-1 min-h-0 overflow-hidden">
            <div
              className={cn(
                "absolute z-10 flex flex-col gap-2",
                isWideLayout
                  ? "left-3 top-1/2 -translate-y-1/2"
                  : "right-3 top-3",
                "rounded-full border border-black/10 bg-white/80 p-1 shadow-sm",
                "backdrop-blur dark:border-white/10 dark:bg-black/40"
              )}
              onPointerDown={(event) => event.stopPropagation()}
            >
              <button
                type="button"
                onClick={handleZoomOut}
                disabled={zoomOutDisabled}
                className={cn(
                  "h-7 w-7 rounded-full flex items-center justify-center",
                  "text-muted-foreground hover:text-foreground hover:bg-black/5",
                  "dark:hover:bg-white/[0.08]",
                  "disabled:opacity-40 disabled:cursor-not-allowed"
                )}
                aria-label={t("zoom_out")}
                title={t("zoom_out")}
              >
                <ZoomOut className="h-4 w-4" />
              </button>
              <div className="text-[11px] font-medium text-muted-foreground text-center">
                {pdfObjectUrl ? `${Math.round(renderScale * 100)}%` : "--"}
              </div>
              <button
                type="button"
                onClick={handleZoomIn}
                disabled={zoomInDisabled}
                className={cn(
                  "h-7 w-7 rounded-full flex items-center justify-center",
                  "text-muted-foreground hover:text-foreground hover:bg-black/5",
                  "dark:hover:bg-white/[0.08]",
                  "disabled:opacity-40 disabled:cursor-not-allowed"
                )}
                aria-label={t("zoom_in")}
                title={t("zoom_in")}
              >
                <ZoomIn className="h-4 w-4" />
              </button>
              <a
                href={pdfObjectUrl ?? "#"}
                download={pdfFileName}
                className={cn(
                  "h-7 w-7 rounded-full text-xs font-medium border flex items-center justify-center",
                  "bg-white/70 border-black/10 hover:bg-white/90",
                  "dark:bg-white/[0.04] dark:border-white/10 dark:hover:bg-white/[0.08]",
                  !pdfObjectUrl && "opacity-50 pointer-events-none"
                )}
                title={t("download_pdf")}
              >
                <Download className="h-3.5 w-3.5" />
	              </a>
	            </div>

              {pdfObjectUrl && (synctexBusy || synctexError) ? (
                <div
                  className={cn(
                    "absolute bottom-3 left-3 z-10 max-w-[min(460px,calc(100%-1.5rem))] rounded-xl border px-3 py-2 text-xs shadow-sm backdrop-blur",
                    synctexError
                      ? "border-amber-400/30 bg-amber-50/90 text-amber-800 dark:bg-amber-500/10 dark:text-amber-100"
                      : "border-black/10 bg-white/75 text-muted-foreground dark:border-white/10 dark:bg-black/40"
                  )}
                >
                  <div className="flex items-center gap-2">
                    {synctexBusy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
                    <span>{synctexError ?? t("synctex_resolving")}</span>
                  </div>
                </div>
              ) : null}

	            {pdfObjectUrl ? (
	              <PdfLoader
                url={pdfObjectUrl}
                workerSrc={PDF_WORKER_SRC}
                cMapUrl={PDF_CMAP_URL}
                cMapPacked
                beforeLoad={
                  <div className="flex-1 flex items-center justify-center text-sm text-muted-foreground">
                    <Loader2 className="h-5 w-5 animate-spin mr-2" />
                    {t("loading_pdf")}
                  </div>
                }
              >
                {(pdfDocument) => (
                  <PdfSurface
                    pdfDocument={pdfDocument}
	                    zoomFactor={zoomScale}
	                    highlights={emptyHighlights}
	                    onPageWidth={handlePageWidth}
	                    onPointDoubleClick={handlePdfPointDoubleClick}
	                  />
	                )}
              </PdfLoader>
            ) : buildStatus === "queued" || buildStatus === "running" ? (
              <div className="flex-1 flex items-center justify-center text-sm text-muted-foreground">
                <Loader2 className="h-5 w-5 animate-spin mr-2" />
                {t("preview_compiling")}
              </div>
            ) : buildStatus === "error" ? (
              <div className="flex-1 flex items-center justify-center text-sm text-muted-foreground">
                {t("preview_no_output")}
              </div>
            ) : (
              <div className="flex-1 flex items-center justify-center text-sm text-muted-foreground">
                {t("preview_empty")}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
