import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react"
import type { AxiosError } from "axios"
import api from "../api/axios"

type AuthContextType = {
  isAuth: boolean
  login: (token: string) => Promise<void>
  logout: () => void
  user: any
  loading: boolean
  setUser: (user: any) => void
}

export const AuthContext = createContext<AuthContextType>({
  isAuth: false,
  login: async () => {},
  logout: () => {},
  user: null,
  loading: false,
  setUser: () => {},
})

export const useAuth = () => useContext(AuthContext)

const PROFILE_CACHE_KEY = "ecosystem.profile.cache.v1"

const readCachedUser = () => {
  try {
    const raw = localStorage.getItem(PROFILE_CACHE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (parsed && typeof parsed === "object" && "data" in parsed) {
      return (parsed as { data: unknown }).data
    }
    return parsed
  } catch {
    return null
  }
}

const persistUserToCache = (value: any) => {
  try {
    if (value) {
      localStorage.setItem(
        PROFILE_CACHE_KEY,
        JSON.stringify({ data: value, savedAt: new Date().toISOString() })
      )
    } else {
      localStorage.removeItem(PROFILE_CACHE_KEY)
    }
  } catch {
    /* ignore */
  }
}

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const [user, setUserState] = useState<any>(() => readCachedUser())
  const [loading, setLoading] = useState(true)
  const [isAuth, setIsAuth] = useState<boolean>(() => {
    try {
      return !!localStorage.getItem("token")
    } catch {
      return false
    }
  })

  const setUser = useCallback(
    (value: any) => {
      setUserState((prev) => {
        const next = typeof value === "function" ? value(prev) : value
        persistUserToCache(next)
        return next
      })
    },
    []
  )

  const applyToken = (token?: string | null) => {
    if (token) {
      try {
        localStorage.setItem("token", token)
      } catch {}
      api.defaults.headers.common["Authorization"] = `Bearer ${token}`
    } else {
      try {
        localStorage.removeItem("token")
      } catch {}
      delete api.defaults.headers.common["Authorization"]
    }
  }

  const fetchMe = async () => {
    try {
      const res = await api.get("/users/me")
      setUser(res.data)
      setIsAuth(true)
      return res.data
    } catch (error) {
      const status = (error as AxiosError | undefined)?.response?.status
      if (status === 401) {
        setUser(null)
        setIsAuth(false)
        return null
      }

      const cached = readCachedUser()
      if (cached) {
        setUser(cached)
        let tokenExists = true
        try {
          tokenExists = !!localStorage.getItem("token")
        } catch {
          tokenExists = true
        }
        setIsAuth(tokenExists)
        return cached
      }

      setIsAuth(false)
      setUser(null)
      return null
    }
  }

  useEffect(() => {
    let token: string | null = null
    try {
      token = localStorage.getItem("token")
    } catch {}
    if (token) api.defaults.headers.common["Authorization"] = `Bearer ${token}`
    fetchMe().finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === "token") {
        const t = localStorage.getItem("token")
        if (t) {
          api.defaults.headers.common["Authorization"] = `Bearer ${t}`
          fetchMe()
        } else {
          delete api.defaults.headers.common["Authorization"]
          setUser(null)
          setIsAuth(false)
        }
      }
    }
    window.addEventListener("storage", onStorage)
    return () => window.removeEventListener("storage", onStorage)
  }, [])

  const login = async (token: string) => {
    applyToken(token)
    setLoading(true)
    await fetchMe()
    setLoading(false)
  }

  const logout = () => {
    applyToken(null)
    setUser(null)
    setIsAuth(false)
  }

  const value = useMemo(
    () => ({ isAuth, login, logout, user, loading, setUser }),
    [isAuth, login, logout, user, loading, setUser]
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}