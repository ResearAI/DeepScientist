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
} from "lucide-react";
import type { PluginComponentProps } from "@/lib/types/plugin";
import { cn } from "@/lib/utils";
import { client as questClient } from "@/lib/api";
import { listFiles, getFileContent, updateFileContent } from "@/lib/api/files";
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
  getLatexBuild,
  getLatexBuildLogText,
  getLatexBuildPdfBlob,
  listLatexBuilds,
  type LatexCompiler,
  type LatexBuildStatus,
  type LatexBuildError,
  type LatexLogItem,
} from "@/lib/api/latex";
import { useI18n } from "@/lib/i18n/useI18n";
import { useWorkspaceSurfaceStore } from "@/lib/stores/workspace-surface";
import { toFilesResourcePath } from "@/lib/utils/resource-paths";
import { supportsSocketIo } from "@/lib/runtime/quest-runtime";

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
};

type LatexFileMeta = {
  id: string;
  name: string;
  path?: string;
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

type BibSnippet = {
  id: string;
  labelKey: string;
  snippet: string;
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

function normalizeCompiler(value?: string | null): LatexCompiler {
  if (value === "xelatex" || value === "lualatex") return value;
  return "pdflatex";
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

  const exact = files.find((file) => normalizeLatexPath(file.name) === normalized);
  if (exact) return exact.id;

  const basename = normalized.split("/").filter(Boolean).pop();
  if (!basename) return null;

  const byBasename = files.find((file) => normalizeLatexPath(file.name).endsWith(`/${basename}`));
  if (byBasename) return byBasename.id;

  const simpleName = files.find((file) => file.name.toLowerCase() === basename);
  return simpleName?.id ?? null;
}

function PdfSurface({ pdfDocument, zoomFactor, highlights, onPageWidth }: PdfSurfaceProps) {
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
  const initialFileId = custom.openFileId ?? custom.mainFileId ?? null;
  const [activeFileId, setActiveFileId] = React.useState<string | null>(initialFileId);
  const [activeFileName, setActiveFileName] = React.useState<string>("main.tex");
  const [initialText, setInitialText] = React.useState<string>("");
  const [syncState, setSyncState] = React.useState<"idle" | "loading" | "ready" | "error">("idle");
  const [saveState, setSaveState] = React.useState<"idle" | "saving" | "error">("idle");
  const [error, setError] = React.useState<string | null>(null);
  const [isDirty, setIsDirty] = React.useState(false);
  const [buildId, setBuildId] = React.useState<string | null>(null);
  const [buildStatus, setBuildStatus] = React.useState<LatexBuildStatus | "idle">("idle");
  const [buildError, setBuildError] = React.useState<string | null>(null);
  const [buildErrors, setBuildErrors] = React.useState<LatexBuildError[]>([]);
  const [compiler, setCompiler] = React.useState<LatexCompiler>("pdflatex");
  const [currentBranch, setCurrentBranch] = React.useState<string | null>(null);
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
  const pendingJumpRef = React.useRef<{ fileId: string | null; line: number } | null>(null);
  const citationIndexRef = React.useRef<CitationEntry[]>([]);
  const labelIndexRef = React.useRef<LabelEntry[]>([]);
  const latexCompletionDisposablesRef = React.useRef<Array<{ dispose?: () => void }>>([]);

  const effectiveReadOnly = viewReadOnly || roleWritable === false;
  const socketAuthMode = "user";
  const canUseRealtimeSync = supportsSocketIo();
  const isBibFile = activeFileName.toLowerCase().endsWith(".bib");

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
            : buildStatus === "error"
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

  // Load folder file list.
  React.useEffect(() => {
    if (!projectId || !latexFolderId) return;
    let cancelled = false;
    (async () => {
      try {
        const items = await listFiles(projectId, latexFolderId);
        if (cancelled) return;
        const candidates = items
          .filter((x) => x.type === "file")
          .map((x) => ({ id: x.id, name: x.name, path: x.path || undefined }))
          .sort((a, b) => a.name.localeCompare(b.name));
        setFiles(candidates);

        // Resolve a main file if needed.
        if (!activeFileId) {
          const main =
            candidates.find((f) => f.name.toLowerCase() === "main.tex") ??
            candidates.find((f) => f.name.toLowerCase().endsWith(".tex")) ??
            candidates[0];
          if (main) {
            setActiveFileId(main.id);
            setActiveFileName(main.name);
          }
        } else {
          const meta = candidates.find((f) => f.id === activeFileId);
          if (meta) setActiveFileName(meta.name);
        }
      } catch (e) {
        console.error("[LatexPlugin] Failed to list files:", e);
        setError(e instanceof Error ? e.message : t("load_files_failed"));
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, latexFolderId]);

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
          .flatMap((item) => parseBibEntries(item.content, item.file.name))
          .sort((a, b) => a.key.localeCompare(b.key));

        const nextLabelIndex = loaded
          .filter((item) => item.file.name.toLowerCase().endsWith(".tex"))
          .flatMap((item) => parseLatexLabels(item.content, item.file.name))
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
      }
    };
  }, [activeFileId]);

  // Sync LaTeX doc (Yjs) via space:* protocol (notebook-style).
  React.useEffect(() => {
    if (!projectId || !activeFileId) return;

    let cancelled = false;
    let cleanup: null | (() => void) = null;

    setSyncState("loading");
    setError(null);

    (async () => {
      const { Doc, applyUpdate, encodeStateVector, encodeStateAsUpdate, mergeUpdates } =
        await import("yjs");

      const ydoc = new Doc();
      const ytext = ydoc.getText("content");
      yDocRef.current = ydoc;
      yTextRef.current = ytext;

      if (!canUseRealtimeSync) {
        const seed = await getFileContent(activeFileId);
        ydoc.transact(() => {
          const length = ytext.length || 0;
          if (length) ytext.delete(0, length);
          if (seed) ytext.insert(0, seed);
        }, "ds-local-seed");

        const textNow = ytext.toString();
        setInitialText(textNow);
        lastSavedRef.current = textNow;
        setIsDirty(false);
        setDirty(false);
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
        const seed = await getFileContent(activeFileId);
        ydoc.transact(() => {
          const length = ytext.length || 0;
          if (length) ytext.delete(0, length);
          if (seed) ytext.insert(0, seed);
        }, "ds-reset");
        if (!effectiveReadOnly) {
          const resetUpdate = encodeStateAsUpdate(ydoc);
          await sync.pushDocUpdate(activeFileId, resetUpdate);
        }
        forceSeedRef.current = false;
      }

      if (!diff) {
        const seed = await getFileContent(activeFileId);
        ydoc.transact(() => {
          ytext.insert(0, seed);
        }, "ds-seed");
        if (!effectiveReadOnly) {
          const initUpdate = encodeStateAsUpdate(ydoc);
          await sync.pushDocUpdate(activeFileId, initUpdate);
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
      setIsDirty(false);
      setDirty(false);
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
  }, [activeFileId, canUseRealtimeSync, effectiveReadOnly, projectId, resetNonce, setDirty, socketAuthMode, t, user?.id, user?.username]);

  const jumpEditorToLine = React.useCallback((line: number) => {
    const editor = editorRef.current;
    if (!editor) return false;
    const model = editor.getModel?.();
    if (!model) return false;

    const maxLine = Math.max(1, Number(model.getLineCount?.() ?? 1));
    const safeLine = Math.min(Math.max(1, Math.round(line || 1)), maxLine);
    editor.revealLineInCenter?.(safeLine);
    editor.setPosition?.({ lineNumber: safeLine, column: 1 });
    editor.setSelection?.({
      startLineNumber: safeLine,
      startColumn: 1,
      endLineNumber: safeLine,
      endColumn: Number(model.getLineMaxColumn?.(safeLine) ?? 1),
    });
    editor.focus?.();
    return true;
  }, []);

  const flushPendingJump = React.useCallback(() => {
    const pending = pendingJumpRef.current;
    if (!pending) return;
    if (pending.fileId && pending.fileId !== activeFileId) return;
    if (jumpEditorToLine(pending.line)) {
      pendingJumpRef.current = null;
    }
  }, [activeFileId, jumpEditorToLine]);

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
    setIsDirty(true);
    setDirty(true);
  }, [effectiveReadOnly, setDirty]);

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

      const ensureLanguage = (id: string) => {
        const languages = monaco.languages.getLanguages?.() || [];
        if (!languages.some((item: { id: string }) => item.id === id)) {
          monaco.languages.register({ id });
        }
      };
      ensureLanguage("latex-ds");
      ensureLanguage("bibtex-ds");
      monaco.editor.setModelLanguage(model, isBibFile ? "bibtex-ds" : "latex-ds");

      latexCompletionDisposablesRef.current.forEach((disposable) => {
        try {
          disposable?.dispose?.();
        } catch {
          // ignore
        }
      });
      latexCompletionDisposablesRef.current = [
        monaco.languages.registerCompletionItemProvider("latex-ds", {
          triggerCharacters: ["\\", "{"],
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

            return { suggestions: [] };
          },
        }),
        monaco.languages.registerCompletionItemProvider("bibtex-ds", {
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
        setIsDirty(true);
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
        setIsDirty(true);
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
    [effectiveReadOnly, flushPendingJump, isBibFile, setDirty, t]
  );

  React.useEffect(() => {
    if (syncState !== "ready") return;
    flushPendingJump();
  }, [activeFileId, flushPendingJump, resetNonce, syncState]);

  const save = React.useCallback(async () => {
    if (!activeFileId) return false;
    if (effectiveReadOnly) return false;
    const ytext = yTextRef.current;
    if (!ytext) return false;
    try {
      setSaveState("saving");
      const text = String(ytext.toString?.() ?? "");
      const res = await updateFileContent(activeFileId, text);
      lastSavedRef.current = text;
      setSaveState("idle");
      setIsDirty(false);
      setDirty(false);
      if (res?.updated_at) {
        updateFileMeta(activeFileId, {
          updatedAt: res.updated_at,
          size: typeof res.size === "number" ? res.size : undefined,
          mimeType: res.mime_type,
        });
      }
      return true;
    } catch (e) {
      console.error("[LatexPlugin] Save failed:", e);
      setSaveState("error");
      window.setTimeout(() => setSaveState("idle"), 1400);
      return false;
    }
  }, [activeFileId, effectiveReadOnly, setDirty, updateFileMeta]);

  const compile = React.useCallback(
    async (opts?: { auto?: boolean }) => {
      if (!projectId || !latexFolderId) return;
      if (viewReadOnly) return;
      if (isDirty && !effectiveReadOnly) {
        const saved = await save();
        if (!saved) return;
      }

      try {
        setBuildError(null);
        setBuildErrors([]);
        setLogText(null);
        setBuildStatus("queued");
        const res = await compileLatex(projectId, latexFolderId, {
          compiler,
          auto: Boolean(opts?.auto),
          stop_on_first_error: false,
        });
        setBuildId(res.build_id);
        setCompiler(normalizeCompiler(res.compiler));
        setBuildStatus(res.status ?? "queued");
      } catch (e) {
        console.error("[LatexPlugin] Compile failed:", e);
        setBuildError(e instanceof Error ? e.message : t("compile_request_failed"));
        setBuildStatus("error");
      }
    },
    [compiler, effectiveReadOnly, isDirty, latexFolderId, projectId, save, t, viewReadOnly]
  );

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
    if (saveState === "saving") {
      return {
        label: t("status_saving"),
        className:
          "border-[#A6B0B6]/30 bg-[#A6B0B6]/12 text-[#5c666b] dark:bg-[#A6B0B6]/12 dark:text-[#d8dde0]",
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
  }, [buildStatus, effectiveReadOnly, isDirty, saveState, t]);

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

      const targetMeta = files.find((file) => file.id === targetFileId);
      pendingJumpRef.current = {
        fileId: targetFileId,
        line: Math.max(1, Number(issue.line || 1)),
      };

      if (targetMeta?.name && targetMeta.name !== activeFileName) {
        setActiveFileName(targetMeta.name);
      }

      if (targetFileId !== activeFileId) {
        setActiveFileId(targetFileId);
        return;
      }

      flushPendingJump();
    },
    [activeFileId, activeFileName, files, flushPendingJump, focusBuildIssue]
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
          <div className="flex flex-wrap items-center gap-2 px-3 py-2 border-b border-black/5 dark:border-white/10">
            <div className="flex items-center gap-2 min-w-0">
              <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
              <select
                className={cn(
                  "h-8 rounded-lg px-2 text-sm bg-white/70 border border-black/10",
                  "dark:bg-white/[0.04] dark:border-white/10",
                  "min-w-[160px] max-w-[260px] truncate",
                  effectiveReadOnly && "opacity-70"
                )}
                value={activeFileId ?? ""}
                onChange={(e) => {
                  const next = e.target.value || null;
                  const meta = files.find((f) => f.id === next);
                  if (meta) setActiveFileName(meta.name);
                  setActiveFileId(next);
                }}
                disabled={files.length === 0}
                aria-label={t("file_label")}
                title={activeFileName}
              >
                {files.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">{t("compiler_label")}</span>
              <select
                className={cn(
                  "h-8 rounded-lg px-2 text-sm bg-white/70 border border-black/10",
                  "dark:bg-white/[0.04] dark:border-white/10",
                  "min-w-[122px]",
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
                  "h-8 px-3 rounded-lg text-sm border inline-flex items-center gap-2",
                  "bg-white/70 border-black/10 hover:bg-white/90",
                  "dark:bg-white/[0.04] dark:border-white/10 dark:hover:bg-white/[0.08]",
                  referencePanelOpen && "border-[#8FA3B8]/28 bg-[#8FA3B8]/12 text-[#405267]"
                )}
                aria-label={t("assist_references")}
                title={t("assist_references")}
              >
                <Link2 className="h-4 w-4" />
                {t("assist_references")}
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
                  "h-8 px-3 rounded-lg text-sm border inline-flex items-center gap-2",
                  "bg-white/70 border-black/10 hover:bg-white/90",
                  "dark:bg-white/[0.04] dark:border-white/10 dark:hover:bg-white/[0.08]",
                  bibPanelOpen && "border-[#A99EBE]/28 bg-[#A99EBE]/12 text-[#564f6a]"
                )}
                aria-label={t("assist_bibtex")}
                title={t("assist_bibtex")}
              >
                <AtSign className="h-4 w-4" />
                {t("assist_bibtex")}
              </button>
            ) : null}

            <div className="ml-auto flex items-center gap-2">
              <span
                className={cn(
                  "text-xs px-2 py-0.5 rounded-full border",
                  statusBadge.className
                )}
              >
                {statusBadge.label}
              </span>

              <button
                type="button"
                onClick={save}
                disabled={effectiveReadOnly || saveState === "saving" || !isDirty}
                className={cn(
                  "h-8 px-3 rounded-lg text-sm font-medium border",
                  "bg-white/70 border-black/10 hover:bg-white/90",
                  "dark:bg-white/[0.04] dark:border-white/10 dark:hover:bg-white/[0.08]",
                  "disabled:opacity-50 disabled:cursor-not-allowed",
                  isDirty && !effectiveReadOnly && "border-black/20"
                )}
              >
                {saveState === "saving" ? (
                  <span className="flex items-center gap-2">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    {t("button_saving")}
                  </span>
                ) : (
                  <span className="flex items-center gap-2">
                    <Save className="h-4 w-4" />
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
                  "h-8 px-3 rounded-lg text-sm font-medium border",
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
                  <span className="flex items-center gap-2">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    {t("button_compiling")}
                  </span>
                ) : (
                  <span className="flex items-center gap-2">
                    <Play className="h-4 w-4" />
                    {isDirty && !effectiveReadOnly ? t("button_save_and_compile") : t("button_compile")}
                  </span>
                )}
              </button>
            </div>
	          </div>

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
                language="plaintext"
                theme={isDark ? "vs-dark" : "light"}
                onMount={(editor, monaco) => {
                  try {
                    bindEditor(editor, monaco);
                  } catch (e) {
                    console.error("[LatexPlugin] Failed to bind editor:", e);
                  }
                }}
                options={{
                  readOnly: effectiveReadOnly,
                  minimap: { enabled: false },
                  wordWrap: "on",
                  fontSize: 13,
                  scrollBeyondLastLine: false,
                }}
              />
            )}
          </div>

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
