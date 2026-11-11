"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ReceiptModal } from "@/components/receipt";
import { Badge, Button, Card, Field, Input, Modal, Notice, Select } from "@/components/ui";
import { api, ApiError, newKey } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { date, dateTime, money, qty } from "@/lib/format";
import { useAction, useApi, useDebounced, useList } from "@/lib/hooks";
import type { Customer, PaymentMethod, Product, Quote, Sale, SaleSummary, StockRow } from "@/lib/types";

interface CartLine {
  product: Product;
  packaging: number;
  quantity: number;
  discount: string;
}

interface PaymentRow {
  method: PaymentMethod;
  amount: string;
}

interface Shift {
  id: number;
  opened_at: string;
  opening_cash: string;
  running_cash: string;
}

const METHODS: [PaymentMethod, string][] = [
  ["cash", "Cash"], ["card", "Card"], ["bank", "Bank"], ["wallet", "Wallet"], ["credit", "Credit"],
];
const looksLikeBarcode = (text: string) => /^\d{6,14}$/.test(text);

export default function PosPage() {
  const { branch } = useAuth();
  return <Pos key={branch?.id} />; // switching branch starts a fresh till: a cart never crosses branches
}

function Pos() {
  const searchRef = useRef<HTMLInputElement>(null);
  const [term, setTerm] = useState("");
  const [highlight, setHighlight] = useState(0);
  const [cart, setCart] = useState<CartLine[]>([]);
  const [customer, setCustomer] = useState("");
  const [invoiceDiscount, setInvoiceDiscount] = useState("");
  const [prescription, setPrescription] = useState("");
  const [payments, setPayments] = useState<PaymentRow[]>([{ method: "cash", amount: "" }]);
  const [priced, setPriced] = useState<Quote | null>(null);
  const [pricingError, setPricingError] = useState<string | null>(null);
  const [receipt, setReceipt] = useState<Sale | null>(null);
  const [resuming, setResuming] = useState<Sale | null>(null);
  const [showHeld, setShowHeld] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const idempotencyKey = useRef(newKey());
  const { busy, error, run, setError } = useAction();

  const debouncedTerm = useDebounced(term.trim(), 200);
  const results = useList<StockRow>(
    debouncedTerm.length >= 2 && !looksLikeBarcode(debouncedTerm) ? "/inventory/stock/" : null,
    { search: debouncedTerm, is_active: true, page_size: 8 },
  );
  const customers = useList<Customer>("/customers/", { is_active: true, page_size: 200 });
  const shift = useApi<Shift | null>("/sales/shifts/current/");

  const focusSearch = useCallback(() => searchRef.current?.focus(), []);

  const reset = useCallback(() => {
    setCart([]);
    setCustomer("");
    setInvoiceDiscount("");
    setPrescription("");
    setPayments([{ method: "cash", amount: "" }]);
    setPriced(null);
    setPricingError(null);
    setResuming(null);
    setError(null);
    idempotencyKey.current = newKey();
    focusSearch();
  }, [focusSearch, setError]);

  const addProduct = useCallback((product: Product, packagingId?: number | null) => {
    const sellable = product.packagings.filter((p) => p.can_sell);
    const packaging =
      sellable.find((p) => p.id === packagingId) ?? sellable.find((p) => p.is_default_sale) ?? sellable[0];
    if (!packaging) {
      setMessage(`${product.name} has no sellable unit configured.`);
      return;
    }
    setMessage(null);
    setCart((lines) => {
      const index = lines.findIndex((l) => l.product.id === product.id && l.packaging === packaging.id);
      if (index >= 0) return lines.map((l, i) => (i === index ? { ...l, quantity: l.quantity + 1 } : l));
      return [...lines, { product, packaging: packaging.id, quantity: 1, discount: "" }];
    });
    idempotencyKey.current = newKey();
    setTerm("");
    setHighlight(0);
    focusSearch();
  }, [focusSearch]);

  const addById = useCallback(async (id: number) => {
    try {
      addProduct(await api<Product>(`/catalog/products/${id}/`));
    } catch (e) {
      setMessage((e as ApiError).message);
    }
  }, [addProduct]);

  const scan = useCallback(async (code: string) => {
    try {
      const product = await api<Product>("/catalog/products/lookup/", { params: { barcode: code } });
      addProduct(product, product.scanned_packaging);
    } catch (e) {
      setMessage((e as ApiError).status === 404 ? `No medicine matches barcode ${code}.` : (e as ApiError).message);
      setTerm("");
    }
  }, [addProduct]);

  const updateLine = (index: number, patch: Partial<CartLine>) => {
    setCart((lines) => lines.map((l, i) => (i === index ? { ...l, ...patch } : l)));
    idempotencyKey.current = newKey();
  };

  const payload = useMemo(
    () => ({
      customer: customer ? Number(customer) : null,
      invoice_discount: invoiceDiscount || "0",
      items: cart.map((l) => ({
        product: l.product.id,
        packaging: l.packaging,
        quantity: l.quantity,
        discount_amount: l.discount || "0",
      })),
    }),
    [cart, customer, invoiceDiscount],
  );
  const debouncedPayload = useDebounced(payload, 250);
  // An empty cart has no quote, whatever the last answer from the server was.
  const quote = cart.length > 0 ? priced : null;
  const quoteError = cart.length > 0 ? pricingError : null;

  // The server prices the cart; the POS only displays what comes back.
  useEffect(() => {
    if (resuming || debouncedPayload.items.length === 0) return;
    let current = true;
    api<Quote>("/sales/quote/", { body: debouncedPayload })
      .then((q) => {
        if (!current) return;
        setPriced(q);
        setPricingError(null);
      })
      .catch((e: ApiError) => {
        if (current) setPricingError(e.message);
      });
    return () => {
      current = false;
    };
  }, [debouncedPayload, resuming]);

  const total = Number(resuming ? resuming.total : (quote?.total ?? 0));
  const paid = payments.reduce((sum, p) => sum + (Number(p.amount) || 0), 0);
  const change = paid - total;
  const needsPrescription = !resuming && Boolean(quote?.requires_prescription);
  const stale = !resuming && debouncedPayload !== payload;
  const canPay = (resuming || (cart.length > 0 && quote && !quoteError && !stale)) && paid >= total && total > 0;

  const cleanPayments = () => payments.filter((p) => Number(p.amount) > 0).map((p) => ({ method: p.method, amount: p.amount }));

  const complete = useCallback(async () => {
    if (!canPay || busy) return;
    const sale = await run(() =>
      resuming
        ? api<Sale>(`/sales/${resuming.id}/complete/`, { body: { payments: cleanPayments(), prescription_reference: prescription } })
        : api<Sale>("/sales/", {
            body: { ...payload, payments: cleanPayments(), prescription_reference: prescription },
            idempotencyKey: idempotencyKey.current, // a double click or network retry cannot create two invoices
          }),
    );
    if (sale) {
      reset();
      setReceipt(sale);
      shift.reload();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canPay, busy, resuming, payload, payments, prescription, run, reset]);

  const hold = useCallback(async () => {
    if (cart.length === 0 || resuming || busy) return;
    const held = await run(() => api<Sale>("/sales/", { body: { ...payload, hold: true, prescription_reference: prescription } }));
    if (held) {
      reset();
      setMessage(`Invoice held. Resume it from "Held" when the customer is back.`);
    }
  }, [cart.length, resuming, busy, run, payload, prescription, reset]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const action = { F2: focusSearch, F8: hold, F9: complete }[event.key];
      if (!action) return;
      event.preventDefault();
      action();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [focusSearch, hold, complete]);

  const onSearchKey = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const step = event.key === "ArrowDown" ? 1 : -1;
      setHighlight((h) => Math.min(Math.max(h + step, 0), Math.max(results.rows.length - 1, 0)));
    }
    if (event.key === "Escape") setTerm("");
    if (event.key === "Enter") {
      event.preventDefault();
      const text = term.trim();
      if (!text) return;
      if (looksLikeBarcode(text)) scan(text); // USB scanners type the code and press Enter
      else if (results.rows[highlight]) addById(results.rows[highlight].id);
    }
  };

  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_22rem]">
      <section className="min-w-0">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h1 className="text-xl font-semibold tracking-tight">Point of sale</h1>
          <div className="flex items-center gap-2">
            <ShiftBar shift={shift.data} onChange={shift.reload} />
            <Button variant="secondary" size="sm" onClick={() => setShowHeld(true)}>Held invoices</Button>
          </div>
        </div>

        <div className="relative">
          <Input
            ref={searchRef}
            value={term}
            onChange={(e) => (setTerm(e.target.value), setHighlight(0))}
            onKeyDown={onSearchKey}
            placeholder="Scan a barcode or type a medicine name…  (F2)"
            aria-label="Search medicine or scan barcode"
            className="h-12 text-base"
            disabled={Boolean(resuming)}
            autoFocus
          />
          {term.trim().length >= 2 && !looksLikeBarcode(term.trim()) && (
            <Card className="absolute z-10 mt-1 w-full overflow-hidden shadow-lg">
              {results.rows.map((row, index) => (
                <button
                  key={row.id}
                  onMouseEnter={() => setHighlight(index)}
                  onClick={() => addById(row.id)}
                  className={`flex w-full items-center justify-between px-3 py-2 text-left ${index === highlight ? "bg-brand-soft" : ""}`}
                >
                  <span>
                    <span className="font-medium">{row.name}</span> <span className="text-muted">{row.strength}</span>
                    {row.generic_name && <span className="ml-2 text-xs text-muted">{row.generic_name}</span>}
                  </span>
                  <span className="num flex items-center gap-3 text-[13px]">
                    {row.sellable > 0 ? (
                      <span className="text-muted">{qty(row.sellable)} {row.base_unit_name.toLowerCase()}s</span>
                    ) : (
                      <Badge tone="danger">out of stock</Badge>
                    )}
                    <span className="w-16 text-right font-medium">{money(row.retail_price)}</span>
                  </span>
                </button>
              ))}
              {!results.loading && results.rows.length === 0 && <p className="px-3 py-3 text-muted">No medicine found.</p>}
            </Card>
          )}
        </div>
        <div className="mt-2 space-y-2">
          <Notice tone="warn">{message}</Notice>
          <Notice>{quoteError}</Notice>
        </div>

        <Card className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[620px] text-left">
            <thead>
              <tr className="border-b border-line text-xs tracking-wide text-muted uppercase">
                <th className="px-3 py-2.5 font-medium">Medicine</th>
                <th className="px-2 py-2.5 font-medium">Unit</th>
                <th className="px-2 py-2.5 font-medium">Qty</th>
                <th className="px-2 py-2.5 text-right font-medium">Price</th>
                <th className="px-2 py-2.5 font-medium">Discount</th>
                <th className="px-3 py-2.5 text-right font-medium">Total</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {resuming
                ? resuming.items.map((item) => (
                    <tr key={item.id} className="border-b border-line/70 last:border-0">
                      <td className="px-3 py-2.5 font-medium">{item.product_name}</td>
                      <td className="px-2">{item.packaging_name}</td>
                      <td className="num px-2">{item.quantity}</td>
                      <td className="num px-2 text-right">{money(item.unit_price)}</td>
                      <td className="num px-2">{money(item.discount_amount)}</td>
                      <td className="num px-3 text-right font-medium">{money(item.line_total)}</td>
                      <td />
                    </tr>
                  ))
                : cart.map((line, index) => {
                    const priced = quote?.items[index];
                    const short = priced && priced.quantity_base > priced.available_base;
                    return (
                      <tr key={`${line.product.id}-${line.packaging}`} className="border-b border-line/70 last:border-0">
                        <td className="px-3 py-2">
                          <p className="font-medium">
                            {line.product.name} <span className="font-normal text-muted">{line.product.strength}</span>
                            {line.product.requires_prescription && <span className="ml-2"><Badge tone="warn">Rx</Badge></span>}
                          </p>
                          {short && (
                            <p className="text-xs text-danger">
                              Only {qty(priced.available_base)} {line.product.base_unit_name.toLowerCase()}(s) can be sold.
                            </p>
                          )}
                        </td>
                        <td className="px-2">
                          <Select
                            aria-label="Unit"
                            value={line.packaging}
                            onChange={(e) => updateLine(index, { packaging: Number(e.target.value) })}
                            className="h-8 w-32"
                          >
                            {line.product.packagings.filter((p) => p.can_sell).map((p) => (
                              <option key={p.id} value={p.id}>
                                {p.unit_name}{p.factor > 1 ? ` ×${p.factor}` : ""}
                              </option>
                            ))}
                          </Select>
                        </td>
                        <td className="px-2">
                          <Input
                            aria-label="Quantity"
                            type="number"
                            min={1}
                            step={1}
                            value={line.quantity}
                            onChange={(e) => updateLine(index, { quantity: Math.max(1, Math.floor(Number(e.target.value) || 1)) })}
                            className="num h-8 w-20"
                          />
                        </td>
                        <td className="num px-2 text-right">{priced ? money(priced.unit_price) : "…"}</td>
                        <td className="px-2">
                          <Input
                            aria-label="Line discount"
                            inputMode="decimal"
                            placeholder="0.00"
                            value={line.discount}
                            onChange={(e) => updateLine(index, { discount: e.target.value.replace(/[^\d.]/g, "") })}
                            className="num h-8 w-20"
                          />
                        </td>
                        <td className="num px-3 text-right font-medium">{priced ? money(priced.line_total) : "…"}</td>
                        <td className="pr-2">
                          <button
                            aria-label={`Remove ${line.product.name}`}
                            onClick={() => (setCart((lines) => lines.filter((_, i) => i !== index)), focusSearch())}
                            className="rounded p-1.5 text-muted hover:bg-danger-soft hover:text-danger"
                          >
                            ✕
                          </button>
                        </td>
                      </tr>
                    );
                  })}
            </tbody>
          </table>
          {cart.length === 0 && !resuming && (
            <p className="px-3 py-14 text-center text-muted">Scan or search to add the first item.</p>
          )}
        </Card>
        <p className="mt-2 text-xs text-muted">F2 search · ↑ ↓ Enter pick · F8 hold · F9 complete</p>
      </section>

      <aside>
        <Card className="sticky top-6 space-y-3 p-4">
          {resuming && <Notice tone="warn">Resuming held invoice #{resuming.id}. Take payment to complete it.</Notice>}
          <Field label="Customer">
            <Select value={resuming ? String(resuming.customer ?? "") : customer} onChange={(e) => setCustomer(e.target.value)} disabled={Boolean(resuming)}>
              <option value="">Walk-in customer</option>
              {customers.rows.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}{c.phone ? ` · ${c.phone}` : ""}
                </option>
              ))}
            </Select>
          </Field>
          {!resuming && (
            <Field label="Invoice discount">
              <Input inputMode="decimal" placeholder="0.00" value={invoiceDiscount} onChange={(e) => setInvoiceDiscount(e.target.value.replace(/[^\d.]/g, ""))} className="num" />
            </Field>
          )}
          {(needsPrescription || resuming) && (
            <Field label="Prescription reference" hint={needsPrescription ? "Required: this invoice has prescription-only medicine." : undefined}>
              <Input value={prescription} onChange={(e) => setPrescription(e.target.value)} placeholder="Doctor / Rx number" />
            </Field>
          )}

          <dl className="num grid grid-cols-2 gap-y-1 border-t border-line pt-3">
            <dt className="text-muted">Subtotal</dt>
            <dd className="text-right">{money(resuming?.subtotal ?? quote?.subtotal)}</dd>
            <dt className="text-muted">Discount</dt>
            <dd className="text-right">{money(-Number(resuming?.discount_total ?? quote?.discount_total ?? 0) || 0)}</dd>
            <dt className="text-muted">Tax (included)</dt>
            <dd className="text-right">{money(resuming?.tax_total ?? quote?.tax_total)}</dd>
            <dt className="pt-1 text-base font-semibold">Total</dt>
            <dd className="pt-1 text-right text-2xl font-semibold tracking-tight">{money(total)}</dd>
          </dl>

          <div className="space-y-2 border-t border-line pt-3">
            {payments.map((payment, index) => (
              <div key={index} className="flex gap-2">
                <Select
                  aria-label="Payment method"
                  value={payment.method}
                  onChange={(e) => setPayments((rows) => rows.map((r, i) => (i === index ? { ...r, method: e.target.value as PaymentMethod } : r)))}
                  className="w-28"
                >
                  {METHODS.map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </Select>
                <Input
                  aria-label="Amount"
                  inputMode="decimal"
                  placeholder="0.00"
                  value={payment.amount}
                  onChange={(e) => setPayments((rows) => rows.map((r, i) => (i === index ? { ...r, amount: e.target.value.replace(/[^\d.]/g, "") } : r)))}
                  onKeyDown={(e) => e.key === "Enter" && complete()}
                  className="num"
                />
                {payments.length > 1 && (
                  <button aria-label="Remove payment" onClick={() => setPayments((rows) => rows.filter((_, i) => i !== index))} className="px-1 text-muted hover:text-danger">
                    ✕
                  </button>
                )}
              </div>
            ))}
            <div className="flex justify-between text-[13px]">
              <button
                className="font-medium text-brand hover:underline"
                onClick={() => setPayments((rows) => rows.map((r, i) => (i === rows.length - 1 ? { ...r, amount: Math.max(total - (paid - (Number(r.amount) || 0)), 0).toFixed(2) } : r)))}
              >
                Fill exact amount
              </button>
              <button className="font-medium text-brand hover:underline" onClick={() => setPayments((rows) => [...rows, { method: "card", amount: "" }])}>
                + Split payment
              </button>
            </div>
            <p className={`num flex justify-between font-medium ${change < 0 ? "text-danger" : "text-ok"}`}>
              <span>{change < 0 ? "Still to pay" : "Change"}</span>
              <span>{money(Math.abs(change))}</span>
            </p>
          </div>

          <Notice>{error}</Notice>
          <Button size="lg" className="w-full" disabled={!canPay || busy} onClick={complete}>
            {busy ? "Saving…" : "Complete sale (F9)"}
          </Button>
          <div className="flex gap-2">
            <Button variant="secondary" className="flex-1" disabled={cart.length === 0 || Boolean(resuming) || busy} onClick={hold}>
              Hold (F8)
            </Button>
            <Button variant="ghost" className="flex-1" onClick={reset}>Clear</Button>
          </div>
        </Card>
      </aside>

      {receipt && <ReceiptModal sale={receipt} onClose={() => (setReceipt(null), focusSearch())} />}
      {showHeld && (
        <HeldModal
          onClose={() => setShowHeld(false)}
          onResume={(sale) => {
            reset();
            setResuming(sale);
            setPrescription(sale.prescription_reference);
            setShowHeld(false);
          }}
        />
      )}
    </div>
  );
}

function HeldModal({ onClose, onResume }: { onClose: () => void; onResume: (sale: Sale) => void }) {
  const held = useList<SaleSummary>("/sales/", { status: "held" });
  const { error, run } = useAction();
  return (
    <Modal title="Held invoices" onClose={onClose}>
      <Notice>{error ?? held.error}</Notice>
      <ul className="divide-y divide-line/70">
        {held.rows.map((sale) => (
          <li key={sale.id} className="flex items-center justify-between gap-3 py-2.5">
            <div>
              <p className="font-medium">#{sale.id} · {sale.customer_name || "Walk-in"}</p>
              <p className="text-xs text-muted">{dateTime(sale.created_at)} · {sale.cashier_name}</p>
            </div>
            <span className="num font-medium">{money(sale.total)}</span>
            <span className="flex gap-1.5">
              <Button size="sm" onClick={async () => { const full = await run(() => api<Sale>(`/sales/${sale.id}/`)); if (full) onResume(full); }}>
                Resume
              </Button>
              <Button size="sm" variant="ghost" onClick={async () => { await run(() => api(`/sales/${sale.id}/discard/`, { method: "POST" })); held.reload(); }}>
                Discard
              </Button>
            </span>
          </li>
        ))}
      </ul>
      {!held.loading && held.rows.length === 0 && <p className="py-6 text-center text-muted">No invoices on hold.</p>}
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
          footer={<Button disabled={busy} onClick={submit}>{shift ? "Close shift" : "Open shift"}</Button>}
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
              <Input autoFocus inputMode="decimal" value={cash} onChange={(e) => setCash(e.target.value.replace(/[^\d.]/g, ""))} className="num" placeholder="0.00" />
            </Field>
          </div>
        </Modal>
      )}
    </>
  );
}
