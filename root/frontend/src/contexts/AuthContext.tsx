import { createContext, useContext, useEffect, useMemo, useState, ReactNode } from "react"
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

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const [user, setUser] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [isAuth, setIsAuth] = useState<boolean>(!!localStorage.getItem("token"))

  const applyToken = (token?: string | null) => {
    if (token) {
      localStorage.setItem("token", token)
      api.defaults.headers.common["Authorization"] = `Bearer ${token}`
    } else {
      localStorage.removeItem("token")
      delete api.defaults.headers.common["Authorization"]
    }
  }

  const fetchMe = async () => {
    try {
      const res = await api.get("/users/me")
      setUser(res.data)
      setIsAuth(true)
      return res.data
    } catch {
      setUser(null)
      setIsAuth(false)
      return null
    }
  }

  useEffect(() => {
    const token = localStorage.getItem("token")
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

  const value = useMemo(() => ({ isAuth, login, logout, user, loading, setUser }), [isAuth, user, loading])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}