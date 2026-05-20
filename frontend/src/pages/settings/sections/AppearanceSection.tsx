import { useCallback, type ChangeEvent } from "react"
import { useTranslation } from "react-i18next"
import { Moon, Sun, Monitor } from "lucide-react"

import { useLanguage, type SupportedLanguage } from "@/contexts/LanguageContext"
import { useTheme } from "@/contexts/ThemeContext"

import {
  RadioGroup,
  Radio,
  FormControlLabel,
  SectionCard,
  SectionTitle,
  SectionSubtitle,
  AccordionSection,
  type ThemeMode,
} from "@/components/settings"

import type { SettingsSectionProps } from "@/pages/settings/types"

export function AppearanceSection(_props: SettingsSectionProps) {
  const { t } = useTranslation(["settings", "common"])
  const { language, setLanguage, available: availableLanguages } = useLanguage()
  const { theme, setTheme, resolvedTheme: resolvedColorScheme } = useTheme()

  const handleThemeChange = useCallback(
    (_: ChangeEvent<HTMLInputElement> | null, value: string) => {
      setTheme(value as ThemeMode)
    },
    [setTheme]
  )

  const handleLanguageChange = useCallback(
    (_: ChangeEvent<HTMLInputElement> | null, value: string) => {
      setLanguage(value as SupportedLanguage)
    },
    [setLanguage]
  )

  const themeOptions: { value: ThemeMode; label: string; icon: typeof Moon }[] = [
    { value: "light", label: t("settings:appearance.theme.options.light"), icon: Sun },
    { value: "dark", label: t("settings:appearance.theme.options.dark"), icon: Moon },
    { value: "system", label: t("settings:appearance.theme.options.system"), icon: Monitor },
  ]

  return (
    <div className="flex w-full flex-col gap-5 sm:gap-6 xl:max-w-(--layout-max-content)">
      <SectionCard component="section">
        <div className="flex flex-col gap-2 mb-4">
          <SectionTitle variant="subtitle1">{t("settings:appearance.title")}</SectionTitle>
          <SectionSubtitle variant="body2">{t("settings:appearance.subtitle")}</SectionSubtitle>
        </div>

        <ul className="flex flex-col gap-3 list-none m-0 p-0">
          <li className="list-none">
            <AccordionSection
              title={t("settings:appearance.language.title")}
              subtitle={t("settings:appearance.language.subtitle")}
            >
              <RadioGroup
                name="language"
                value={language}
                onChange={handleLanguageChange}
                className="flex flex-col gap-1.5"
              >
                {availableLanguages.map((code) => (
                  <FormControlLabel
                    key={code}
                    value={code}
                    control={<Radio />}
                    label={t(`settings:appearance.language.options.${code}`)}
                  />
                ))}
              </RadioGroup>
            </AccordionSection>
          </li>

          <li className="list-none">
            <AccordionSection
              title={t("settings:appearance.theme.title")}
              subtitle={t("settings:appearance.theme.subtitle")}
            >
              <RadioGroup
                name="theme"
                value={theme}
                onChange={handleThemeChange}
                className="flex flex-col gap-1.5"
              >
                {themeOptions.map((option) => (
                  <FormControlLabel
                    key={option.value}
                    value={option.value}
                    control={<Radio />}
                    label={
                      <span className="flex items-center gap-2">
                        <option.icon className="w-4 h-4" />
                        {option.label}
                      </span>
                    }
                  />
                ))}
              </RadioGroup>
              {theme === "system" && (
                <p className="mt-2 text-xs text-text-muted">
                  {t("settings:appearance.theme.systemHint", {
                    value: t(`settings:appearance.theme.hintOptions.${resolvedColorScheme}`),
                  })}
                </p>
              )}
            </AccordionSection>
          </li>
        </ul>
      </SectionCard>
    </div>
  )
}
