import { MessagesSquare } from "lucide-react";
import { useMe } from "@/auth";
import { EmptyState, PageHeader } from "@/components/PageHeader";

/** Placeholder: the practice chat is built in issue #61. */
export function PracticePage() {
  const me = useMe().data;
  const first = me?.display_name?.split(/\s+/)[0];
  return (
    <>
      <PageHeader
        title={first ? `Welcome, ${first}` : "Practice"}
        description="Talk with an AI child and try out your questions and prompts."
      />
      <EmptyState icon={<MessagesSquare aria-hidden />} title="Practice is coming soon">
        This is where you will pick a child's age and a scene, then have a conversation. It's being built now.
      </EmptyState>
    </>
  );
}
