import { useMutation } from "@tanstack/react-query";
import { CircleAlert, LoaderCircle } from "lucide-react";
import { useState, type FormEvent } from "react";
import { api } from "@/api";
import { useMe } from "@/auth";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/toast";

export function AccountPage() {
  const me = useMe().data;
  const toast = useToast();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);

  const change = useMutation({
    mutationFn: () => api.changePassword(current, next),
    onSuccess: () => {
      setCurrent("");
      setNext("");
      setConfirm("");
      toast({ tone: "success", title: "Password changed", description: "Use your new password next time you sign in." });
    },
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    setLocalError(null);
    change.reset();
    if (next !== confirm) {
      setLocalError("The new passwords don't match.");
      return;
    }
    if (next === current) {
      setLocalError("The new password must be different from the current one.");
      return;
    }
    change.mutate();
  };

  const error = localError ?? change.error?.message;
  const ready = current && next && confirm && !change.isPending;

  return (
    <>
      <PageHeader title="Account" description="Your sign-in details." />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <section className="rounded-xl border bg-surface p-6 shadow-card" aria-labelledby="profile-heading">
          <h2 id="profile-heading" className="mb-4 text-base font-semibold">
            Profile
          </h2>
          <dl className="grid gap-3 text-sm">
            <div className="grid gap-0.5">
              <dt className="text-muted-foreground">Name</dt>
              <dd className="font-medium break-words">{me?.display_name}</dd>
            </div>
            <div className="grid gap-0.5">
              <dt className="text-muted-foreground">Username</dt>
              <dd className="font-medium break-words">{me?.username}</dd>
            </div>
            <div className="grid gap-0.5">
              <dt className="text-muted-foreground">Role</dt>
              <dd className="font-medium">{me?.role === "admin" ? "Administrator" : "Educator"}</dd>
            </div>
          </dl>
        </section>

        <section className="rounded-xl border bg-surface p-6 shadow-card" aria-labelledby="password-heading">
          <h2 id="password-heading" className="mb-1 text-base font-semibold">
            Change password
          </h2>
          <p className="mb-5 text-sm text-muted-foreground">Choose a password you don't use anywhere else.</p>
          <form onSubmit={onSubmit} noValidate className="grid max-w-md gap-4">
            {error && (
              <div role="alert" className="flex items-start gap-2 rounded-md bg-danger-soft px-3 py-2.5 text-sm text-danger-soft-foreground">
                <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
                <span>{error}</span>
              </div>
            )}
            <div className="grid gap-2">
              <Label htmlFor="current-password">Current password</Label>
              <Input
                id="current-password"
                type="password"
                autoComplete="current-password"
                value={current}
                onChange={(e) => setCurrent(e.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="new-password">New password</Label>
              <Input
                id="new-password"
                type="password"
                autoComplete="new-password"
                value={next}
                onChange={(e) => setNext(e.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="confirm-password">Confirm new password</Label>
              <Input
                id="confirm-password"
                type="password"
                autoComplete="new-password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
              />
            </div>
            <div>
              <Button type="submit" disabled={!ready}>
                {change.isPending && <LoaderCircle className="animate-spin" aria-hidden />}
                Update password
              </Button>
            </div>
          </form>
        </section>
      </div>
    </>
  );
}
