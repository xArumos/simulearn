import { Compass } from "lucide-react";
import { Link } from "react-router";
import { EmptyState } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";

export function NotFoundPage() {
  return (
    <EmptyState icon={<Compass aria-hidden />} title="Page not found">
      <p className="mb-4">That page doesn't exist.</p>
      <Button asChild variant="secondary">
        <Link to="/">Back to Practice</Link>
      </Button>
    </EmptyState>
  );
}
