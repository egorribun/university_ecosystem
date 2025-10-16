import axios, {
  AxiosHeaders,
  type AxiosInstance,
  type AxiosRequestConfig,
  type AxiosResponse,
} from "axios";
import i18n from "@/i18n/config";

export const API_UNAUTHORIZED_EVENT = "auth:unauthorized";
export const SKIP_UNAUTHORIZED_HEADER = "X-Client-Skip-Unauthorized";

const devBase = "/api";
const prodBase = import.meta.env.VITE_BACKEND_ORIGIN || "/api";

export type ApiRequestConfig<D = unknown> = AxiosRequestConfig<D> & {
  signal?: AbortSignal
};

type ApiInstance = Omit<AxiosInstance, "get" | "delete" | "post" | "patch" | "put"> & {
  get<T = unknown, R = AxiosResponse<T>, D = unknown>(url: string, config?: ApiRequestConfig<D>): Promise<R>;
  delete<T = unknown, R = AxiosResponse<T>, D = unknown>(url: string, config?: ApiRequestConfig<D>): Promise<R>;
  post<T = unknown, R = AxiosResponse<T>, D = unknown>(
    url: string,
    data?: D,
    config?: ApiRequestConfig<D>
  ): Promise<R>;
  patch<T = unknown, R = AxiosResponse<T>, D = unknown>(
    url: string,
    data?: D,
    config?: ApiRequestConfig<D>
  ): Promise<R>;
  put<T = unknown, R = AxiosResponse<T>, D = unknown>(
    url: string,
    data?: D,
    config?: ApiRequestConfig<D>
  ): Promise<R>;
};

const api: ApiInstance = axios.create({
  baseURL: import.meta.env.DEV ? devBase : prodBase,
  withCredentials: true,
  timeout: 8000,
  xsrfCookieName: "XSRF-TOKEN",
  xsrfHeaderName: "X-XSRF-TOKEN",
  headers: {
    Accept: "application/json",
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest",
  },
}) as ApiInstance;

const acceptLanguageHeader = "Accept-Language";

const resolveAcceptLanguage = (language?: string) => {
  if (!language) return "ru";
  const normalized = language.toLowerCase();
  if (normalized.startsWith("en")) return "en";
  if (normalized.startsWith("ru")) return "ru";
  return "ru";
};

api.interceptors.request.use((config) => {
  const currentLanguage = i18n.language || i18n.resolvedLanguage || "ru";
  const headerValue = resolveAcceptLanguage(currentLanguage);

  if (config.headers instanceof AxiosHeaders) {
    if (!config.headers.has(acceptLanguageHeader)) {
      config.headers.set(acceptLanguageHeader, headerValue);
    }
    return config;
  }

  const headers = (config.headers ?? {}) as Record<string, unknown>;
  const existing = headers[acceptLanguageHeader] ?? headers[acceptLanguageHeader.toLowerCase()];

  if (existing == null) {
    config.headers = { ...headers, [acceptLanguageHeader]: headerValue };
  }

  return config;
});

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err?.response?.status === 401) {
      const headers = (err.config?.headers ?? {}) as Record<string, unknown>;
      if (headers[SKIP_UNAUTHORIZED_HEADER]) {
        delete headers[SKIP_UNAUTHORIZED_HEADER];
        return Promise.reject(err);
      }
      if (typeof window !== "undefined") {
        window.dispatchEvent(new CustomEvent(API_UNAUTHORIZED_EVENT));
      }
    }
    return Promise.reject(err);
  }
);

export default api;
