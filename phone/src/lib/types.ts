// Mirrors the API contracts in docs/openapi.yaml (the web app keeps the same shapes in frontend/lib/types.ts).

export interface Branch {
  id: number;
  name: string;
  code: string;
}

export interface User {
  id: number;
  username: string;
  first_name: string;
  role: string;
  permissions: string[];
  branches: Branch[];
}

export interface Paginated<T> {
  count: number;
  results: T[];
}

export interface StockAlert {
  id: number;
  product: number;
  product_name: string;
  base_unit_name: string;
  reorder_level: number;
  kind: 'low_stock' | 'out_of_stock';
  status: 'open' | 'added' | 'skipped' | 'resolved';
  triggered_quantity: number;
  suggested_quantity: number;
  requested_quantity: number | null;
  created_at: string;
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
  state: 'ok' | 'low' | 'out';
}

export interface Batch {
  id: number;
  batch_number: string;
  expiry_date: string;
  quantity_on_hand: number;
  status: 'active' | 'blocked' | 'quarantined';
  is_expired: boolean;
}

export interface Product {
  id: number;
  name: string;
  strength: string;
  scanned_packaging?: number | null;
}

export interface RequisitionItem {
  id: number;
  product: number;
  product_name: string;
  quantity: number;
  supplier_name: string;
  requested_by_name: string;
}

export interface Requisition {
  id: number | null;
  number?: string;
  status: string;
  items: RequisitionItem[];
}

export interface AppNotification {
  id: number;
  type: string;
  title: string;
  body: string;
  data: Record<string, string | number>;
  is_read: boolean;
  created_at: string;
}

export interface Dashboard {
  today_sales: string;
  today_invoices: number;
  month_revenue: string;
  month_gross_profit: string;
  stock_value: string;
  low_stock_count: number;
  out_of_stock_count: number;
  near_expiry_count: number;
  expired_count: number;
}
