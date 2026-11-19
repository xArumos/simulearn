import { LoaderCircle } from "lucide-react";

export function FullPageSpinner() {
  return (
    <div className="flex min-h-[50vh] items-center justify-center" role="status" aria-label="Loading">
      <LoaderCircle className="size-6 animate-spin text-muted-foreground" aria-hidden />
    </div>
  );
}
