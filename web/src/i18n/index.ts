import es from "./es";
import en from "./en";

type DeepStrings<T> = { [K in keyof T]: T[K] extends string ? string : DeepStrings<T[K]> };

/** Shape of the message catalogue; es.ts is the reference. */
export type Messages = DeepStrings<typeof es>;
export type Lang = "es" | "en";

export const languages: readonly Lang[] = ["es", "en"];
/** Language names are shown in their own language, so they are not translated. */
export const languageNames: Record<Lang, string> = { es: "Español", en: "English" };

export const catalogues: Record<Lang, Messages> = { es, en };

/** Fills `{name}` placeholders of a message. */
export function format(template: string, vars: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (m, k: string) => (k in vars ? String(vars[k]) : m));
}
