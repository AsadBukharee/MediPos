"use client";

import { useState } from "react";
import { Button, Modal, Tabs } from "@/components/ui";
import { dateTime, money } from "@/lib/format";
import type { Sale } from "@/lib/types";

const BUSINESS = process.env.NEXT_PUBLIC_BUSINESS_NAME || "MediPos Pharmacy";

/** Printable invoice: 80mm thermal roll or A4. Reprinting uses the same component. */
export function ReceiptModal({ sale, onClose }: { sale: Sale; onClose: () => void }) {
  const [format, setFormat] = useState<"thermal" | "a4">("thermal");
  const thermal = format === "thermal";
  return (
    <Modal
      title={`Invoice ${sale.number ?? ""}`}
      onClose={onClose}
      wide={!thermal}
      footer={
        <>
          <Tabs value={format} onChange={setFormat} options={[["thermal", "80mm receipt"], ["a4", "A4 invoice"]]} />
          <span className="flex-1" />
          <Button variant="secondary" onClick={onClose}>Close</Button>
          <Button autoFocus onClick={() => window.print()}>Print</Button>
        </>
      }
    >
      <div className={`print-area mx-auto ${thermal ? "receipt-80" : "max-w-3xl text-[13px]"}`}>
        <div className={thermal ? "text-center" : "flex items-start justify-between"}>
          <div>
            <p className={thermal ? "text-sm font-bold" : "text-xl font-semibold"}>{BUSINESS}</p>
            <p>{sale.branch_name}</p>
          </div>
          <div className={thermal ? "mt-1" : "text-right"}>
            <p className="font-semibold">{sale.number}</p>
            <p>{dateTime(sale.completed_at ?? sale.created_at)}</p>
            <p>Cashier: {sale.cashier_name}</p>
            {sale.customer_name && <p>Customer: {sale.customer_name}</p>}
            {sale.prescription_reference && <p>Rx: {sale.prescription_reference}</p>}
          </div>
        </div>
        <table className="mt-3 w-full border-collapse">
          <thead>
            <tr className="border-y border-dashed border-current text-left">
              <th className="py-1 font-semibold">Item</th>
              <th className="py-1 text-right font-semibold">Qty</th>
              <th className="py-1 text-right font-semibold">Price</th>
              <th className="py-1 text-right font-semibold">Total</th>
            </tr>
          </thead>
          <tbody>
            {sale.items.map((item) => (
              <tr key={item.id} className="align-top">
                <td className="py-0.5 pr-1">{item.product_name}</td>
                <td className="num py-0.5 text-right whitespace-nowrap">
                  {item.quantity} {item.packaging_name.toLowerCase()}
                </td>
                <td className="num py-0.5 text-right">{money(item.unit_price)}</td>
                <td className="num py-0.5 text-right">{money(item.line_total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <dl className="num mt-2 ml-auto grid w-full max-w-64 grid-cols-2 gap-y-0.5 border-t border-dashed border-current pt-2">
          <dt>Subtotal</dt>
          <dd className="text-right">{money(sale.subtotal)}</dd>
          {Number(sale.discount_total) > 0 && (
            <>
              <dt>Discount</dt>
              <dd className="text-right">−{money(sale.discount_total)}</dd>
            </>
          )}
          {Number(sale.tax_total) > 0 && (
            <>
              <dt>Tax (incl.)</dt>
              <dd className="text-right">{money(sale.tax_total)}</dd>
            </>
          )}
          <dt className="text-[1.15em] font-bold">Total</dt>
          <dd className="text-right text-[1.15em] font-bold">{money(sale.total)}</dd>
          {sale.payments.map((payment, index) => (
            <span key={index} className="contents">
              <dt className="capitalize">{payment.method}</dt>
              <dd className="text-right">{money(payment.amount)}</dd>
            </span>
          ))}
          {Number(sale.change_due) > 0 && (
            <>
              <dt>Change</dt>
              <dd className="text-right">{money(sale.change_due)}</dd>
            </>
          )}
        </dl>
        <p className="mt-3 text-center">Thank you. Keep medicines out of reach of children.</p>
      </div>
    </Modal>
  );
}
