import { Badge } from "@/components/ui"
import { TrendingUp as TrendingUpIcon, TrendingDown as TrendingDownIcon } from "lucide-react"

export default function TrendChip({ value }: { value?: number }) {
  if (typeof value !== "number") return null

  return (
    <Badge
      size="xs"
      variant="outline"
      tone={value >= 0 ? "success" : "danger"}
      leadingIcon={
        value >= 0 ? (
          <TrendingUpIcon className="activity-trend-icon" />
        ) : (
          <TrendingDownIcon className="activity-trend-icon" />
        )
      }
      className="font-extrabold"
    >
      {`${value > 0 ? "+" : ""}${value.toFixed(1)}%`}
    </Badge>
  )
}
