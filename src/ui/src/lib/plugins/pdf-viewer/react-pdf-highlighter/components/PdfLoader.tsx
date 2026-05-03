import { GlobalWorkerOptions, getDocument } from "pdfjs-dist";
import type { PDFDocumentProxy } from "pdfjs-dist";
import React, { Component } from "react";
import {
  PDF_CMAP_PACKED,
  PDF_CMAP_URL,
  PDF_WORKER_SRC,
} from "../../lib/pdf-utils";

interface Props {
  /** See `GlobalWorkerOptionsType`. */
  workerSrc: string;

  url: string;
  httpHeaders?: Record<string, string>;
  beforeLoad: JSX.Element;
  errorMessage?: JSX.Element;
  children: (pdfDocument: PDFDocumentProxy) => JSX.Element;
  onError?: (error: Error) => void;
  cMapUrl?: string;
  cMapPacked?: boolean;
}

interface State {
  pdfDocument: PDFDocumentProxy | null;
  error: Error | null;
}

type PdfDocumentLoadingTask = ReturnType<typeof getDocument>;

export class PdfLoader extends Component<Props, State> {
  state: State = {
    pdfDocument: null,
    error: null,
  };

  static defaultProps = {
    workerSrc: PDF_WORKER_SRC,
    cMapUrl: PDF_CMAP_URL,
    cMapPacked: PDF_CMAP_PACKED,
  };

  documentRef = React.createRef<HTMLElement>();
  private loadingTask: PdfDocumentLoadingTask | null = null;
  private loadGeneration = 0;

  componentDidMount() {
    this.load();
  }

  componentWillUnmount() {
    this.loadGeneration += 1;
    this.destroyLoadingTask();
    const { pdfDocument: discardedDocument } = this.state;
    if (discardedDocument) {
      discardedDocument.destroy();
    }
  }

  componentDidUpdate({ url }: Props) {
    if (this.props.url !== url) {
      this.load();
    }
  }

  componentDidCatch(error: Error) {
    const { onError } = this.props;

    if (onError) {
      onError(error);
    }

    this.setState({ pdfDocument: null, error });
  }

  destroyLoadingTask() {
    if (!this.loadingTask) return;
    const task = this.loadingTask;
    this.loadingTask = null;
    try {
      void task.destroy();
    } catch {
      // Ignore cleanup errors.
    }
  }

  load() {
    const { ownerDocument = document } = this.documentRef.current || {};
    const { url, cMapUrl, cMapPacked, workerSrc } = this.props;
    const { pdfDocument: discardedDocument } = this.state;
    const generation = this.loadGeneration + 1;
    this.loadGeneration = generation;
    this.destroyLoadingTask();
    this.setState({ pdfDocument: null, error: null });

    if (typeof workerSrc === "string") {
      GlobalWorkerOptions.workerSrc = workerSrc;
    }

    Promise.resolve()
      .then(() => discardedDocument?.destroy())
      .then(() => {
        if (!url) {
          return;
        }

        const document = {
          ...this.props,
          ownerDocument,
          ...(cMapUrl
            ? {
                cMapUrl,
                cMapPacked,
              }
            : {}),
          };

        const loadingTask = getDocument(document);
        this.loadingTask = loadingTask;
        return loadingTask.promise.then((pdfDocument) => {
          if (this.loadGeneration !== generation) {
            pdfDocument.destroy();
            return;
          }
          this.loadingTask = null;
          this.setState({ pdfDocument });
        });
      })
      .catch((e) => {
        if (this.loadGeneration !== generation) return;
        this.loadingTask = null;
        this.componentDidCatch(e);
      });
  }

  render() {
    const { children, beforeLoad } = this.props;
    const { pdfDocument, error } = this.state;
    return (
      <>
        <span ref={this.documentRef} />
        {error
          ? this.renderError()
          : !pdfDocument || !children
            ? beforeLoad
            : children(pdfDocument)}
      </>
    );
  }

  renderError() {
    const { errorMessage } = this.props;
    if (errorMessage) {
      return React.cloneElement(errorMessage, { error: this.state.error });
    }

    return null;
  }
}
