import { createContext, use, useCallback, useEffect, useMemo, useState } from 'react';

import { api, session } from './api';
import { registerForPush, unregisterPush } from './push';
import type { Branch, User } from './types';

interface AuthState {
  ready: boolean;
  user: User | null;
  branch: Branch | null;
  can: (permission: string) => boolean;
  signIn: (username: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  chooseBranch: (branch: Branch) => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

function savedBranch(user: User): Branch | null {
  const id = session.branchId();
  // With a single branch there is nothing to choose.
  return user.branches.find((b) => b.id === id) ?? (user.branches.length === 1 ? user.branches[0] : null);
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [user, setUser] = useState<User | null>(null);
  const [branch, setBranch] = useState<Branch | null>(null);

  const adopt = useCallback(async (me: User) => {
    const chosen = savedBranch(me);
    if (chosen) await session.setBranch(chosen.id);
    setUser(me);
    setBranch(chosen);
    registerForPush().catch(() => undefined); // push is optional: the app works without it
  }, []);

  useEffect(() => {
    session.onSignedOut(() => {
      setUser(null);
      setBranch(null);
    });
    const restore = async () => {
      if (!(await session.load())) return;
      try {
        await adopt(await api<User>('/auth/me/'));
      } catch {
        /* offline or expired: stay signed out until the server answers */
      }
    };
    restore().finally(() => setReady(true));
  }, [adopt]);

  const signIn = useCallback(
    async (username: string, password: string) => {
      const data = await api<{ access: string; refresh: string; user: User }>('/auth/login/', {
        body: { username, password },
      });
      await session.save(data.access, data.refresh);
      await adopt(data.user);
    },
    [adopt],
  );

  const signOut = useCallback(async () => {
    await unregisterPush().catch(() => undefined);
    const refresh = session.refreshToken();
    if (refresh) await api('/auth/logout/', { body: { refresh } }).catch(() => undefined);
    await session.clear();
    setUser(null);
    setBranch(null);
  }, []);

  const chooseBranch = useCallback(async (next: Branch) => {
    await session.setBranch(next.id);
    setBranch(next);
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      ready,
      user,
      branch,
      // Only decides what to show. The server checks every request again.
      can: (permission) => Boolean(user?.permissions.includes(permission)),
      signIn,
      signOut,
      chooseBranch,
    }),
    [ready, user, branch, signIn, signOut, chooseBranch],
  );
  return <AuthContext value={value}>{children}</AuthContext>;
}

export function useAuth(): AuthState {
  const context = use(AuthContext);
  if (!context) throw new Error('useAuth must be used inside AuthProvider');
  return context;
}
