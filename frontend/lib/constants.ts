export const TABS = ["customer", "product", "advisor"] as const;

export type TabId = (typeof TABS)[number];

export const TAB_LABELS: Record<TabId, string> = {
  customer: "Customer",
  product: "Product",
  advisor: "Advisor",
};
