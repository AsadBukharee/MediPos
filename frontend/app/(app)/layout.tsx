"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "@/lib/auth";
import { title } from "@/lib/format";

const NAV: { href: string; label: string; permission: string; group: string }[] = [
  { href: "/dashboard", label: "Dashboard", permission: "reports.view", group: "Overview" },
  { href: "/pos", label: "Point of sale", permission: "sales.create", group: "Sell" },
  { href: "/sales", label: "Invoices", permission: "sales.view", group: "Sell" },
  { href: "/customers", label: "Customers", permission: "customers.view", group: "Sell" },
  { href: "/products", label: "Medicines", permission: "catalog.view", group: "Stock" },
  { href: "/inventory", label: "Inventory", permission: "inventory.view", group: "Stock" },
  { href: "/order-list", label: "Alerts & order list", permission: "inventory.view", group: "Stock" },
  { href: "/purchases", label: "Purchases", permission: "purchases.view", group: "Buy" },
  { href: "/suppliers", label: "Suppliers", permission: "suppliers.view", group: "Buy" },
  { href: "/reports", label: "Reports", permission: "reports.view", group: "Finance" },
  { href: "/reports/trends", label: "Sales trends", permission: "reports.view", group: "Finance" },
  { href: "/accounting", label: "Accounting", permission: "accounting.view", group: "Finance" },
  { href: "/users", label: "Users", permission: "users.manage", group: "Admin" },
];

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, branch, ready, can, signOut, switchBranch } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    if (ready && !user) router.replace("/login");
  }, [ready, user, router]);

  if (!ready || !user) return <p className="p-10 text-muted">Loading…</p>;
  const links = NAV.filter((item) => can(item.permission));
  const groups = [...new Set(links.map((item) => item.group))];

  return (
    <div className="flex min-h-screen">
      <aside className="no-print sticky top-0 flex h-screen w-56 shrink-0 flex-col bg-ink text-white">
        <div className="px-5 pt-5 pb-4 text-lg font-semibold tracking-tight">
          Medi<span className="text-[#5fd4c4]">Pos</span>
        </div>
        <nav className="flex-1 overflow-y-auto px-2.5 pb-4" aria-label="Main">
          {groups.map((group) => (
            <div key={group} className="mt-3">
              <p className="px-2.5 pb-1 text-[11px] tracking-wider text-white/40 uppercase">{group}</p>
              {links
                .filter((item) => item.group === group)
                .map((item) => {
                  const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      aria-current={active ? "page" : undefined}
                      className={`block rounded-md px-2.5 py-1.5 ${active ? "bg-white/12 font-medium text-white" : "text-white/70 hover:bg-white/6 hover:text-white"}`}
                    >
                      {item.label}
                    </Link>
                  );
                })}
            </div>
          ))}
        </nav>
        <div className="space-y-2 border-t border-white/10 p-3">
          {user.branches.length > 1 ? (
            // Styled for the dark sidebar, so it does not inherit the light form palette.
            <select
              aria-label="Branch"
              value={branch?.id ?? ""}
              onChange={(event) => switchBranch(Number(event.target.value))}
              className="h-9 w-full rounded-md border border-white/15 bg-ink-2 px-2.5 pr-7 text-white"
            >
              {user.branches.map((b) => (
                <option key={b.id} value={b.id} className="text-ink">
                  {b.name}
                </option>
              ))}
            </select>
          ) : (
            <p className="px-1 text-[13px] text-white/70">{branch?.name ?? "No branch assigned"}</p>
          )}
          <div className="flex items-center justify-between px-1">
            <div className="min-w-0">
              <p className="truncate text-[13px] font-medium">{user.first_name || user.username}</p>
              <p className="text-xs text-white/50">{title(user.role)}</p>
            </div>
            <button onClick={() => signOut()} className="rounded px-2 py-1 text-xs text-white/70 hover:bg-white/10 hover:text-white">
              Sign out
            </button>
          </div>
        </div>
      </aside>
      <main className="min-w-0 flex-1 p-6">
        {branch ? children : <p className="text-muted">Your account has no branch yet. Ask an owner to assign one.</p>}
      </main>
    </div>
  );
}
