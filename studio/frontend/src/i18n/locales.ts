// Locale registry — the languages MACU Studio ships. English is the bundled source
// of truth; every other locale is a lazy-loaded JSON catalog under ./locales/.
//
// `completeness` is the fraction of English keys present + valid in that catalog
// (1 = fully translated). The translation pipeline (scripts/i18n-translate.mjs)
// rewrites these numbers from its validator report; the Settings picker shows a
// "NN% translated" badge for anything < 1.

export interface LocaleMeta {
  code: string;
  nativeName: string;
  englishName: string;
  dir: "ltr" | "rtl";
  completeness: number;
}

const RTL = new Set(["ar", "he", "fa", "ur"]);

export function dirOf(code: string): "ltr" | "rtl" {
  return RTL.has(code) ? "rtl" : "ltr";
}

// Order: English first, then roughly by region. nativeName is how a speaker sees
// their own language (shown primary in the picker); englishName is the gloss.
export const LOCALES: LocaleMeta[] = [
  { code: "en", nativeName: "English", englishName: "English", dir: "ltr", completeness: 1 },
  // Required
  { code: "es", nativeName: "Español", englishName: "Spanish", dir: "ltr", completeness: 0.992 },
  { code: "hi", nativeName: "हिन्दी", englishName: "Hindi", dir: "ltr", completeness: 0.992 },
  { code: "uk", nativeName: "Українська", englishName: "Ukrainian", dir: "ltr", completeness: 0.992 },
  // Romance
  { code: "fr", nativeName: "Français", englishName: "French", dir: "ltr", completeness: 0.992 },
  { code: "it", nativeName: "Italiano", englishName: "Italian", dir: "ltr", completeness: 0.987 },
  { code: "pt-BR", nativeName: "Português (Brasil)", englishName: "Portuguese (Brazil)", dir: "ltr", completeness: 0.986 },
  { code: "ro", nativeName: "Română", englishName: "Romanian", dir: "ltr", completeness: 0.992 },
  { code: "ca", nativeName: "Català", englishName: "Catalan", dir: "ltr", completeness: 0.989 },
  // European
  { code: "de", nativeName: "Deutsch", englishName: "German", dir: "ltr", completeness: 0.992 },
  { code: "nl", nativeName: "Nederlands", englishName: "Dutch", dir: "ltr", completeness: 0.992 },
  { code: "pl", nativeName: "Polski", englishName: "Polish", dir: "ltr", completeness: 0.992 },
  { code: "cs", nativeName: "Čeština", englishName: "Czech", dir: "ltr", completeness: 0.992 },
  { code: "el", nativeName: "Ελληνικά", englishName: "Greek", dir: "ltr", completeness: 0.989 },
  { code: "sv", nativeName: "Svenska", englishName: "Swedish", dir: "ltr", completeness: 0.992 },
  { code: "da", nativeName: "Dansk", englishName: "Danish", dir: "ltr", completeness: 0.992 },
  { code: "nb", nativeName: "Norsk Bokmål", englishName: "Norwegian", dir: "ltr", completeness: 0.992 },
  { code: "fi", nativeName: "Suomi", englishName: "Finnish", dir: "ltr", completeness: 0.98 },
  { code: "hu", nativeName: "Magyar", englishName: "Hungarian", dir: "ltr", completeness: 0.99 },
  { code: "tr", nativeName: "Türkçe", englishName: "Turkish", dir: "ltr", completeness: 0.992 },
  // CJK + Korean
  { code: "zh-Hans", nativeName: "简体中文", englishName: "Chinese (Simplified)", dir: "ltr", completeness: 0.992 },
  { code: "zh-Hant", nativeName: "繁體中文", englishName: "Chinese (Traditional)", dir: "ltr", completeness: 0.992 },
  { code: "ja", nativeName: "日本語", englishName: "Japanese", dir: "ltr", completeness: 0.991 },
  { code: "ko", nativeName: "한국어", englishName: "Korean", dir: "ltr", completeness: 0.991 },
  // South-East Asian
  { code: "vi", nativeName: "Tiếng Việt", englishName: "Vietnamese", dir: "ltr", completeness: 0.99 },
  { code: "th", nativeName: "ไทย", englishName: "Thai", dir: "ltr", completeness: 0.992 },
  { code: "id", nativeName: "Bahasa Indonesia", englishName: "Indonesian", dir: "ltr", completeness: 0.992 },
  { code: "ms", nativeName: "Bahasa Melayu", englishName: "Malay", dir: "ltr", completeness: 0.992 },
  { code: "fil", nativeName: "Filipino", englishName: "Filipino", dir: "ltr", completeness: 0.992 },
  // Indian subcontinent
  { code: "bn", nativeName: "বাংলা", englishName: "Bengali", dir: "ltr", completeness: 0.992 },
  { code: "ta", nativeName: "தமிழ்", englishName: "Tamil", dir: "ltr", completeness: 0.991 },
  { code: "te", nativeName: "తెలుగు", englishName: "Telugu", dir: "ltr", completeness: 0.992 },
  { code: "mr", nativeName: "मराठी", englishName: "Marathi", dir: "ltr", completeness: 0.992 },
  { code: "gu", nativeName: "ગુજરાતી", englishName: "Gujarati", dir: "ltr", completeness: 0.992 },
  { code: "ur", nativeName: "اردو", englishName: "Urdu", dir: "rtl", completeness: 0.992 },
  { code: "pa", nativeName: "ਪੰਜਾਬੀ", englishName: "Punjabi", dir: "ltr", completeness: 0.992 },
  { code: "ml", nativeName: "മലയാളം", englishName: "Malayalam", dir: "ltr", completeness: 0.99 },
  { code: "kn", nativeName: "ಕನ್ನಡ", englishName: "Kannada", dir: "ltr", completeness: 0.991 },
  // Middle East (RTL)
  { code: "ar", nativeName: "العربية", englishName: "Arabic", dir: "rtl", completeness: 0.98 },
  { code: "he", nativeName: "עברית", englishName: "Hebrew", dir: "rtl", completeness: 0.991 },
  { code: "fa", nativeName: "فارسی", englishName: "Persian", dir: "rtl", completeness: 0.991 },
  // African
  { code: "sw", nativeName: "Kiswahili", englishName: "Swahili", dir: "ltr", completeness: 0.992 },
  { code: "am", nativeName: "አማርኛ", englishName: "Amharic", dir: "ltr", completeness: 0.992 },
  { code: "yo", nativeName: "Yorùbá", englishName: "Yoruba", dir: "ltr", completeness: 0.99 },
  { code: "ha", nativeName: "Hausa", englishName: "Hausa", dir: "ltr", completeness: 0.992 },
  { code: "zu", nativeName: "isiZulu", englishName: "Zulu", dir: "ltr", completeness: 0.992 },
  { code: "ig", nativeName: "Igbo", englishName: "Igbo", dir: "ltr", completeness: 0.991 },
  { code: "af", nativeName: "Afrikaans", englishName: "Afrikaans", dir: "ltr", completeness: 0.989 },
  { code: "so", nativeName: "Soomaali", englishName: "Somali", dir: "ltr", completeness: 0.992 },
];
