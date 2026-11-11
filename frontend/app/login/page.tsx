"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Button, Field, Input, Notice } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { useAction } from "@/lib/hooks";

export default function LoginPage() {
  const { user, ready, signIn } = useAuth();
  const router = useRouter();
  const { busy, error, run } = useAction();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  useEffect(() => {
    if (ready && user) router.replace("/");
  }, [ready, user, router]);

  return (
    <main className="grid min-h-screen lg:grid-cols-[1.1fr_1fr]">
      <section className="hidden flex-col justify-between bg-ink p-12 text-white lg:flex">
        <p className="text-lg font-semibold tracking-tight">
          Medi<span className="text-[#5fd4c4]">Pos</span>
        </p>
        <div>
          <p className="max-w-md text-4xl leading-tight font-semibold tracking-tight">
            Every strip, every batch, every rupee — accounted for.
          </p>
          <p className="mt-4 max-w-sm text-white/60">
            Point of sale, batch inventory, purchasing and accounts for single stores and chains.
          </p>
        </div>
        <p className="text-xs text-white/40">Expired and blocked batches are never sold. Stock is deducted first-expiry-first.</p>
      </section>

      <section className="flex items-center justify-center p-6">
        <form
          className="w-full max-w-sm space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            run(() => signIn(username.trim(), password));
          }}
        >
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Sign in</h1>
            <p className="mt-1 text-muted">Use the account your manager gave you.</p>
          </div>
          <Notice>{error}</Notice>
          <Field label="Username">
            <Input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus autoComplete="username" required />
          </Field>
          <Field label="Password">
            <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
          </Field>
          <Button type="submit" size="lg" className="w-full" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </Button>
          <Link href="/reset-password" className="block text-center text-[13px] font-medium text-brand hover:underline">
            Forgot your password?
          </Link>
        </form>
      </section>
    </main>
  );
}
