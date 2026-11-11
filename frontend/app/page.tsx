"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "@/lib/auth";

export default function Home() {
  const { user, ready } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (ready) router.replace(!user ? "/login" : user.permissions.includes("reports.view") ? "/dashboard" : "/pos");
  }, [ready, user, router]);
  return null;
}
