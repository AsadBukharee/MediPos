"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { SearchSelect, type SelectOption } from "@/components/search-select";
import { Badge, Button, Card, Field, Input, Modal, Notice, Select } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { date, money, qty } from "@/lib/format";
import { useAction, useDebounced, useGlobalKeys, useList } from "@/lib/hooks";
import { PAYMENT_METHODS, type Cart, type CartLine } from "@/lib/pos";
import type { Batch, Customer, PaymentMethod, Product, Quote, Sale, StockRow } from "@/lib/types";

const looksLikeBarcode = (text: string) => /^\d{6,14}$/.test(text);

/** One customer's cart: search, lines, totals and payment. The server prices everything. */
export function Till({
  cart,
  onChange,
  onCompleted,
  onHeld,
  customers,
  onCustomerAdded,
}: {
  cart: Cart;
  onChange: (patch: Partial<Cart>) => void;
  onCompleted: (sale: Sale) => void;
  onHeld: () => void;
  customers: Customer[];
  onCustomerAdded: () => void;
}) {
  const { can } = useAuth();
  const searchRef = useRef<HTMLInputElement>(null);
  const [term, setTerm] = useState("");
  const [highlight, setHighlight] = useState(0);
  const [priced, setPriced] = useState<Quote | null>(null);
  const [pricingError, setPricingError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [addingCustomer, setAddingCustomer] = useState(false);
  const { busy, error, run, setError } = useAction();

  const debouncedTerm = useDebounced(term.trim(), 200);
  const results = useList<StockRow>(
    debouncedTerm.length >= 2 && !looksLikeBarcode(debouncedTerm) ? "/inventory/stock/" : null,
    { search: debouncedTerm, is_active: true, page_size: 8 },
  );
  const focusSearch = useCallback(() => searchRef.current?.focus(), []);
  const { lines, resuming } = cart;

  const addProduct = useCallback(
    (product: Product, packagingId?: number | null) => {
      const sellable = product.packagings.filter((p) => p.can_sell);
      const packaging = sellable.find((p) => p.id === packagingId) ?? sellable.find((p) => p.is_default_sale) ?? sellable[0];
      if (!packaging) {
        setMessage(`${product.name} has no sellable unit configured.`);
        return;
      }
      setMessage(null);
      const index = lines.findIndex((line) => line.product.id === product.id && line.packaging === packaging.id);
      onChange({
        lines:
          index >= 0
            ? lines.map((line, position) => (position === index ? { ...line, quantity: line.quantity + 1 } : line))
            : [...lines, { product, packaging: packaging.id, quantity: 1, discount: "", batch: null }],
      });
      setTerm("");
      setHighlight(0);
      focusSearch();
    },
    [lines, onChange, focusSearch],
  );

  const addById = useCallback(
    async (id: number) => {
      try {
        addProduct(await api<Product>(`/catalog/products/${id}/`));
      } catch (problem) {
        setMessage((problem as ApiError).message);
      }
    },
    [addProduct],
  );

  const scan = useCallback(
    async (code: string) => {
      try {
        const product = await api<Product>("/catalog/products/lookup/", { params: { barcode: code } });
        addProduct(product, product.scanned_packaging);
      } catch (problem) {
        setMessage((problem as ApiError).status === 404 ? `No medicine matches barcode ${code}.` : (problem as ApiError).message);
        setTerm("");
      }
    },
    [addProduct],
  );

  const updateLine = (index: number, patch: Partial<CartLine>) =>
    onChange({ lines: lines.map((line, position) => (position === index ? { ...line, ...patch } : line)) });

  const payload = useMemo(
    () => ({
      customer: cart.customer ? Number(cart.customer) : null,
      invoice_discount: cart.invoiceDiscount || "0",
      items: lines.map((line) => ({
        product: line.product.id,
        packaging: line.packaging,
        quantity: line.quantity,
        discount_amount: line.discount || "0",
        batch: line.batch,
      })),
    }),
    [lines, cart.customer, cart.invoiceDiscount],
  );
  const debouncedPayload = useDebounced(payload, 250);
  // An empty cart has no quote, whatever the last answer from the server was.
  const quote = lines.length > 0 ? priced : null;
  const quoteError = lines.length > 0 ? pricingError : null;

  // The server prices the cart; the POS only displays what comes back.
  useEffect(() => {
    if (resuming || debouncedPayload.items.length === 0) return;
    let current = true;
    api<Quote>("/sales/quote/", { body: debouncedPayload })
      .then((answer) => {
        if (!current) return;
        setPriced(answer);
        setPricingError(null);
      })
      .catch((problem: ApiError) => {
        if (current) setPricingError(problem.message);
      });
    return () => {
      current = false;
    };
  }, [debouncedPayload, resuming]);

  const total = Number(resuming ? resuming.total : (quote?.total ?? 0));
  const paid = cart.payments.reduce((sum, payment) => sum + (Number(payment.amount) || 0), 0);
  const change = paid - total;
  const needsPrescription = !resuming && Boolean(quote?.requires_prescription);
  const stale = !resuming && debouncedPayload !== payload;
  const canPay = (resuming || (lines.length > 0 && quote && !quoteError && !stale)) && paid >= total && total > 0;
  const chosenCustomer = customers.find((entry) => String(entry.id) === cart.customer);
  const owes = chosenCustomer ? Number(chosenCustomer.balance) : 0;

  const cleanPayments = () =>
    cart.payments.filter((payment) => Number(payment.amount) > 0).map(({ method, amount }) => ({ method, amount }));

  const complete = useCallback(async () => {
    if (!canPay || busy) return;
    const sale = await run(() =>
      resuming
        ? api<Sale>(`/sales/${resuming.id}/complete/`, {
            body: { payments: cleanPayments(), prescription_reference: cart.prescription },
          })
        : api<Sale>("/sales/", {
            body: { ...payload, payments: cleanPayments(), prescription_reference: cart.prescription },
            idempotencyKey: cart.key, // a double click or a network retry cannot bill twice
          }),
    );
    if (sale) onCompleted(sale);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canPay, busy, resuming, payload, cart.payments, cart.prescription, cart.key, run, onCompleted]);

  const hold = useCallback(async () => {
    if (lines.length === 0 || resuming || busy) return;
    const held = await run(() =>
      api<Sale>("/sales/", { body: { ...payload, hold: true, prescription_reference: cart.prescription } }),
    );
    if (held) onHeld();
  }, [lines.length, resuming, busy, run, payload, cart.prescription, onHeld]);

  useGlobalKeys((event) => {
    const action = { F2: focusSearch, F8: hold, F9: complete }[event.key];
    if (!action) return;
    event.preventDefault();
    action();
  });

  const onSearchKey = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const step = event.key === "ArrowDown" ? 1 : -1;
      setHighlight((current) => Math.min(Math.max(current + step, 0), Math.max(results.rows.length - 1, 0)));
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

  const customerOptions: SelectOption[] = customers.map((entry) => ({
    value: String(entry.id),
    label: entry.name,
    hint: entry.phone || (Number(entry.credit_limit) > 0 ? "account" : undefined),
  }));

  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_22rem]">
      <section className="min-w-0">
        <div className="relative">
          <Input
            ref={searchRef}
            value={term}
            onChange={(event) => (setTerm(event.target.value), setHighlight(0))}
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
                      <span className="text-muted">
                        {qty(row.sellable)} {row.base_unit_name.toLowerCase()}s
                      </span>
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
          <table className="w-full min-w-[720px] text-left">
            <thead>
              <tr className="border-b border-line text-xs tracking-wide text-muted uppercase">
                <th className="px-3 py-2.5 font-medium">Medicine</th>
                <th className="px-2 py-2.5 font-medium">Unit</th>
                <th className="px-2 py-2.5 font-medium">Qty</th>
                <th className="px-2 py-2.5 font-medium">Batch</th>
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
                      <td className="px-2 text-muted">auto</td>
                      <td className="num px-2 text-right">{money(item.unit_price)}</td>
                      <td className="num px-2">{money(item.discount_amount)}</td>
                      <td className="num px-3 text-right font-medium">{money(item.line_total)}</td>
                      <td />
                    </tr>
                  ))
                : lines.map((line, index) => {
                    const pricedLine = quote?.items[index];
                    const short = pricedLine && pricedLine.quantity_base > pricedLine.available_base;
                    return (
                      <tr key={`${line.product.id}-${line.packaging}`} className="border-b border-line/70 last:border-0">
                        <td className="px-3 py-2">
                          <p className="font-medium">
                            {line.product.name} <span className="font-normal text-muted">{line.product.strength}</span>
                            {line.product.requires_prescription && (
                              <span className="ml-2">
                                <Badge tone="warn">Rx</Badge>
                              </span>
                            )}
                          </p>
                          {short && (
                            <p className="text-xs text-danger">
                              Only {qty(pricedLine.available_base)} {line.product.base_unit_name.toLowerCase()}(s) can be sold.
                            </p>
                          )}
                        </td>
                        <td className="px-2">
                          <Select
                            aria-label="Unit"
                            value={line.packaging}
                            onChange={(event) => updateLine(index, { packaging: Number(event.target.value) })}
                            className="h-8 w-32"
                          >
                            {line.product.packagings
                              .filter((pack) => pack.can_sell)
                              .map((pack) => (
                                <option key={pack.id} value={pack.id}>
                                  {pack.unit_name}
                                  {pack.factor > 1 ? ` ×${pack.factor}` : ""}
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
                            onChange={(event) =>
                              updateLine(index, { quantity: Math.max(1, Math.floor(Number(event.target.value) || 1)) })
                            }
                            className="num h-8 w-20"
                          />
                        </td>
                        <td className="px-2">
                          <BatchPicker
                            productId={line.product.id}
                            value={line.batch}
                            onChange={(batch) => updateLine(index, { batch })}
                          />
                        </td>
                        <td className="num px-2 text-right">{pricedLine ? money(pricedLine.unit_price) : "…"}</td>
                        <td className="px-2">
                          <Input
                            aria-label="Line discount"
                            inputMode="decimal"
                            placeholder="0.00"
                            value={line.discount}
                            onChange={(event) => updateLine(index, { discount: event.target.value.replace(/[^\d.]/g, "") })}
                            className="num h-8 w-20"
                          />
                        </td>
                        <td className="num px-3 text-right font-medium">{pricedLine ? money(pricedLine.line_total) : "…"}</td>
                        <td className="pr-2">
                          <button
                            aria-label={`Remove ${line.product.name}`}
                            onClick={() => (onChange({ lines: lines.filter((_, position) => position !== index) }), focusSearch())}
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
          {lines.length === 0 && !resuming && <p className="px-3 py-14 text-center text-muted">Scan or search to add the first item.</p>}
        </Card>
      </section>

      <aside>
        <Card className="sticky top-6 space-y-3 p-4">
          {resuming && <Notice tone="warn">Resuming held invoice #{resuming.id}. Take payment to complete it.</Notice>}
          <Field label="Customer">
            <SearchSelect
              label="Customer"
              className="w-full"
              value={resuming ? String(resuming.customer ?? "") : cart.customer}
              onChange={(value) => onChange({ customer: value })}
              options={customerOptions}
              emptyLabel="Walk-in customer"
              disabled={Boolean(resuming)}
              footer={
                can("customers.manage")
                  ? (close) => (
                      <button
                        className="w-full rounded px-2 py-1 text-left text-[13px] font-medium text-brand hover:bg-canvas"
                        onClick={() => (close(), setAddingCustomer(true))}
                      >
                        + New customer
                      </button>
                    )
                  : undefined
              }
            />
          </Field>
          {chosenCustomer && (owes > 0 || Number(chosenCustomer.credit_limit) > 0) && (
            <p className="num -mt-1 text-[13px] text-muted">
              Owes {money(owes)} of {money(chosenCustomer.credit_limit)} limit
            </p>
          )}
          {!resuming && (
            <Field label="Invoice discount">
              <Input
                inputMode="decimal"
                placeholder="0.00"
                value={cart.invoiceDiscount}
                onChange={(event) => onChange({ invoiceDiscount: event.target.value.replace(/[^\d.]/g, "") })}
                className="num"
              />
            </Field>
          )}
          {(needsPrescription || resuming) && (
            <Field
              label="Prescription reference"
              hint={needsPrescription ? "Required: this invoice has prescription-only medicine." : undefined}
            >
              <Input
                value={cart.prescription}
                onChange={(event) => onChange({ prescription: event.target.value })}
                placeholder="Doctor / Rx number"
              />
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
            {cart.payments.map((payment, index) => (
              <div key={index} className="flex gap-2">
                <Select
                  aria-label="Payment method"
                  value={payment.method}
                  onChange={(event) =>
                    onChange({
                      payments: cart.payments.map((row, position) =>
                        position === index ? { ...row, method: event.target.value as PaymentMethod } : row,
                      ),
                    })
                  }
                  className="w-28"
                >
                  {PAYMENT_METHODS.map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </Select>
                <Input
                  aria-label="Amount"
                  inputMode="decimal"
                  placeholder="0.00"
                  value={payment.amount}
                  onChange={(event) =>
                    onChange({
                      payments: cart.payments.map((row, position) =>
                        position === index ? { ...row, amount: event.target.value.replace(/[^\d.]/g, "") } : row,
                      ),
                    })
                  }
                  onKeyDown={(event) => event.key === "Enter" && complete()}
                  className="num"
                />
                {cart.payments.length > 1 && (
                  <button
                    aria-label="Remove payment"
                    onClick={() => onChange({ payments: cart.payments.filter((_, position) => position !== index) })}
                    className="px-1 text-muted hover:text-danger"
                  >
                    ✕
                  </button>
                )}
              </div>
            ))}
            <div className="flex justify-between text-[13px]">
              <button
                className="font-medium text-brand hover:underline"
                onClick={() =>
                  onChange({
                    payments: cart.payments.map((row, index) =>
                      index === cart.payments.length - 1
                        ? { ...row, amount: Math.max(total - (paid - (Number(row.amount) || 0)), 0).toFixed(2) }
                        : row,
                    ),
                  })
                }
              >
                Fill exact amount
              </button>
              <button
                className="font-medium text-brand hover:underline"
                onClick={() => onChange({ payments: [...cart.payments, { method: "card", amount: "" }] })}
              >
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
            <Button variant="secondary" className="flex-1" disabled={lines.length === 0 || Boolean(resuming) || busy} onClick={hold}>
              Park on server (F8)
            </Button>
            <Button
              variant="ghost"
              className="flex-1"
              onClick={() => {
                onChange({ lines: [], customer: "", invoiceDiscount: "", prescription: "", payments: [{ method: "cash", amount: "" }], resuming: null });
                setPriced(null);
                setError(null);
                focusSearch();
              }}
            >
              Clear
            </Button>
          </div>
        </Card>
      </aside>

      {addingCustomer && (
        <QuickCustomer
          onClose={() => setAddingCustomer(false)}
          onCreated={(created) => {
            setAddingCustomer(false);
            onCustomerAdded();
            onChange({ customer: String(created.id) });
          }}
        />
      )}
    </div>
  );
}

/** First expiry first by default; a pharmacist can name the batch when a customer needs one. */
function BatchPicker({
  productId,
  value,
  onChange,
}: {
  productId: number;
  value: number | null;
  onChange: (batch: number | null) => void;
}) {
  const [opened, setOpened] = useState(false);
  const batches = useList<Batch>(opened ? `/inventory/stock/${productId}/batches/` : null);
  const sellable = batches.rows.filter((batch) => !batch.is_expired && batch.status === "active" && batch.quantity_on_hand > 0);
  return (
    <SearchSelect
      label="Batch"
      className="w-36"
      value={value === null ? "" : String(value)}
      onChange={(next) => onChange(next ? Number(next) : null)}
      onOpenChange={(open) => open && setOpened(true)}
      loading={batches.loading}
      emptyLabel="Auto (FEFO)"
      options={sellable.map((batch) => ({
        value: String(batch.id),
        label: batch.batch_number,
        hint: `exp ${date(batch.expiry_date)} · ${qty(batch.quantity_on_hand)}`,
      }))}
    />
  );
}

function QuickCustomer({ onClose, onCreated }: { onClose: () => void; onCreated: (customer: Customer) => void }) {
  const [form, setForm] = useState({ name: "", phone: "", credit_limit: "0" });
  const { busy, error, run } = useAction();
  const save = async () => {
    const created = await run(() => api<Customer>("/customers/", { body: form }));
    if (created) onCreated(created);
  };
  return (
    <Modal
      title="New customer"
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={busy || !form.name.trim()} onClick={save}>
            Save and select
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <Notice>{error}</Notice>
        <Field label="Name">
          <Input autoFocus value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} />
        </Field>
        <Field label="Phone">
          <Input
            value={form.phone}
            onChange={(event) => setForm({ ...form, phone: event.target.value })}
            onKeyDown={(event) => event.key === "Enter" && save()}
          />
        </Field>
        <Field label="Credit limit" hint="Leave at 0 unless this customer buys on account.">
          <Input
            inputMode="decimal"
            className="num"
            value={form.credit_limit}
            onChange={(event) => setForm({ ...form, credit_limit: event.target.value.replace(/[^\d.]/g, "") })}
          />
        </Field>
      </div>
    </Modal>
  );
}
