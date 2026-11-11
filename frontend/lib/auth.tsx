"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, login as apiLogin, logout as apiLogout, session } from "./api";
import type { Branch, User } from "./types";

interface AuthState {
  user: User | null;
  branch: Branch | null;
  ready: boolean;
  can: (permission: string) => boolean;
  signIn: (username: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  switchBranch: (id: number) => void;
}

const AuthContext = createContext<AuthState | null>(null);

function pickBranch(user: User): Branch | null {
  const saved = Number(session.branchId());
  const branch = user.branches.find((b) => b.id === saved) ?? user.branches[0] ?? null;
  if (branch) session.setBranch(branch.id);
  return branch;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [branch, setBranch] = useState<Branch | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const restore = async () => {
      if (!session.hasToken()) return;
      try {
        const me = await api<User>("/auth/me/");
        setUser(me);
        setBranch(pickBranch(me));
      } catch {
        session.clear();
      }
    };
    restore().finally(() => setReady(true));
  }, []);

  const signIn = useCallback(async (username: string, password: string) => {
    const me = await apiLogin(username, password);
    setUser(me);
    setBranch(pickBranch(me));
  }, []);

  const signOut = useCallback(async () => {
    await apiLogout();
    setUser(null);
    setBranch(null);
  }, []);

  const switchBranch = useCallback(
    (id: number) => {
      const next = user?.branches.find((b) => b.id === id);
      if (!next) return;
      session.setBranch(next.id);
      setBranch(next);
    },
    [user],
  );

  const value = useMemo<AuthState>(
    () => ({
      user,
      branch,
      ready,
      // Hides what a role cannot use. The server enforces the same rules on every request.
      can: (permission) => Boolean(user?.permissions.includes(permission)),
      signIn,
      signOut,
      switchBranch,
    }),
    [user, branch, ready, signIn, signOut, switchBranch],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
