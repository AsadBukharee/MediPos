"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Button, Field, Input, Notice } from "@/components/ui";
import { api } from "@/lib/api";
import { useAction } from "@/lib/hooks";

/** Without ?uid&token: ask for a reset email. With them (from the email link): choose a new password. */
export default function ResetPasswordPage() {
  return (
    <Suspense fallback={null}>
      <ResetPassword />
    </Suspense>
  );
}

function ResetPassword() {
  const query = useSearchParams();
  const link = { uid: query.get("uid") ?? "", token: query.get("token") ?? "" };
  const hasLink = Boolean(link.uid && link.token);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [done, setDone] = useState<string | null>(null);
  const { busy, error, run } = useAction();

  const submit = async () => {
    const result = await run(async () => {
      if (hasLink) await api("/auth/password/reset/confirm/", { body: { ...link, new_password: password } });
      else await api("/auth/password/reset/", { body: { email } });
      return true;
    });
    if (result) setDone(hasLink ? "Password changed. You can sign in now." : "If that email belongs to an account, a reset link is on its way.");
  };

  return (
    <main className="flex min-h-screen items-center justify-center p-6">
      <form className="w-full max-w-sm space-y-4" onSubmit={(event) => (event.preventDefault(), void submit())}>
        <h1 className="text-2xl font-semibold tracking-tight">{hasLink ? "Choose a new password" : "Reset your password"}</h1>
        <Notice>{error}</Notice>
        <Notice tone="ok">{done}</Notice>
        {!done &&
          (hasLink ? (
            <Field label="New password" hint="At least 8 characters.">
              <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" autoFocus required minLength={8} />
            </Field>
          ) : (
            <Field label="Email on your account">
              <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" autoFocus required />
            </Field>
          ))}
        {!done && (
          <Button type="submit" size="lg" className="w-full" disabled={busy}>
            {hasLink ? "Save password" : "Send reset link"}
          </Button>
        )}
        <Link href="/login" className="block text-center text-[13px] font-medium text-brand hover:underline">
          Back to sign in
        </Link>
      </form>
    </main>
  );
}
