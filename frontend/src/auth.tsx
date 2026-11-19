import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";
import { api, queryKeys, type Me } from "@/api";
import { FullPageSpinner } from "@/components/FullPageSpinner";

/** The logged-in user (`null` when logged out, `undefined` while loading). */
export function useMe() {
  return useQuery({ queryKey: queryKeys.me, queryFn: api.me, staleTime: 60_000, retry: false });
}

export function useLogin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ username, password }: { username: string; password: string }) => api.login(username, password),
    onSuccess: (me: Me) => {
      qc.removeQueries({ predicate: (q) => q.queryKey[0] !== queryKeys.me[0] });
      qc.setQueryData(queryKeys.me, me);
    },
  });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.logout,
    // Whatever the server said, forget everything this user loaded.
    onSettled: () => {
      qc.clear();
      qc.setQueryData(queryKeys.me, null);
    },
  });
}

/** Renders its children only for a logged-in user; otherwise goes to /login. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const me = useMe();
  const location = useLocation();
  if (me.isPending) return <FullPageSpinner />;
  if (me.isError) {
    return (
      <div role="alert" className="mx-auto max-w-md px-4 py-16 text-center text-sm text-muted-foreground">
        {me.error.message}
      </div>
    );
  }
  if (!me.data) {
    const from = location.pathname + location.search;
    return <Navigate to="/login" replace state={from === "/" ? undefined : { from }} />;
  }
  return <>{children}</>;
}
