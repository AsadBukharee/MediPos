const CURRENCY = process.env.NEXT_PUBLIC_CURRENCY || "PKR";

// Display only: amounts stay decimal strings end to end, the server does all arithmetic.
export function money(value: string | number | null | undefined, withCurrency = false): string {
  const number = Number(value ?? 0);
  const text = number.toLocaleString("en-PK", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return withCurrency ? `${CURRENCY} ${text}` : text;
}

export const qty = (value: number | null | undefined) => Number(value ?? 0).toLocaleString("en-PK");

export function date(value: string | null | undefined): string {
  if (!value) return "—";
  return new Date(value).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}

export function dateTime(value: string | null | undefined): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function daysUntil(value: string | null | undefined): number | null {
  if (!value) return null;
  return Math.ceil((new Date(value).getTime() - Date.now()) / 86_400_000);
}

export const today = () => new Date().toISOString().slice(0, 10);

export const title = (text: string) => text.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
