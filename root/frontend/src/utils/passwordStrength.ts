import type { ZxcvbnResult } from "@zxcvbn-ts/core"

type ZxcvbnFn = (password: string, userInputs?: (string | number)[]) => ZxcvbnResult

let loader: Promise<ZxcvbnFn> | null = null

const COMMON_PASSWORDS = [
  "123456",
  "123456789",
  "qwerty",
  "password",
  "111111",
  "12345678",
  "abc123",
  "1234567",
  "12345",
  "iloveyou",
  "000000",
  "123123",
  "qwerty123",
  "1q2w3e4r",
  "admin",
  "letmein",
  "welcome",
  "monkey",
  "dragon",
  "football",
]

const COMMON_WORDS = [
  "university",
  "password",
  "welcome",
  "student",
  "teacher",
  "login",
  "service",
  "profile",
  "schedule",
  "guu",
  "moscow",
  "guu2024",
]

const translations = {
  warnings: {
    straightRow: "Пароль содержит последовательность клавиатуры.",
    keyPattern: "Пароль содержит очевидный шаблон клавиатуры.",
    simpleRepeat: "Пароль состоит из повторяющихся символов.",
    extendedRepeat: "Пароль состоит из повторяющихся последовательностей.",
    sequences: "Пароль содержит последовательности символов.",
    recentYears: "Использование года легко угадать.",
    dates: "Даты легко угадываются.",
    topTen: "Пароль входит в топ-10 самых популярных.",
    topHundred: "Пароль входит в топ-100 самых популярных.",
    common: "Очень распространённый пароль.",
    similarToCommon: "Пароль похож на распространённый.",
    wordByItself: "Использовано одно слово без модификаций.",
    namesByThemselves: "Имена сами по себе легко угадываются.",
    commonNames: "Распространённые имена легко угадываются.",
    userInputs: "Пароль содержит ваши данные.",
    pwned: "Пароль найден в утечках.",
  },
  suggestions: {
    l33t: "Изменения букв на похожие символы не помогают.",
    reverseWords: "Перестановка букв не усложняет пароль.",
    allUppercase: "Добавьте строчные буквы.",
    capitalization: "Используйте смешанный регистр.",
    dates: "Избегайте дат и годов.",
    recentYears: "Избегайте недавних годов.",
    associatedYears: "Не используйте связанные с вами годы.",
    sequences: "Избегайте последовательностей.",
    repeated: "Избегайте повторяющихся символов.",
    longerKeyboardPattern: "Усложните шаблон на клавиатуре.",
    anotherWord: "Добавьте больше уникальных слов.",
    useWords: "Используйте несколько случайных слов.",
    noNeed: "Не добавляйте спецсимволы только в конце.",
    pwned: "Используйте иной пароль, не встречавшийся в утечках.",
  },
  timeEstimation: {
    ltSecond: "меньше секунды",
    second: "секунда",
    seconds: "секунды",
    minute: "минута",
    minutes: "минут",
    hour: "час",
    hours: "часов",
    day: "день",
    days: "дней",
    month: "месяц",
    months: "месяцев",
    year: "год",
    years: "лет",
    centuries: "века",
  },
}

const createLoader = async (): Promise<ZxcvbnFn> => {
  const { zxcvbn, zxcvbnOptions } = await import("@zxcvbn-ts/core")

  zxcvbnOptions.setOptions({
    dictionary: {
      passwords: COMMON_PASSWORDS,
      commonWords: COMMON_WORDS,
    },
    translations,
  })

  return zxcvbn
}

const getLoader = () => {
  if (!loader) {
    loader = createLoader()
  }
  return loader
}

export const evaluatePasswordStrength = async (
  password: string,
  userInputs?: (string | number)[]
): Promise<ZxcvbnResult> => {
  const evaluate = await getLoader()
  return evaluate(password, userInputs)
}

export type { ZxcvbnResult as PasswordStrengthResult }
