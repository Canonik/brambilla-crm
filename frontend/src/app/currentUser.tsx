import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { listOwners } from "@/api/endpoints";
import { DEFAULT_USER, USERS, setKnownUsers, userByEmail } from "@/api/users";
import type { CrmUser } from "@/api/types";

// Who is using the CRM right now. The assistant contract needs an active
// Brambilla user as `context.user`, and notes are logged under that name.
// There is no login in this challenge, so the user is picked in the sidebar
// from the owners the migration created (utenti.csv).

const STORAGE_KEY = "brambilla.crm.user";

interface CurrentUserApi {
  user: CrmUser;
  users: CrmUser[];
  setUser: (email: string) => void;
}

const Ctx = createContext<CurrentUserApi | null>(null);

function readStoredEmail(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function CurrentUserProvider({ children }: { children: ReactNode }) {
  const owners = useQuery({ queryKey: ["owners"], queryFn: listOwners, staleTime: 10 * 60_000, retry: 1 });
  const users = owners.data && owners.data.length > 0 ? owners.data : USERS;
  const [email, setEmail] = useState<string | null>(readStoredEmail);

  useEffect(() => {
    if (owners.data) setKnownUsers(owners.data);
  }, [owners.data]);

  const user = useMemo<CrmUser>(() => {
    const stored = email ? users.find((u) => u.email === email.toLowerCase()) ?? userByEmail(email) : null;
    if (stored) return stored;
    return users.find((u) => u.email === DEFAULT_USER.email) ?? users[0] ?? DEFAULT_USER;
  }, [email, users]);

  const api = useMemo<CurrentUserApi>(
    () => ({
      user,
      users,
      setUser: (next) => {
        const key = next.trim().toLowerCase();
        if (!users.some((u) => u.email === key)) return;
        setEmail(key);
        try {
          window.localStorage.setItem(STORAGE_KEY, key);
        } catch {
          // ignore
        }
      },
    }),
    [user, users],
  );
  return <Ctx.Provider value={api}>{children}</Ctx.Provider>;
}

export function useCurrentUser() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useCurrentUser must be used inside CurrentUserProvider");
  return ctx;
}
