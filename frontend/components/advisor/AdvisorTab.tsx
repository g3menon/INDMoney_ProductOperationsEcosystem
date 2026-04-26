import { EmptyState } from "@/components/shared/EmptyState";

export function AdvisorTab() {
  return (
    <EmptyState
      title="Advisor approvals arrive in Phase 6"
      description="The Advisor tab will list pending approvals and upcoming IST slots. For now, badge counts are sourced from the backend badge endpoint (stub counts in Phase 1)."
    />
  );
}
