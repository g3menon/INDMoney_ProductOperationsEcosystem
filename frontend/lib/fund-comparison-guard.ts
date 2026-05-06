/** Detects user messages that ask the assistant to compare funds or pick a “better” scheme (policy layer). */

const COMPARISON_RE =
  /\b(compare|comparing|comparison|versus|vs\.?)\b|\bwhich\s+(fund|one|scheme|option)\s+(is\s+)?(better|best)\b|\bwhich\s+fund\s+should\s+i\b/i;

const FUND_LIKE_RE =
  /\b(mutual\s+funds?|\bfund\b|sip\b|scheme\b|direct\s+plan|hdfc|motilal|flexi\s*cap|mid\s*cap|large\s*cap|index\s+fund|\betf\b|nifty|nav\b|aum\b|growth\b)\b/i;

export function isFundComparisonPrompt(text: string): boolean {
  if (!text.trim()) return false;
  if (!COMPARISON_RE.test(text)) return false;
  const lower = text.toLowerCase();
  if (lower.includes("play store") || lower.includes("playstore") || lower.includes("app review")) return false;
  return FUND_LIKE_RE.test(text);
}
