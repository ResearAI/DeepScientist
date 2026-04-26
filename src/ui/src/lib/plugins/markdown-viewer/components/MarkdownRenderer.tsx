/**
 * Markdown Renderer Component
 *
 * Renders markdown content with:
 * - GFM (GitHub Flavored Markdown) support via remark-gfm
 * - Math formula support via remark-math + rehype-katex (KaTeX)
 * - Syntax highlighted code blocks (styling)
 * - Custom styling for tables, blockquotes, lists, etc.
 */

"use client";

import React from "react";
import type { Components } from "react-markdown";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import rehypeRaw from "rehype-raw";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import { normalizeHeadingText, slugifyHeading } from "@/lib/docs/markdown";
import {
  buildQuestDocumentAssetUrl,
  getQuestMarkdownContextFromFileId,
  type QuestMarkdownContext,
  resolveQuestMarkdownAssetUrl,
} from "@/lib/markdown/quest-assets";
import { cn } from "@/lib/utils";

// ============================================================
// Types
// ============================================================

interface MarkdownRendererProps {
  content: string;
  className?: string;
  questContext?: QuestMarkdownContext | null;
}

type MarkdownLiProps = React.HTMLAttributes<HTMLLIElement> & {
  checked?: boolean;
  ordered?: boolean;
};

type MarkdownCodeProps = React.HTMLAttributes<HTMLElement> & {
  inline?: boolean;
};

const SAFE_LINK_PROTOCOLS = new Set(["http", "https", "mailto", "tel", "sms"]);
const SAFE_IMAGE_PROTOCOLS = new Set(["http", "https"]);
const INTERNAL_PROTOCOL_PREFIXES = ["dsfile://", "ds://file/"];
const BLOCKED_HTML_TAGS = new Set(["script", "style", "iframe", "object", "embed", "link", "meta", "base"]);

function sanitizeUrl(raw: string, allowedProtocols: Set<string>): string | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const lowered = trimmed.toLowerCase();
  if (INTERNAL_PROTOCOL_PREFIXES.some((prefix) => lowered.startsWith(prefix))) {
    return trimmed;
  }
  if (trimmed.startsWith("#")) return trimmed;
  if (trimmed.startsWith("/") || trimmed.startsWith("./") || trimmed.startsWith("../")) {
    return trimmed;
  }
  if (!trimmed.includes(":") && !trimmed.startsWith("//")) {
    return trimmed;
  }
  try {
    const parsed = new URL(trimmed);
    const protocol = parsed.protocol.replace(":", "").toLowerCase();
    if (allowedProtocols.has(protocol)) {
      return trimmed;
    }
  } catch {
    return null;
  }
  return null;
}

function sanitizeLinkUrl(value?: string | null): string | null {
  if (!value) return null;
  return sanitizeUrl(value, SAFE_LINK_PROTOCOLS);
}

function sanitizeImageUrl(value?: string | null): string | null {
  if (!value) return null;
  return sanitizeUrl(value, SAFE_IMAGE_PROTOCOLS);
}

// ============================================================
// React Markdown Components
// ============================================================

function parseDsFileSrc(src?: string | null): string | null {
  if (!src) return null;
  if (src.startsWith("dsfile://")) return src.slice("dsfile://".length);
  if (src.startsWith("ds://file/")) return src.slice("ds://file/".length);
  return null;
}

function MarkdownImage({
  src,
  alt,
  className,
  questContext,
  ...props
}: React.ImgHTMLAttributes<HTMLImageElement> & { questContext?: QuestMarkdownContext | null }) {
  const resolvedSrc = resolveQuestMarkdownAssetUrl(
    typeof src === "string" ? src : null,
    questContext
  );
  const safeSrc = sanitizeImageUrl(resolvedSrc);
  const fileId = parseDsFileSrc(safeSrc);
  const internalAssetUrl = React.useMemo(() => {
    if (!fileId) return null;
    const context = getQuestMarkdownContextFromFileId(fileId);
    if (context?.questId && context.baseDocumentId) {
      return buildQuestDocumentAssetUrl(context.questId, context.baseDocumentId);
    }
    return `/api/v1/files/${encodeURIComponent(fileId)}/content`;
  }, [fileId]);
  const [blobUrl, setBlobUrl] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    let activeUrl: string | null = null;

    setError(null);
    setBlobUrl(null);

    if (!fileId) {
      return () => {
        cancelled = true;
        if (activeUrl) URL.revokeObjectURL(activeUrl);
      };
    }

    (async () => {
      try {
        if (!internalAssetUrl) {
          throw new Error("Missing internal asset URL.");
        }
        const response = await fetch(internalAssetUrl);
        if (!response.ok) {
          throw new Error(`Failed to load image (${response.status}).`);
        }
        const nextUrl = URL.createObjectURL(await response.blob());
        if (cancelled) return;
        activeUrl = nextUrl;
        setBlobUrl(activeUrl);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Failed to load image");
      }
    })();

    return () => {
      cancelled = true;
      if (activeUrl) URL.revokeObjectURL(activeUrl);
    };
  }, [internalAssetUrl, fileId, safeSrc]);

  if (!safeSrc) {
    return (
      <span className={cn("text-xs text-muted-foreground", className)}>
        Image blocked{alt ? `: ${alt}` : ""}.
      </span>
    );
  }

  if (fileId) {
    if (error) {
      return (
        <span className={cn("text-xs text-muted-foreground", className)}>
          Image failed to load{alt ? `: ${alt}` : ""}.
        </span>
      );
    }
    return (
      <img
        {...props}
        src={blobUrl || undefined}
        alt={alt}
        className={className}
        loading="lazy"
      />
    );
  }

  return (
    <img
      {...props}
      src={safeSrc || undefined}
      alt={alt}
      className={className}
      loading="lazy"
    />
  );
}

function getNodeText(node: React.ReactNode): string {
  if (typeof node === "string" || typeof node === "number") {
    return String(node);
  }
  if (Array.isArray(node)) {
    return node.map(getNodeText).join(" ");
  }
  if (React.isValidElement(node)) {
    return getNodeText(node.props.children);
  }
  return "";
}

function buildMarkdownComponents(
  questContext?: QuestMarkdownContext | null
): Components {
  const headingIds = new Map<string, number>();

  const withHeadingId =
    (tag: "h1" | "h2" | "h3" | "h4" | "h5" | "h6", classNameToken: string) =>
    ({ className, children, ...props }: React.HTMLAttributes<HTMLHeadingElement>) => {
      const text = normalizeHeadingText(getNodeText(children));
      const base = slugifyHeading(text || tag);
      const count = (headingIds.get(base) ?? 0) + 1;
      headingIds.set(base, count);
      const id = count === 1 ? base : `${base}-${count}`;
      return React.createElement(tag, {
        ...props,
        id,
        className: cn(classNameToken, className),
        children,
      });
    };

  return {
    h1: withHeadingId("h1", "md-h1"),
    h2: withHeadingId("h2", "md-h2"),
    h3: withHeadingId("h3", "md-h3"),
    h4: withHeadingId("h4", "md-h4"),
    h5: withHeadingId("h5", "md-h5"),
    h6: withHeadingId("h6", "md-h6"),
    p: ({ className, ...props }) => (
      <p {...props} className={cn("md-p", className)} />
    ),
    a: ({ className, href, ...props }) => {
      const safeHref = typeof href === "string" ? sanitizeLinkUrl(href) : null;
      if (!safeHref) {
        return <span {...props} className={cn("md-link", className)} />;
      }
      const isExternal = /^https?:\/\//.test(safeHref);
      return (
        <a
          {...props}
          href={safeHref}
          className={cn("md-link", className)}
          target={isExternal ? "_blank" : undefined}
          rel={isExternal ? "noopener noreferrer" : undefined}
        />
      );
    },
    img: ({ className, src, ...props }) => (
      <MarkdownImage
        {...props}
        src={src}
        questContext={questContext}
        className={cn("md-image", className)}
      />
    ),
    blockquote: ({ className, ...props }) => (
      <blockquote {...props} className={cn("md-blockquote", className)} />
    ),
    ul: ({ className, ...props }) => {
      const isTaskList = className?.includes("contains-task-list");
      return (
        <ul
          {...props}
          className={cn(isTaskList ? "md-task-list" : "md-ul", className)}
        />
      );
    },
    ol: ({ className, ...props }) => (
      <ol {...props} className={cn("md-ol", className)} />
    ),
    li: ({ className, checked, ordered, ...props }: MarkdownLiProps) => {
      const isTask = typeof checked === "boolean";
      const baseClass = isTask ? "task-item" : ordered ? "md-li-ordered" : "md-li";
      return (
        <li
          {...props}
          className={cn(baseClass, isTask && checked && "checked", className)}
        />
      );
    },
    table: ({ className, ...props }) => (
      <table {...props} className={cn("md-table", className)} />
    ),
    tr: ({ className, ...props }) => (
      <tr {...props} className={cn("md-tr", className)} />
    ),
    td: ({ className, ...props }) => (
      <td {...props} className={cn("md-td", className)} />
    ),
    th: ({ className, ...props }) => (
      <th {...props} className={cn("md-td", "md-th", className)} />
    ),
    hr: ({ className, ...props }) => (
      <hr {...props} className={cn("md-hr", className)} />
    ),
    pre: ({ className, ...props }) => (
      <pre
        {...props}
        className={cn(
          "code-block !text-[#1f1b16] [&_code]:!text-[#1f1b16] dark:!text-[#1f1b16] dark:[&_code]:!text-[#1f1b16]",
          className
        )}
      />
    ),
    code: ({ className, inline, ...props }: MarkdownCodeProps) =>
      inline ? (
        <code {...props} className={cn("inline-code !text-[#1f1b16] dark:!text-[#1f1b16]", className)} />
      ) : (
        <code {...props} className={cn("!text-[#1f1b16] dark:!text-[#1f1b16]", className)} />
      ),
  };
}

// ============================================================
// Markdown Renderer Component
// ============================================================

export default function MarkdownRenderer({
  content,
  className,
  questContext,
}: MarkdownRendererProps) {
  const components = React.useMemo(
    () => buildMarkdownComponents(questContext),
    [content, questContext]
  );

  return (
    <ReactMarkdown
      className={cn("markdown-content", className)}
      remarkPlugins={[remarkGfm, remarkMath]}
      rehypePlugins={[rehypeRaw, rehypeKatex]}
      allowElement={(element) => {
        if (!("tagName" in element) || typeof element.tagName !== "string") {
          return true;
        }
        return !BLOCKED_HTML_TAGS.has(element.tagName.toLowerCase());
      }}
      components={components}
    >
      {content}
    </ReactMarkdown>
  );
}
