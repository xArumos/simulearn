import { cn } from "@/lib/utils";

/** The SimuLearn mark: two speech bubbles (adult and child) and the name. */
export function Wordmark({ className, size = "md" }: { className?: string; size?: "md" | "lg" }) {
  const box = size === "lg" ? "size-9" : "size-7";
  return (
    <span className={cn("inline-flex items-center gap-2 text-foreground", className)}>
      <svg viewBox="0 0 32 32" className={box} aria-hidden>
        <rect width="32" height="32" rx="8" className="fill-accent" />
        <path
          d="M8 10.5a3 3 0 0 1 3-3h7a3 3 0 0 1 3 3v3.5a3 3 0 0 1-3 3h-4.2L10.5 19.6v-2.7A3 3 0 0 1 8 14z"
          className="fill-accent-foreground"
        />
        <path
          d="M15 17.6h5.4a2.6 2.6 0 0 1 2.6 2.6v2a2.6 2.6 0 0 1-2.6 2.6h-.3v2.1l-2.8-2.1h-.1A2.6 2.6 0 0 1 14.6 22.2z"
          className="fill-accent-foreground"
          opacity="0.7"
        />
      </svg>
      <span className={cn("font-semibold tracking-tight", size === "lg" ? "text-2xl" : "text-lg")}>
        Simu<span className="text-accent">Learn</span>
      </span>
    </span>
  );
}
