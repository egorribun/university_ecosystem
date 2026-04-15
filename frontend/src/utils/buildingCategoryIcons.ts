import {
  BookOpen,
  Building2,
  Dumbbell,
  Home,
  GraduationCap,
  UtensilsCrossed,
  type LucideIcon,
} from "lucide-react"
import type { MapCategory } from "@/data/campusBuildings"

const CATEGORY_ICONS: Record<string, LucideIcon> = {
  study: BookOpen,
  food: UtensilsCrossed,
  services: Building2,
  sports: Dumbbell,
  housing: Home,
  events: GraduationCap,
}

export function getPrimaryIcon(tags: MapCategory[]): LucideIcon {
  for (const tag of tags) {
    if (CATEGORY_ICONS[tag]) return CATEGORY_ICONS[tag]
  }
  return Building2
}
