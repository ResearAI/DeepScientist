import axios, { type AxiosError, type AxiosRequestConfig } from "axios";
import { toast } from "@/components/ui/toast";
import { redactSensitive, sanitizeUrl, truncateText } from "@/lib/bugbash/sanitize";
import { recordRequestEvent } from "@/lib/bugbash/repro-recorder";
import { handleUnauthorizedAuth, readRequestAuthContext } from "@/lib/auth";

/**
 * Resolve API base URL from environment or default configuration.
 * This is the single source of truth for API URL - all other files should import this.
 *
 * Priority:
 * 1. NEXT_PUBLIC_API_URL environment variable (from .env)
 * 2. Default backend URL
 *
 * @returns The API base URL without trailing slash
 */
export function resolveApiBaseUrl(): string {
  const env = import.meta.env as Record<string, string | undefined>
  const configured = env.VITE_API_URL || env.NEXT_PUBLIC_API_URL
  const windowLocation = typeof window !== 'undefined' ? window.location : null
  const sameOriginBaseUrl = windowLocation?.origin || 'http://127.0.0.1:20999'

  // Local-first rule:
  // - in the browser, prefer the daemon that served the app
  // - allow explicit override via VITE_API_URL / NEXT_PUBLIC_API_URL
  // - outside the browser, default to the local daemon address
  let base = configured || sameOriginBaseUrl

  if (typeof window !== "undefined") {
    try {
      // Support protocol-relative env values like //example.com:8080
      if (base.startsWith("//")) {
        base = `${window.location.protocol}${base}`
      }
    } catch {
      // If base isn't a valid URL, keep it as-is.
    }
  }

  return base.replace(/\/$/, '')
}

const DEFAULT_REQUEST_TIMEOUT_MS = 40000;
const DEFAULT_UPLOAD_TIMEOUT_MS = 4 * 60 * 1000;

type DsAxiosConfig = AxiosRequestConfig & {
  __dsRequestStartedAt?: number;
  __dsSkipErrorToast?: boolean;
  __dsErrorToastShown?: boolean;
};

const resolveRequestUrl = (config?: AxiosRequestConfig) => {
  if (!config) return "";
  try {
    return apiClient.getUri(config);
  } catch {
    return config.url || "";
  }
};

const buildErrorDetails = (error: AxiosError, config?: AxiosRequestConfig) => {
  const method = (config?.method || "GET").toString().toUpperCase();
  const url = sanitizeUrl(resolveRequestUrl(config));
  const status = error.response?.status;
  const code = error.code;
  const message = error.message ? redactSensitive(error.message) : "";
  const parts = [
    `Method: ${method}`,
    `URL: ${url}`,
    status ? `Status: ${status}` : null,
    code ? `Code: ${code}` : null,
    message ? `Message: ${message}` : null,
  ].filter(Boolean) as string[];
  return parts.length ? truncateText(parts.join("\n"), 2000) : undefined;
};

const shouldShowRetryToast = (error: AxiosError) => {
  const status = error.response?.status;
  const isTimeout =
    error.code === "ECONNABORTED" ||
    (typeof error.message === "string" && error.message.toLowerCase().includes("timeout"));
  const isNetwork = !error.response;
  const isServerError = typeof status === "number" && status >= 500;
  return { isTimeout, isNetwork, isServerError };
};

const buildRetryAction = (config?: AxiosRequestConfig) => {
  if (!config) return undefined;
  const method = (config.method || "GET").toString().toUpperCase();
  const url = sanitizeUrl(resolveRequestUrl(config));
  const nextConfig: DsAxiosConfig = {
    ...config,
    headers: { ...config.headers },
    __dsSkipErrorToast: true,
  };
  return {
    label: "Retry",
    ariaLabel: `Retry ${method} ${url}`,
    onClick: async () => {
      try {
        await apiClient.request(nextConfig);
        toast({
          type: "success",
          title: "Retry succeeded",
          description: `${method} ${url}`,
        });
      } catch (retryError) {
        const retryMessage =
          retryError instanceof Error
            ? redactSensitive(retryError.message)
            : "Request failed again.";
        toast({
          type: "error",
          title: "Retry failed",
          description: retryMessage,
          details:
            retryError && typeof retryError === "object"
              ? buildErrorDetails(retryError as AxiosError, nextConfig)
              : undefined,
        });
      }
    },
  };
};

export const apiClient = axios.create({
  baseURL: resolveApiBaseUrl(),
  headers: {
    "Content-Type": "application/json",
  },
  withCredentials: true,
  timeout: DEFAULT_REQUEST_TIMEOUT_MS,
});

export function getApiBaseUrl(): string {
  return apiClient.defaults.baseURL || resolveApiBaseUrl();
}

// Request interceptor - add auth token
apiClient.interceptors.request.use((config) => {
  const dsConfig = config as DsAxiosConfig;
  dsConfig.__dsRequestStartedAt = Date.now();
  if (typeof FormData !== "undefined" && config.data instanceof FormData) {
    const headers = config.headers ?? {};
    if (headers && typeof headers === "object") {
      delete (headers as Record<string, string>)["Content-Type"];
      delete (headers as Record<string, string>)["content-type"];
    }
    config.headers = headers;

    // Keep upload requests more tolerant to larger PDF files.
    if (config.timeout == null || config.timeout === DEFAULT_REQUEST_TIMEOUT_MS) {
      config.timeout = DEFAULT_UPLOAD_TIMEOUT_MS;
    }
  }
  if (typeof window !== "undefined") {
    const { token } = readRequestAuthContext();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

// Response interceptor - handle 401 + network retries
apiClient.interceptors.response.use(
  (response) => {
    const config = response.config as DsAxiosConfig;
    const duration =
      typeof config.__dsRequestStartedAt === "number"
        ? Date.now() - config.__dsRequestStartedAt
        : undefined;
    recordRequestEvent({
      method: (config.method || "GET").toString().toUpperCase(),
      url: sanitizeUrl(resolveRequestUrl(config)),
      status: response.status,
      duration_ms: duration,
    });
    return response;
  },
  (error: AxiosError) => {
    const config = error.config as DsAxiosConfig | undefined;
    const duration =
      typeof config?.__dsRequestStartedAt === "number"
        ? Date.now() - config.__dsRequestStartedAt
        : undefined;
    recordRequestEvent({
      method: (config?.method || "GET").toString().toUpperCase(),
      url: sanitizeUrl(resolveRequestUrl(config)),
      status: error.response?.status,
      duration_ms: duration,
      error: redactSensitive(error.message || "request_failed"),
    });

    if (error.response?.status === 401) {
      if (typeof window !== "undefined") {
        const { mode } = readRequestAuthContext();
        if (mode !== "none") {
          handleUnauthorizedAuth(mode, "session_expired");
        }
      }
      return Promise.reject(error);
    }

    if (axios.isCancel(error) || error.code === "ERR_CANCELED") {
      return Promise.reject(error);
    }

    const dsConfig = config as DsAxiosConfig | undefined;
    const skipToast =
      Boolean(dsConfig?.__dsSkipErrorToast) ||
      Boolean((config?.headers as Record<string, unknown> | undefined)?.["x-skip-error-toast"]);
    const alreadyShown = Boolean(dsConfig?.__dsErrorToastShown);
    if (!skipToast && !alreadyShown) {
      if (dsConfig) dsConfig.__dsErrorToastShown = true;
      const { isTimeout, isNetwork, isServerError } = shouldShowRetryToast(error);
      const offline = typeof navigator !== "undefined" && !navigator.onLine;
      if (isTimeout || isNetwork || isServerError) {
        const title = isTimeout
          ? "Request timed out"
          : offline
            ? "You are offline"
            : isServerError
              ? "Server error"
              : "Network error";
        const description = isTimeout
          ? "The request took too long to respond."
          : offline
            ? "Reconnect to the internet and try again."
            : isServerError
              ? "The server returned an error response."
              : "Unable to reach the server.";
        toast({
          type: isTimeout ? "warning" : "error",
          title,
          description,
          details: buildErrorDetails(error, config),
          action: buildRetryAction(config),
          duration: 0,
        });
      }
    }

    return Promise.reject(error);
  }
);
