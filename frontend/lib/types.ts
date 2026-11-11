// Contracts returned by the MediPos API (see docs/openapi.yaml). Money and prices are decimal strings.

export interface Branch {
  id: number;
  name: string;
  code: string;
  kind: "store" | "warehouse";
}

export interface User {
  id: number;
  username: string;
  first_name: string;
  last_name: string;
  email: string;
  role: string;
  max_discount_percent: string;
  permissions: string[];
  branches: Branch[];
}

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface Packaging {
  id: number;
  unit: number;
  unit_name: string;
  factor: number;
  is_default_sale: boolean;
  is_default_purchase: boolean;
  can_sell: boolean;
}

export interface Barcode {
  id: number;
  product: number;
  packaging: number | null;
  code: string;
  is_primary: boolean;
}

export interface Product {
  id: number;
  name: string;
  generic_name: string;
  brand: string;
  strength: string;
  dosage_form: string;
  sku: string;
  category: number | null;
  category_name: string;
  manufacturer: number | null;
  manufacturer_name: string;
  requires_prescription: boolean;
  is_active: boolean;
  base_unit: number;
  base_unit_name: string;
  purchase_price: string;
  retail_price: string;
  wholesale_price: string;
  tax_rate: string;
  reorder_level: number;
  min_stock: number;
  max_stock: number;
  preferred_supplier: number | null;
  packagings: Packaging[];
  barcodes: Barcode[];
  scanned_packaging?: number | null;
}

export interface Named {
  id: number;
  name: string;
}

export interface Unit extends Named {
  abbreviation: string;
}

export interface StockRow {
  id: number;
  name: string;
  generic_name: string;
  strength: string;
  sku: string;
  base_unit_name: string;
  retail_price: string;
  reorder_level: number;
  on_hand: number;
  sellable: number;
  nearest_expiry: string | null;
  state: "ok" | "low" | "out";
}

export interface Batch {
  id: number;
  product: number;
  product_name: string;
  batch_number: string;
  expiry_date: string;
  purchase_cost: string;
  selling_price: string | null;
  quantity_on_hand: number;
  status: "active" | "blocked" | "quarantined";
  is_expired: boolean;
}

export interface QuoteLine {
  product: number;
  product_name: string;
  packaging: number;
  packaging_name: string;
  quantity: number;
  quantity_base: number;
  unit_price: string;
  discount_amount: string;
  tax_amount: string;
  line_total: string;
  available_base: number;
}

export interface Quote {
  subtotal: string;
  discount_total: string;
  tax_total: string;
  total: string;
  requires_prescription: boolean;
  items: QuoteLine[];
}

export type PaymentMethod = "cash" | "card" | "bank" | "wallet" | "credit";

export interface SaleItem {
  id: number;
  product: number;
  product_name: string;
  packaging_name: string;
  quantity: number;
  quantity_base: number;
  unit_price: string;
  discount_amount: string;
  tax_amount: string;
  line_total: string;
  returned_base: number;
}

export interface Sale {
  id: number;
  number: string | null;
  status: "held" | "completed" | "cancelled";
  branch_name: string;
  customer: number | null;
  customer_name: string;
  cashier_name: string;
  subtotal: string;
  discount_total: string;
  tax_total: string;
  total: string;
  paid_total: string;
  change_due: string;
  prescription_reference: string;
  created_at: string;
  completed_at: string | null;
  items: SaleItem[];
  payments: { method: PaymentMethod; amount: string; reference: string }[];
}

export type SaleSummary = Pick<
  Sale,
  "id" | "number" | "status" | "customer_name" | "cashier_name" | "total" | "paid_total" | "created_at" | "completed_at"
>;

export interface Supplier {
  id: number;
  name: string;
  contact_person: string;
  phone: string;
  email: string;
  address: string;
  opening_balance: string;
  is_active: boolean;
  balance: string;
}

export interface Customer {
  id: number;
  name: string;
  phone: string;
  price_tier: "retail" | "wholesale";
  credit_limit: string;
  balance: string;
  is_active: boolean;
}

export interface GrnItem {
  id?: number;
  product: number;
  product_name?: string;
  packaging: number;
  packaging_name?: string;
  quantity: number;
  unit_cost: string;
  batch_number: string;
  expiry_date: string;
}

export interface Grn {
  id: number;
  number: string;
  supplier: number;
  supplier_name: string;
  status: "draft" | "confirmed" | "cancelled";
  supplier_invoice_number: string;
  total: string;
  created_at: string;
  confirmed_at: string | null;
  items: GrnItem[];
}

export interface PurchaseOrder {
  id: number;
  number: string;
  supplier_name: string;
  status: string;
  expected_date: string | null;
  total: string;
  created_at: string;
  items: { id: number; product_name: string; packaging_name: string; quantity: number; unit_price: string; received_base: number }[];
}

export interface RequisitionItem {
  id: number;
  product: number;
  product_name: string;
  quantity: number;
  supplier: number | null;
  supplier_name: string;
  requested_by_name: string;
}

export interface Requisition {
  id: number | null;
  number?: string;
  status: string;
  created_at?: string;
  items: RequisitionItem[];
}

export interface StockAlert {
  id: number;
  product: number;
  product_name: string;
  base_unit_name: string;
  reorder_level: number;
  kind: "low_stock" | "out_of_stock";
  status: "open" | "added" | "skipped" | "resolved";
  triggered_quantity: number;
  suggested_quantity: number;
  requested_quantity: number | null;
  created_at: string;
}

export interface Dashboard {
  today_sales: string;
  today_invoices: number;
  month_revenue: string;
  month_gross_profit: string;
  month_purchases: string;
  stock_value: string;
  low_stock_count: number;
  out_of_stock_count: number;
  near_expiry_count: number;
  expired_count: number;
  supplier_payables: string;
  customer_receivables: string;
  top_products: { key: number; label: string; quantity: number; revenue: string; profit: string }[];
  sales_chart: { label: string; invoices: number; total: string; profit: string }[];
}

export type Row = Record<string, string | number | null>;
