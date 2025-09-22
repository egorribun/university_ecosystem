import axios from "@/api/axios"

export async function fetchNotifications(limit = 20, offset = 0) {
  const r = await axios.get("/notifications", { params: { limit, offset } })
  return r.data
}

export async function markRead(id: number) {
  await axios.post("/notifications/mark-read", { id })
}

export async function markAllRead() {
  await axios.post("/notifications/mark-all-read", {})
}