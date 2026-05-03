export type SupportedFund = {
  name: string;
  category: string;
  mark: string;
};

export type BookingReason = {
  id: string;
  label: string;
  summary: string;
  prompt: string;
};

export const SUPPORTED_FUNDS: SupportedFund[] = [
  { name: "HDFC Flexi Cap Fund", category: "Equity - Flexi Cap", mark: "HF" },
  { name: "Parag Parikh Flexi Cap Fund", category: "Equity - Flexi Cap", mark: "PP" },
  { name: "Motilal Oswal Midcap Fund", category: "Equity - Mid Cap", mark: "MO" },
  { name: "HDFC Large Cap Fund", category: "Equity - Large Cap", mark: "HL" },
  { name: "Nifty 50 Index Fund", category: "Passive - Index", mark: "N50" },
];

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
  "What is the NAV of HDFC Flexi Cap Fund?",
  "Compare HDFC Flexi Cap and Parag Parikh Flexi Cap",
  "Explain expense ratio in simple terms",
  "What fees do I pay in a mutual fund?",
  "I need help with withdrawals and timelines",
  "I'm facing SIP or mandate issues",
  "Help me with statements and tax docs",
  "Book an advisor for KYC help",
  "Cancel my booking using booking ID",
];
