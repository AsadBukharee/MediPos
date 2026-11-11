"use client";

import { useState } from "react";
import { Button, Field, Input, Modal, Notice, Select } from "@/components/ui";
import { api, newKey } from "@/lib/api";
import { money } from "@/lib/format";
import { useAction } from "@/lib/hooks";

/** Record a payment to a supplier or from a customer. */
export function PaymentModal({ kind, party, onClose }: { kind: "supplier" | "customer"; party: { id: number; name: string; balance: string }; onClose: () => void }) {
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState("cash");
  const [reference, setReference] = useState("");
  const [key] = useState(newKey);
  const { busy, error, run } = useAction();
  const save = async () => {
    const done = await run(() =>
      api(`/${kind}s/payments/`, { body: { [kind]: party.id, amount, method, reference }, idempotencyKey: key }),
    );
    if (done) onClose();
  };
  return (
    <Modal
      title={kind === "supplier" ? `Pay ${party.name}` : `Receive payment from ${party.name}`}
      onClose={onClose}
      footer={<Button disabled={busy || !(Number(amount) > 0)} onClick={save}>Save payment</Button>}
    >
      <div className="space-y-3">
        <Notice>{error}</Notice>
        <p className="text-muted">Outstanding balance: <span className="num font-medium text-ink">{money(party.balance)}</span></p>
        <Field label="Amount"><Input autoFocus inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value.replace(/[^\d.]/g, ""))} className="num" /></Field>
        <Field label="Method">
          <Select value={method} onChange={(e) => setMethod(e.target.value)}>
            <option value="cash">Cash</option>
            <option value="bank">Bank transfer</option>
            <option value="card">Card</option>
            <option value="wallet">Mobile wallet</option>
          </Select>
        </Field>
        <Field label="Reference"><Input value={reference} onChange={(e) => setReference(e.target.value)} placeholder="Cheque / transaction no." /></Field>
      </div>
    </Modal>
  );
}
