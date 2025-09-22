import axios from "axios";

const devBase = "/api";
const prodBase = import.meta.env.VITE_BACKEND_ORIGIN || "/api";

const api = axios.create({
  baseURL: import.meta.env.DEV ? devBase : prodBase,
  withCredentials: true,
  xsrfCookieName: "XSRF-TOKEN",
  xsrfHeaderName: "X-XSRF-TOKEN",
  headers: {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest"
  }
});

export function setAuthToken(token?: string) {
  if (token) {
    try { localStorage.setItem("token", token); } catch {}
    api.defaults.headers.common.Authorization = `Bearer ${token}`;
  } else {
    try { localStorage.removeItem("token"); } catch {}
    delete api.defaults.headers.common.Authorization;
  }
}

api.interceptors.request.use(
  (config) => {
    const token = typeof localStorage !== "undefined" ? localStorage.getItem("token") : null;
    if (token) {
      config.headers = config.headers || {};
      (config.headers as any).Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err?.response?.status === 401) {
      setAuthToken(undefined);
    }
    return Promise.reject(err);
  }
);

export default api;