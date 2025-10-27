type ClassValue =
  | string
  | number
  | null
  | false
  | undefined
  | ClassDictionary
  | ClassArray

interface ClassDictionary {
  [id: string]: boolean | null | undefined
}

type ClassArray = ClassValue[]

const toVal = (mix: ClassValue): string => {
  if (typeof mix === "string" || typeof mix === "number") {
    return String(mix)
  }

  if (Array.isArray(mix)) {
    return mix.map(toVal).filter(Boolean).join(" ")
  }

  if (mix && typeof mix === "object") {
    return Object.entries(mix)
      .filter(([, value]) => Boolean(value))
      .map(([key]) => key)
      .join(" ")
  }

  return ""
}

export function cn(...inputs: ClassValue[]): string {
  return inputs.map(toVal).filter(Boolean).join(" ")
}

