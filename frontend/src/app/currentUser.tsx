import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import { DEFAULT_USER, USERS, userByEmail } from "@/api/users";
import type { CrmUser } from "@/api/types";

// Who is using the CRM right now. The assistant contract needs an active
// Brambilla user as `context.user`, and notes are logged under that name.
// There is no login in this challenge, so the user is picked in the sidebar.

const STORAGE_KEY = "brambilla.crm.user";

interface CurrentUserApi {
  user: CrmUser;
  users: CrmUser[];
  setUser: (email: string) => void;
}

const Ctx = createContext<CurrentUserApi | null>(null);

function readStored(): CrmUser {
  try {
    const email = window.localStorage.getItem(STORAGE_KEY);
    return userByEmail(email) ?? DEFAULT_USER;
  } catch {
    return DEFAULT_USER;
  }
}

export function CurrentUserProvider({ children }: { children: ReactNode }) {
  const [user, setUserState] = useState<CrmUser>(readStored);
  const api = useMemo<CurrentUserApi>(
    () => ({
      user,
      users: USERS,
      setUser: (email) => {
        const u = userByEmail(email);
        if (!u) return;
        setUserState(u);
        try {
          window.localStorage.setItem(STORAGE_KEY, u.email);
        } catch {
          // ignore
        }
      },
    }),
    [user],
  );
  return <Ctx.Provider value={api}>{children}</Ctx.Provider>;
}

export function useCurrentUser() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useCurrentUser must be used inside CurrentUserProvider");
  return ctx;
}
