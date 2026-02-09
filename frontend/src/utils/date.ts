import dayjs from "dayjs"
import utc from "dayjs/plugin/utc"
import timezone from "dayjs/plugin/timezone"
import "dayjs/locale/ru"

dayjs.extend(utc)
dayjs.extend(timezone)

export const normalizeDate = (d?: string) => (d ? d.replace("T", " ").replace("Z", "") : "")

export const getMoscowDate = (dateStr: string) => {
  let parsed = dayjs(dateStr)
  if (!/([Zz]|[+\-]\d\d:?\d\d)$/.test(dateStr)) parsed = dayjs.utc(dateStr)
  return parsed.tz("Europe/Moscow").format("DD.MM.YYYY HH:mm")
}

export const formatLocalDateTime = (dateStr?: string) => {
  if (!dateStr) return ""
  return dayjs(normalizeDate(dateStr).replace(" ", "T")).format("DD.MM.YYYY HH:mm")
}




