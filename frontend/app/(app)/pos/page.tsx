"use client";

import { useCallback, useState } from "react";
import { Returns } from "@/components/pos/returns";
import { Till } from "@/components/pos/till";
import { ReceiptModal } from "@/components/receipt";
import { Button, Field, Input, Modal, Notice, Tabs } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { date, dateTime, money } from "@/lib/format";
import { useAction, useApi, useGlobalKeys, useList } from "@/lib/hooks";
import { newCart, type Cart } from "@/lib/pos";
import type { Customer, Sale, SaleSummary } from "@/lib/types";

interface Shift {
  id: number;
  opened_at: string;
  opening_cash: string;
  running_cash: string;
}

export default function PosPage() {
  const { branch } = useAuth();
  // Switching branch starts a fresh till: a cart never crosses branches.
  return <Counter key={branch?.id} />;
}

function Counter() {
  const { can } = useAuth();
  const [mode, setMode] = useState<"sell" | "return">("sell");
  const [carts, setCarts] = useState<Cart[]>(() => [newCart("Customer 1")]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [receipt, setReceipt] = useState<Sale | null>(null);
  const [lastSale, setLastSale] = useState<Sale | null>(null);
  const [showHeld, setShowHeld] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const customers = useList<Customer>("/customers/", { is_active: true, page_size: 500 });
  const shift = useApi<Shift | null>("/sales/shifts/current/");
  const active = carts.find((cart) => cart.id === activeId) ?? carts[0];

  const patch = useCallback(
    (id: string, change: Partial<Cart>) => setCarts((all) => all.map((cart) => (cart.id === id ? { ...cart, ...change } : cart))),
    [],
  );

  const openCart = useCallback(
    (cart: Cart) => {
      setCarts((all) => [...all, cart]);
      setActiveId(cart.id);
      setMode("sell");
    },
    [],
  );

  const nextName = useCallback(
    () => `Customer ${carts.length + 1}`,
    [carts.length],
  );

  const closeCart = (id: string) => {
    const left = carts.filter((cart) => cart.id !== id);
    const replacement = left.length ? left : [newCart("Customer 1")];
    setCarts(replacement);
    if (id === active.id) setActiveId(replacement[0].id);
  };

  // Alt+N opens another customer's cart, Alt+1…9 jumps between them.
  useGlobalKeys((event) => {
    if (!event.altKey || mode !== "sell") return;
    if (event.key.toLowerCase() === "n") {
      event.preventDefault();
      openCart(newCart(`Customer ${carts.length + 1}`));
    } else if (/^[1-9]$/.test(event.key) && carts[Number(event.key) - 1]) {
      event.preventDefault();
      setActiveId(carts[Number(event.key) - 1].id);
    }
  });

  const finish = (sale: Sale) => {
    closeCart(active.id);
    setReceipt(sale);
    setLastSale(sale);
    shift.reload();
    customers.reload();
  };

  const named = (cart: Cart, index: number) => {
    const chosen = customers.rows.find((entry) => String(entry.id) === cart.customer);
    return chosen?.name ?? (cart.resuming ? `Held #${cart.resuming.id}` : cart.name || `Customer ${index + 1}`);
  };

  return (
    <>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-semibold tracking-tight">Point of sale</h1>
          <Tabs
            value={mode}
            onChange={setMode}
            options={can("sales.return") ? [["sell", "Sell"], ["return", "Return"]] : [["sell", "Sell"]]}
          />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {lastSale && (
            <Button variant="ghost" size="sm" onClick={() => setReceipt(lastSale)}>
              Reprint {lastSale.number}
            </Button>
          )}
          <ShiftBar shift={shift.data} onChange={shift.reload} />
          <Button variant="secondary" size="sm" onClick={() => setShowHeld(true)}>
            Parked invoices
          </Button>
        </div>
      </div>

      {mode === "sell" ? (
        <>
          {/* One tab per customer at the counter, so a cart can wait while another is served. */}
          <div className="mb-3 flex flex-wrap items-center gap-1.5" role="tablist" aria-label="Open carts">
            {carts.map((cart, index) => {
              const current = cart.id === active.id;
              return (
                <span
                  key={cart.id}
                  className={`flex items-center gap-1 rounded-full border py-1 pr-1 pl-3 text-[13px] ${
                    current ? "border-ink bg-ink text-white" : "border-line bg-surface text-muted hover:text-ink"
                  }`}
                >
                  <button role="tab" aria-selected={current} onClick={() => setActiveId(cart.id)}>
                    {named(cart, index)}
                    {cart.lines.length > 0 && (
                      <span className={current ? "text-white/70" : "text-muted"}> · {cart.lines.length}</span>
                    )}
                  </button>
                  {carts.length > 1 && (
                    <button
                      aria-label={`Close ${named(cart, index)}`}
                      onClick={() => closeCart(cart.id)}
                      className={`rounded-full px-1 ${current ? "hover:bg-white/15" : "hover:bg-canvas hover:text-danger"}`}
                    >
                      ✕
                    </button>
                  )}
                </span>
              );
            })}
            <Button variant="ghost" size="sm" onClick={() => openCart(newCart(nextName()))}>
              + Another customer
            </Button>
          </div>

          <Notice tone="ok">{message}</Notice>
          <Till
            key={active.id}
            cart={active}
            onChange={(change) => patch(active.id, change)}
            onCompleted={finish}
            onHeld={() => {
              closeCart(active.id);
              setMessage("Invoice parked on the server. Pick it up from Parked invoices on any till.");
            }}
            customers={customers.rows}
            onCustomerAdded={customers.reload}
          />
          <p className="mt-2 text-xs text-muted">
            F2 search · ↑ ↓ Enter pick · F8 park · F9 complete · Alt+N another customer · Alt+1…9 switch
          </p>
        </>
      ) : (
        <Returns onDone={() => shift.reload()} />
      )}

      {receipt && <ReceiptModal sale={receipt} onClose={() => setReceipt(null)} />}
      {showHeld && (
        <HeldModal
          onClose={() => setShowHeld(false)}
          onResume={(sale) => {
            const cart = newCart(`Held #${sale.id}`);
            openCart({ ...cart, resuming: sale, prescription: sale.prescription_reference });
            setShowHeld(false);
          }}
        />
      )}
    </>
  );
}

function HeldModal({ onClose, onResume }: { onClose: () => void; onResume: (sale: Sale) => void }) {
  const held = useList<SaleSummary>("/sales/", { status: "held" });
  const { error, run } = useAction();
  return (
    <Modal title="Parked invoices" onClose={onClose}>
      <Notice>{error ?? held.error}</Notice>
      <ul className="divide-y divide-line/70">
        {held.rows.map((sale) => (
          <li key={sale.id} className="flex items-center justify-between gap-3 py-2.5">
            <div>
              <p className="font-medium">
                #{sale.id} · {sale.customer_name || "Walk-in"}
              </p>
              <p className="text-xs text-muted">
                {dateTime(sale.created_at)} · {sale.cashier_name}
              </p>
            </div>
            <span className="num font-medium">{money(sale.total)}</span>
            <span className="flex gap-1.5">
              <Button
                size="sm"
                onClick={async () => {
                  const full = await run(() => api<Sale>(`/sales/${sale.id}/`));
                  if (full) onResume(full);
                }}
              >
                Resume
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={async () => {
                  await run(() => api(`/sales/${sale.id}/discard/`, { method: "POST" }));
                  held.reload();
                }}
              >
                Discard
              </Button>
            </span>
          </li>
        ))}
      </ul>
      {!held.loading && held.rows.length === 0 && <p className="py-6 text-center text-muted">No invoices parked.</p>}
    </Modal>
  );
}

function ShiftBar({ shift, onChange }: { shift: Shift | null; onChange: () => void }) {
  const [open, setOpen] = useState(false);
  const [cash, setCash] = useState("");
  const { busy, error, run } = useAction();
  const submit = async () => {
    const done = await run(() =>
      shift
        ? api(`/sales/shifts/${shift.id}/close/`, { body: { closing_cash: cash || "0" } })
        : api("/sales/shifts/open/", { body: { opening_cash: cash || "0" } }),
    );
    if (done !== undefined) {
      setOpen(false);
      setCash("");
      onChange();
    }
  };
  return (
    <>
      <Button variant="secondary" size="sm" onClick={() => setOpen(true)}>
        {shift ? `Shift open · cash ${money(shift.running_cash)}` : "Open shift"}
      </Button>
      {open && (
        <Modal
          title={shift ? "Close shift" : "Open shift"}
          onClose={() => setOpen(false)}
          footer={
            <Button disabled={busy} onClick={submit}>
              {shift ? "Close shift" : "Open shift"}
            </Button>
          }
        >
          <div className="space-y-3">
            <Notice>{error}</Notice>
            {shift && (
              <p className="text-muted">
                Opened {date(shift.opened_at)} with {money(shift.opening_cash)}. Expected in drawer:{" "}
                <span className="num font-medium text-ink">{money(shift.running_cash)}</span>
              </p>
            )}
            <Field label={shift ? "Cash counted in drawer" : "Opening cash"}>
              <Input
                autoFocus
                inputMode="decimal"
                value={cash}
                onChange={(event) => setCash(event.target.value.replace(/[^\d.]/g, ""))}
                className="num"
                placeholder="0.00"
              />
            </Field>
          </div>
        </Modal>
      )}
    </>
  );
}
