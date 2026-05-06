export type SupportedFund = {
  /** Must match indexed `fund_name` for metrics/RAG lookups (Deliverables/Resources.md). */
  name: string;
  category: string;
  /** Short avatar label in the horizontal fund cards */
  mark: string;
};

/**
 * Canonical MF pages for product chat – same schemes and Groww URLs as
 * Deliverables/Resources.md § "Mutual fund pages to scrape".
 */
export const SUPPORTED_FUNDS: SupportedFund[] = [
  { name: "Motilal Oswal Midcap Fund Direct Growth", category: "Equity - Mid Cap", mark: "MO" },
  {
    name: "Motilal Oswal Flexi Cap Fund Direct Growth",
    category: "Equity - Flexi Cap",
    mark: "MF",
  },
  {
    name: "Motilal Oswal Nifty Midcap 150 Index Fund Direct Growth",
    category: "Index Funds / ETF",
    mark: "M150",
  },
  {
    name: "HDFC Large and Mid Cap Fund Direct Growth",
    category: "Equity - Large & Mid Cap",
    mark: "HM",
  },
  { name: "HDFC Flexi Cap Direct Plan Growth", category: "Equity - Flexi Cap", mark: "HF" },
  { name: "HDFC Large Cap Fund Direct Growth", category: "Equity - Large Cap", mark: "HL" },
];

export type BookingReason = {
  id: string;
  label: string;
  summary: string;
  prompt: string;
};

export const BOOKING_REASONS: BookingReason[] = [
  {
    id: "kyc",
    label: "KYC/Onboarding",
    summary: "Document verification, account activation, and first-time setup.",
    prompt: "Book an advisor for KYC help",
  },
  {
    id: "sip",
    label: "SIP/mandates",
    summary: "Autopay, mandate setup, failed SIPs, and payment retries.",
    prompt: "Book an advisor for SIP or mandate issues",
  },
  {
    id: "tax",
    label: "Statements/Tax Docs",
    summary: "Capital gains statements, tax proofs, and report access.",
    prompt: "Book an advisor for statements and tax docs",
  },
  {
    id: "withdrawals",
    label: "Withdrawals and Timelines",
    summary: "Redemption steps, expected timelines, and payout tracking.",
    prompt: "Book an advisor for withdrawals and timelines",
  },
  {
    id: "account",
    label: "Account Changes/Nominee",
    summary: "Nominee updates, profile changes, and account maintenance.",
    prompt: "Book an advisor for account changes or nominee help",
  },
];

export const CURATED_CUSTOMER_PROMPTS = [
  "What is the NAV of HDFC Flexi Cap Direct Plan Growth?",
  "Compare expense ratio of Motilal Oswal Midcap Fund Direct Growth and Motilal Oswal Nifty Midcap 150 Index Fund Direct Growth",
  "Explain expense ratio in simple terms",
  "What fees do I pay in a mutual fund?",
  "I need help with withdrawals and timelines",
  "I'm facing SIP or mandate issues",
  "Help me with statements and tax docs",
  "Book an advisor for KYC help",
  "Cancel my booking using booking ID",
];
