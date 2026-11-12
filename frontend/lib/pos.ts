import { newKey } from "@/lib/api";
import type { PaymentMethod, Product, Sale } from "@/lib/types";

export interface CartLine {
  product: Product;
  packaging: number;
  quantity: number;
  discount: string;
  /** A specific batch, when the pharmacist overrides first-expiry-first. */
  batch: number | null;
}

export interface PaymentRow {
  method: PaymentMethod;
  amount: string;
}

/** One customer at the counter. Several can be open at once; only completing one touches stock. */
export interface Cart {
  id: string;
  name: string;
  lines: CartLine[];
  customer: string;
  invoiceDiscount: string;
  prescription: string;
  payments: PaymentRow[];
  /** Set when this cart came from an invoice parked on the server. */
  resuming: Sale | null;
  /** Sent with the sale so a retry cannot bill the customer twice. */
  key: string;
}

export function newCart(name: string): Cart {
  return {
    id: newKey(),
    name,
    lines: [],
    customer: "",
    invoiceDiscount: "",
    prescription: "",
    payments: [{ method: "cash", amount: "" }],
    resuming: null,
    key: newKey(),
  };
}

export const cartIsEmpty = (cart: Cart) => cart.lines.length === 0 && !cart.resuming;

export const PAYMENT_METHODS: [PaymentMethod, string][] = [
  ["cash", "Cash"],
  ["card", "Card"],
  ["bank", "Bank transfer"],
  ["wallet", "Mobile wallet"],
  ["credit", "On account"],
];
