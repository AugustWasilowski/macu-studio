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
  { code: "es", nativeName: "Español", englishName: "Spanish", dir: "ltr", completeness: 1 },
  { code: "hi", nativeName: "हिन्दी", englishName: "Hindi", dir: "ltr", completeness: 1 },
  { code: "uk", nativeName: "Українська", englishName: "Ukrainian", dir: "ltr", completeness: 1 },
  // Romance
  { code: "fr", nativeName: "Français", englishName: "French", dir: "ltr", completeness: 1 },
  { code: "it", nativeName: "Italiano", englishName: "Italian", dir: "ltr", completeness: 0.994 },
  { code: "pt-BR", nativeName: "Português (Brasil)", englishName: "Portuguese (Brazil)", dir: "ltr", completeness: 0.993 },
  { code: "ro", nativeName: "Română", englishName: "Romanian", dir: "ltr", completeness: 1 },
  { code: "ca", nativeName: "Català", englishName: "Catalan", dir: "ltr", completeness: 0.996 },
  // European
  { code: "de", nativeName: "Deutsch", englishName: "German", dir: "ltr", completeness: 1 },
  { code: "nl", nativeName: "Nederlands", englishName: "Dutch", dir: "ltr", completeness: 1 },
  { code: "pl", nativeName: "Polski", englishName: "Polish", dir: "ltr", completeness: 1 },
  { code: "cs", nativeName: "Čeština", englishName: "Czech", dir: "ltr", completeness: 1 },
  { code: "el", nativeName: "Ελληνικά", englishName: "Greek", dir: "ltr", completeness: 0.996 },
  { code: "sv", nativeName: "Svenska", englishName: "Swedish", dir: "ltr", completeness: 1 },
  { code: "da", nativeName: "Dansk", englishName: "Danish", dir: "ltr", completeness: 1 },
  { code: "nb", nativeName: "Norsk Bokmål", englishName: "Norwegian", dir: "ltr", completeness: 1 },
  { code: "fi", nativeName: "Suomi", englishName: "Finnish", dir: "ltr", completeness: 0.985 },
  { code: "hu", nativeName: "Magyar", englishName: "Hungarian", dir: "ltr", completeness: 0.998 },
  { code: "tr", nativeName: "Türkçe", englishName: "Turkish", dir: "ltr", completeness: 1 },
  // CJK + Korean
  { code: "zh-Hans", nativeName: "简体中文", englishName: "Chinese (Simplified)", dir: "ltr", completeness: 1 },
  { code: "zh-Hant", nativeName: "繁體中文", englishName: "Chinese (Traditional)", dir: "ltr", completeness: 1 },
  { code: "ja", nativeName: "日本語", englishName: "Japanese", dir: "ltr", completeness: 0.999 },
  { code: "ko", nativeName: "한국어", englishName: "Korean", dir: "ltr", completeness: 0.999 },
  // South-East Asian
  { code: "vi", nativeName: "Tiếng Việt", englishName: "Vietnamese", dir: "ltr", completeness: 0.998 },
  { code: "th", nativeName: "ไทย", englishName: "Thai", dir: "ltr", completeness: 1 },
  { code: "id", nativeName: "Bahasa Indonesia", englishName: "Indonesian", dir: "ltr", completeness: 1 },
  { code: "ms", nativeName: "Bahasa Melayu", englishName: "Malay", dir: "ltr", completeness: 1 },
  { code: "fil", nativeName: "Filipino", englishName: "Filipino", dir: "ltr", completeness: 1 },
  // Indian subcontinent
  { code: "bn", nativeName: "বাংলা", englishName: "Bengali", dir: "ltr", completeness: 1 },
  { code: "ta", nativeName: "தமிழ்", englishName: "Tamil", dir: "ltr", completeness: 0.999 },
  { code: "te", nativeName: "తెలుగు", englishName: "Telugu", dir: "ltr", completeness: 1 },
  { code: "mr", nativeName: "मराठी", englishName: "Marathi", dir: "ltr", completeness: 1 },
  { code: "gu", nativeName: "ગુજરાતી", englishName: "Gujarati", dir: "ltr", completeness: 1 },
  { code: "ur", nativeName: "اردو", englishName: "Urdu", dir: "rtl", completeness: 1 },
  { code: "pa", nativeName: "ਪੰਜਾਬੀ", englishName: "Punjabi", dir: "ltr", completeness: 1 },
  { code: "ml", nativeName: "മലയാളം", englishName: "Malayalam", dir: "ltr", completeness: 0.998 },
  { code: "kn", nativeName: "ಕನ್ನಡ", englishName: "Kannada", dir: "ltr", completeness: 0.999 },
  // Middle East (RTL)
  { code: "ar", nativeName: "العربية", englishName: "Arabic", dir: "rtl", completeness: 0.985 },
  { code: "he", nativeName: "עברית", englishName: "Hebrew", dir: "rtl", completeness: 0.999 },
  { code: "fa", nativeName: "فارسی", englishName: "Persian", dir: "rtl", completeness: 0.999 },
  // African
  { code: "sw", nativeName: "Kiswahili", englishName: "Swahili", dir: "ltr", completeness: 1 },
  { code: "am", nativeName: "አማርኛ", englishName: "Amharic", dir: "ltr", completeness: 1 },
  { code: "yo", nativeName: "Yorùbá", englishName: "Yoruba", dir: "ltr", completeness: 0.998 },
  { code: "ha", nativeName: "Hausa", englishName: "Hausa", dir: "ltr", completeness: 1 },
  { code: "zu", nativeName: "isiZulu", englishName: "Zulu", dir: "ltr", completeness: 1 },
  { code: "ig", nativeName: "Igbo", englishName: "Igbo", dir: "ltr", completeness: 0.999 },
  { code: "af", nativeName: "Afrikaans", englishName: "Afrikaans", dir: "ltr", completeness: 0.996 },
  { code: "so", nativeName: "Soomaali", englishName: "Somali", dir: "ltr", completeness: 1 },
];
