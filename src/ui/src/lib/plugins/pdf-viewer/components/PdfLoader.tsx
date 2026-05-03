/**
 * PdfLoader Component
 *
 * Loads PDF documents using PDF.js and provides the document proxy
 * to child components through a render prop pattern.
 *
 * @module plugins/pdf-viewer/components/PdfLoader
 */

"use client";

import React, { useState, useEffect } from "react";
import { Loader2, AlertCircle, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n/useI18n";
import { PDF_CMAP_PACKED, PDF_CMAP_URL, PDF_WORKER_SRC } from "../lib/pdf-utils";

// ============================================================
// Types
// ============================================================

interface PDFDocumentProxy {
  numPages: number;
  getPage: (pageNumber: number) => Promise<PDFPageProxy>;
  getMetadata: () => Promise<{ info?: Record<string, unknown> }>;
  destroy: () => void;
}

interface PDFPageProxy {
  pageNumber: number;
  getViewport: (options: { scale: number }) => PDFViewport;
  render: (options: {
    canvasContext: CanvasRenderingContext2D;
    viewport: PDFViewport;
  }) => PDFRenderTask;
  getTextContent: () => Promise<PDFTextContent>;
}

interface PDFViewport {
  width: number;
  height: number;
  scale: number;
}

interface PDFRenderTask {
  promise: Promise<void>;
  cancel: () => void;
}

interface PDFDocumentLoadingTask {
  promise: Promise<PDFDocumentProxy>;
  destroy: () => Promise<void> | void;
}

interface PDFTextContent {
  items: Array<{ str: string; transform: number[] }>;
}

interface PdfLoaderProps {
  /** URL to load PDF from (can be API endpoint or blob URL) */
  url: string;
  /** Optional headers (e.g. Authorization) for PDF.js requests */
  httpHeaders?: Record<string, string>;
  /** Render function when PDF is loaded */
  children: (pdfDocument: PDFDocumentProxy) => React.ReactNode;
  /** Error callback */
  onError?: (error: Error) => void;
  /** Loading started callback */
  onLoadStart?: () => void;
  /** Loading complete callback */
  onLoadComplete?: (pdfDocument: PDFDocumentProxy) => void;
  /** Custom loading component */
  loadingComponent?: React.ReactNode;
  /** Custom error component */
  errorComponent?: React.ReactNode;
}

// ============================================================
// Loading State Component
// ============================================================

function LoadingState() {
  const { t } = useI18n("pdf_viewer");

  return (
    <div className="flex items-center justify-center h-full bg-muted/30">
      <div className="flex flex-col items-center gap-4">
        <Loader2 className="w-10 h-10 animate-spin text-muted-foreground" />
        <div className="text-sm text-muted-foreground">{t("loading_pdf")}</div>
      </div>
    </div>
  );
}

// ============================================================
// Error State Component
// ============================================================

interface ErrorStateProps {
  error: Error;
  onRetry: () => void;
}

function ErrorState({ error, onRetry }: ErrorStateProps) {
  const { t } = useI18n("pdf_viewer");

  return (
    <div className="flex items-center justify-center h-full bg-muted/30">
      <div className="flex flex-col items-center gap-4 max-w-md p-6 text-center">
        <AlertCircle className="w-12 h-12 text-destructive" />
        <div>
          <h3 className="text-lg font-semibold text-foreground mb-2">
            {t("failed_to_load_pdf")}
          </h3>
          <p className="text-sm text-muted-foreground mb-4">{error.message}</p>
        </div>
        <button
          onClick={onRetry}
          className={cn(
            "flex items-center gap-2 px-4 py-2 rounded-lg",
            "bg-primary text-primary-foreground",
            "hover:bg-primary/90 transition-colors"
          )}
        >
          <RefreshCw className="w-4 h-4" />
          {t("try_again")}
        </button>
      </div>
    </div>
  );
}

// ============================================================
// PdfLoader Component
// ============================================================

/**
 * PdfLoader Component
 *
 * Loads a PDF document using PDF.js and renders children with the document proxy.
 * Handles loading states, errors, and cleanup.
 *
 * @example
 * ```tsx
 * <PdfLoader url="/api/files/123/content">
 *   {(pdfDocument) => (
 *     <PdfHighlighter pdfDocument={pdfDocument} scale={1.0} />
 *   )}
 * </PdfLoader>
 * ```
 */
export function PdfLoader({
  url,
  httpHeaders,
  children,
  onError,
  onLoadStart,
  onLoadComplete,
  loadingComponent,
  errorComponent,
}: PdfLoaderProps) {
  const [pdfDocument, setPdfDocument] = useState<PDFDocumentProxy | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let loadingTask: PDFDocumentLoadingTask | null = null;
    let loadedDoc: PDFDocumentProxy | null = null;

    setLoading(true);
    setError(null);
    setPdfDocument(null);
    onLoadStart?.();

    void (async () => {
      try {
        // Dynamically import PDF.js to avoid SSR issues.
        const pdfjsLib = await import("pdfjs-dist");

        // Configure worker.
        if (typeof window !== "undefined") {
          pdfjsLib.GlobalWorkerOptions.workerSrc = PDF_WORKER_SRC;
        }

        if (cancelled) {
          return;
        }

        loadingTask = pdfjsLib.getDocument({
          url,
          httpHeaders,
          // Enable range requests for large files.
          disableRange: false,
          disableStream: false,
          // Enable auto-fetch for better performance.
          disableAutoFetch: false,
          ...(PDF_CMAP_URL
            ? {
                cMapUrl: PDF_CMAP_URL,
                cMapPacked: PDF_CMAP_PACKED,
              }
            : {}),
        }) as unknown as PDFDocumentLoadingTask;

        const doc = await loadingTask.promise;
        loadedDoc = doc;

        if (cancelled) {
          try {
            loadedDoc.destroy();
          } catch {
            // Ignore cleanup errors
          }
          return;
        }

        setPdfDocument(loadedDoc);
        setLoading(false);
        onLoadComplete?.(loadedDoc);
      } catch (err) {
        if (!cancelled) {
          const errorObj = err instanceof Error ? err : new Error("Failed to load PDF");
          setError(errorObj);
          setLoading(false);
          onError?.(errorObj);
        }
      }
    })();

    return () => {
      cancelled = true;
      if (loadingTask) {
        try {
          void loadingTask.destroy();
        } catch {
          // Ignore cleanup errors
        }
      }
      if (loadedDoc) {
        try {
          loadedDoc.destroy();
        } catch {
          // Ignore cleanup errors
        }
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, retryCount]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (pdfDocument) {
        try {
          pdfDocument.destroy();
        } catch {
          // Ignore cleanup errors
        }
      }
    };
  }, [pdfDocument]);

  // Handle retry
  const handleRetry = useCallback(() => {
    setRetryCount((c) => c + 1);
  }, []);

  // Render loading state
  if (loading) {
    return <>{loadingComponent ?? <LoadingState />}</>;
  }

  // Render error state
  if (error) {
    return (
      <>
        {errorComponent ?? <ErrorState error={error} onRetry={handleRetry} />}
      </>
    );
  }

  // Render children with document
  return pdfDocument ? <>{children(pdfDocument)}</> : null;
}

// ============================================================
// Export Types
// ============================================================

export type {
  PDFDocumentProxy,
  PDFPageProxy,
  PDFViewport,
  PDFRenderTask,
  PDFTextContent,
  PdfLoaderProps,
};

export default PdfLoader;
