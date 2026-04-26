import { EmptyState } from "@/components/shared/EmptyState";

export function CustomerTab() {
  return (
    <EmptyState
      title="Customer chat arrives in Phase 3"
      description="Phase 1 establishes the shell only. Upcoming phases add grounded MF + fee chat, prompt chips, and booking flows per `Docs/Architecture.md`."
    />
  );
}
