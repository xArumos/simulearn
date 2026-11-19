import { History } from "lucide-react";
import { EmptyState, PageHeader } from "@/components/PageHeader";

/** Placeholder: the history list and export are built in issue #62. */
export function HistoryPage() {
  return (
    <>
      <PageHeader title="History" description="Your past practice conversations." />
      <EmptyState icon={<History aria-hidden />} title="Nothing here yet">
        Your saved conversations will appear here, ready to reopen or download.
      </EmptyState>
    </>
  );
}
