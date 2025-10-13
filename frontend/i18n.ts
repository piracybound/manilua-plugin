import en from "../locales/en.json";
import es from "../locales/es.json";
import ptBR from "../locales/pt-BR.json";
import fr from "../locales/fr.json";
import it from "../locales/it.json";

type TranslationMap = Record<string, any>;

const FALLBACK_LOCALE = "en";
const STATIC_TRANSLATIONS: Record<string, TranslationMap> = {
  en,
  es,
  "pt-BR": ptBR,
  fr,
  it,
};

function normaliseLocale(locale: string | undefined | null): string {
  if (!locale || typeof locale !== "string") {
    return FALLBACK_LOCALE;
  }

  const lower = locale.toLowerCase();

  if (lower === "pt-br" || lower === "pt_br") return "pt-BR";
  if (lower.startsWith("en")) return "en";
  if (lower.startsWith("es")) return "es";

  const base = lower.split(/[-_]/)[0];
  const mapped = Object.keys(STATIC_TRANSLATIONS).find(
    (code) => code.toLowerCase() === base
  );
  return mapped ?? FALLBACK_LOCALE;
}

class I18n {
  private translations = new Map<string, TranslationMap>();
  private currentLocale = FALLBACK_LOCALE;
  private initialised = false;
  private initPromise: Promise<void> | null = null;

  async init(): Promise<void> {
    if (this.initialised) {
      return;
    }

    if (!this.initPromise) {
      this.initPromise = this.bootstrap();
    }

    await this.initPromise;
    this.initialised = true;
  }

  t(key: string, vars?: Record<string, string | number>): string {
    const value =
      this.lookup(this.currentLocale, key) ??
      this.lookup(FALLBACK_LOCALE, key) ??
      key;

    if (typeof value !== "string") {
      return key;
    }

    if (!vars) {
      return value;
    }

    return value.replace(/\{(.*?)\}/g, (_, token: string) => {
      const replacement = vars[token.trim()];
      return replacement === undefined || replacement === null
        ? ""
        : String(replacement);
    });
  }

  private async bootstrap(): Promise<void> {
    const preferredLocale = normaliseLocale(
      navigator.language || (navigator as any).userLanguage || FALLBACK_LOCALE
    );

    this.loadLocale(preferredLocale);
    if (
      !this.translations.has(preferredLocale) &&
      preferredLocale !== FALLBACK_LOCALE
    ) {
      this.loadLocale(FALLBACK_LOCALE);
      this.currentLocale = FALLBACK_LOCALE;
      return;
    }

    this.currentLocale = preferredLocale;
  }

  private loadLocale(locale: string): void {
    if (this.translations.has(locale)) {
      return;
    }

    const data = STATIC_TRANSLATIONS[locale];
    if (data) {
      this.translations.set(locale, data);
    }
  }

  private lookup(locale: string, key: string): string | undefined {
    const translations = this.translations.get(locale);
    if (!translations) {
      return undefined;
    }

    return key.split(".").reduce<any>((value, segment) => {
      if (value && typeof value === "object") {
        return value[segment];
      }
      return undefined;
    }, translations);
  }
}

const i18nInstance = new I18n();

export async function initI18n(): Promise<void> {
  await i18nInstance.init();
}

export function t(key: string, vars?: Record<string, string | number>): string {
  return i18nInstance.t(key, vars);
}
