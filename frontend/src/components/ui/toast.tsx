import { CircleAlert, CircleCheck, Info, X } from "lucide-react";
import { Toast as ToastPrimitive } from "radix-ui";
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";

export type ToastTone = "info" | "success" | "error";

export interface ToastInput {
  title: string;
  description?: string;
  tone?: ToastTone;
}

interface ToastItem extends ToastInput {
  id: number;
}

const ToastContext = createContext<((t: ToastInput) => void) | null>(null);

const toneIcon = { info: Info, success: CircleCheck, error: CircleAlert } as const;
const toneClass = { info: "text-accent", success: "text-success", error: "text-danger" } as const;

/** Provides `useToast()` and renders the toast stack (bottom right, or bottom on phones). */
export function Toaster({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const push = useCallback((t: ToastInput) => {
    setItems((prev) => [...prev.slice(-3), { ...t, id: Date.now() + Math.random() }]);
  }, []);
  const remove = (id: number) => setItems((prev) => prev.filter((t) => t.id !== id));
  const value = useMemo(() => push, [push]);

  return (
    <ToastContext.Provider value={value}>
      <ToastPrimitive.Provider swipeDirection="right" duration={5000}>
        {children}
        {items.map((t) => {
          const tone = t.tone ?? "info";
          const Icon = toneIcon[tone];
          return (
            <ToastPrimitive.Root
              key={t.id}
              type={tone === "error" ? "foreground" : "background"}
              onOpenChange={(open) => !open && remove(t.id)}
              className="flex items-start gap-3 rounded-lg border bg-surface p-4 text-foreground shadow-pop animate-pop-in data-[swipe=end]:animate-fade-in"
            >
              <Icon className={cn("mt-0.5 size-5 shrink-0", toneClass[tone])} aria-hidden />
              <div className="grid min-w-0 flex-1 gap-1">
                <ToastPrimitive.Title className="text-sm font-medium">{t.title}</ToastPrimitive.Title>
                {t.description && (
                  <ToastPrimitive.Description className="text-sm text-muted-foreground">{t.description}</ToastPrimitive.Description>
                )}
              </div>
              <ToastPrimitive.Close
                className="rounded-md p-1 text-muted-foreground hover:bg-surface-muted hover:text-foreground"
                aria-label="Dismiss"
              >
                <X className="size-4" aria-hidden />
              </ToastPrimitive.Close>
            </ToastPrimitive.Root>
          );
        })}
        <ToastPrimitive.Viewport className="fixed bottom-0 right-0 z-[100] flex w-full max-w-sm flex-col gap-2 p-4 outline-none" />
      </ToastPrimitive.Provider>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const push = useContext(ToastContext);
  if (!push) throw new Error("useToast must be used inside <Toaster>");
  return push;
}
