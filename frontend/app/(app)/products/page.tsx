"use client";

import { useState } from "react";
import { Badge, Button, DataTable, Field, Input, Modal, Notice, PageHeader, Select } from "@/components/ui";
import { api, download } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { money } from "@/lib/format";
import { useAction, useDebounced, useList } from "@/lib/hooks";
import type { Named, Product, Unit } from "@/lib/types";

export default function ProductsPage() {
  const { can } = useAuth();
  const [search, setSearch] = useState("");
  const [editing, setEditing] = useState<Product | "new" | null>(null);
  const [importing, setImporting] = useState(false);
  const products = useList<Product>("/catalog/products/", { search: useDebounced(search) });

  return (
    <>
      <PageHeader title="Medicines" subtitle={`${products.count} in the catalog`}>
        <Input placeholder="Name, generic, SKU or barcode" value={search} onChange={(e) => setSearch(e.target.value)} className="w-64" />
        <Button variant="secondary" onClick={() => download("/catalog/products/export/", { search }, "medicines.csv")}>Export CSV</Button>
        {can("catalog.manage") && (
          <>
            <Button variant="secondary" onClick={() => setImporting(true)}>Import CSV</Button>
            <Button onClick={() => setEditing("new")}>New medicine</Button>
          </>
        )}
      </PageHeader>
      <DataTable
        rows={products.rows}
        rowKey={(row) => row.id}
        loading={products.loading}
        error={products.error}
        onRowClick={can("catalog.manage") ? setEditing : undefined}
        columns={[
          {
            header: "Medicine",
            cell: (p) => (
              <>
                <span className="font-medium">{p.name}</span> <span className="text-muted">{p.strength} {p.dosage_form}</span>
                {p.requires_prescription && <span className="ml-2"><Badge tone="warn">Rx</Badge></span>}
                {!p.is_active && <span className="ml-2"><Badge>inactive</Badge></span>}
                <p className="text-xs text-muted">{p.generic_name}</p>
              </>
            ),
          },
          { header: "SKU", cell: (p) => <span className="font-mono text-[13px]">{p.sku}</span> },
          { header: "Category", cell: (p) => p.category_name || "—" },
          { header: "Packs", cell: (p) => p.packagings.map((k) => (k.factor > 1 ? `${k.unit_name} ×${k.factor}` : k.unit_name)).join(" · ") },
          { header: "Barcodes", cell: (p) => <span className="font-mono text-xs">{p.barcodes.map((b) => b.code).join(", ") || "—"}</span> },
          { header: "Price / unit", align: "right", cell: (p) => money(p.retail_price) },
          { header: "Reorder at", align: "right", cell: (p) => p.reorder_level || "—" },
        ]}
      />
      {editing && <ProductForm product={editing === "new" ? null : editing} onClose={() => (setEditing(null), products.reload())} />}
      {importing && <ImportModal onClose={() => (setImporting(false), products.reload())} />}
    </>
  );
}

interface PackRow {
  unit: string;
  factor: string;
}

function ProductForm({ product, onClose }: { product: Product | null; onClose: () => void }) {
  const units = useList<Unit>("/catalog/units/", { page_size: 200 });
  const categories = useList<Named>("/catalog/categories/", { page_size: 200 });
  const { busy, error, run } = useAction();
  const [form, setForm] = useState({
    name: product?.name ?? "",
    generic_name: product?.generic_name ?? "",
    strength: product?.strength ?? "",
    dosage_form: product?.dosage_form ?? "",
    sku: product?.sku ?? "",
    category: String(product?.category ?? ""),
    base_unit: String(product?.base_unit ?? ""),
    purchase_price: product?.purchase_price ?? "",
    retail_price: product?.retail_price ?? "",
    tax_rate: product?.tax_rate ?? "0",
    reorder_level: String(product?.reorder_level ?? 0),
    max_stock: String(product?.max_stock ?? 0),
    requires_prescription: product?.requires_prescription ?? false,
    is_active: product?.is_active ?? true,
  });
  const [packs, setPacks] = useState<PackRow[]>(
    product?.packagings.filter((p) => p.factor > 1).map((p) => ({ unit: String(p.unit), factor: String(p.factor) })) ?? [],
  );
  const [barcode, setBarcode] = useState("");
  const [allowDuplicate, setAllowDuplicate] = useState(false);
  const set = (patch: Partial<typeof form>) => setForm((f) => ({ ...f, ...patch }));
  const text = (name: keyof typeof form) => ({
    value: form[name] as string,
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => set({ [name]: e.target.value }),
  });

  const save = async () => {
    const body = {
      ...form,
      category: form.category ? Number(form.category) : null,
      base_unit: Number(form.base_unit),
      purchase_price: form.purchase_price || "0",
      retail_price: form.retail_price || "0",
      reorder_level: Number(form.reorder_level) || 0,
      max_stock: Number(form.max_stock) || 0,
      allow_duplicate: allowDuplicate,
      packagings: packs.filter((p) => p.unit && Number(p.factor) > 1).map((p) => ({ unit: Number(p.unit), factor: Number(p.factor) })),
    };
    const saved = await run(async () => {
      const result = product
        ? await api<Product>(`/catalog/products/${product.id}/`, { method: "PATCH", body })
        : await api<Product>("/catalog/products/", { body });
      if (barcode.trim()) await api("/catalog/barcodes/", { body: { product: result.id, code: barcode.trim(), is_primary: result.barcodes.length === 0 } });
      return result;
    });
    if (saved) onClose();
  };
  const generate = () => product && run(async () => (await api("/catalog/barcodes/generate/", { body: { product: product.id } }), onClose()));

  return (
    <Modal
      wide
      title={product ? `Edit ${product.name}` : "New medicine"}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button disabled={busy || !form.name || !form.sku || !form.base_unit} onClick={save}>Save</Button>
        </>
      }
    >
      <div className="space-y-4">
        <Notice>{error}</Notice>
        {error?.includes("already exists") && (
          <label className="flex items-center gap-2 text-[13px]">
            <input type="checkbox" checked={allowDuplicate} onChange={(e) => setAllowDuplicate(e.target.checked)} />
            This is a different product — save it anyway.
          </label>
        )}
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Name"><Input {...text("name")} autoFocus /></Field>
          <Field label="Generic name"><Input {...text("generic_name")} /></Field>
          <Field label="SKU"><Input {...text("sku")} /></Field>
          <Field label="Strength"><Input {...text("strength")} placeholder="500mg" /></Field>
          <Field label="Dosage form"><Input {...text("dosage_form")} placeholder="Tablet" /></Field>
          <Field label="Category">
            <Select {...text("category")}>
              <option value="">—</option>
              {categories.rows.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </Select>
          </Field>
        </div>

        <fieldset className="rounded-lg border border-line p-3">
          <legend className="px-1 text-[13px] font-medium text-muted">Units &amp; packaging</legend>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Base unit (smallest you sell)" hint={product ? "Cannot change after creation." : "Stock is counted in this unit."}>
              <Select {...text("base_unit")} disabled={Boolean(product)}>
                <option value="">Choose…</option>
                {units.rows.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
              </Select>
            </Field>
          </div>
          {packs.map((pack, index) => (
            <div key={index} className="mt-2 flex items-end gap-2">
              <Field label="Pack">
                <Select value={pack.unit} onChange={(e) => setPacks((rows) => rows.map((r, i) => (i === index ? { ...r, unit: e.target.value } : r)))}>
                  <option value="">Choose…</option>
                  {units.rows.filter((u) => String(u.id) !== form.base_unit).map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
                </Select>
              </Field>
              <Field label="Contains (base units)">
                <Input type="number" min={2} step={1} value={pack.factor} onChange={(e) => setPacks((rows) => rows.map((r, i) => (i === index ? { ...r, factor: e.target.value } : r)))} className="num" />
              </Field>
            </div>
          ))}
          <button className="mt-2 text-[13px] font-medium text-brand hover:underline" onClick={() => setPacks((rows) => [...rows, { unit: "", factor: "" }])}>
            + Add a pack (strip, box, carton…)
          </button>
        </fieldset>

        <div className="grid gap-3 sm:grid-cols-5">
          <Field label="Cost / base unit"><Input {...text("purchase_price")} inputMode="decimal" className="num" /></Field>
          <Field label="Price / base unit"><Input {...text("retail_price")} inputMode="decimal" className="num" /></Field>
          <Field label="Tax %"><Input {...text("tax_rate")} inputMode="decimal" className="num" /></Field>
          <Field label="Reorder level"><Input {...text("reorder_level")} type="number" min={0} className="num" /></Field>
          <Field label="Target stock"><Input {...text("max_stock")} type="number" min={0} className="num" /></Field>
        </div>
        <div className="grid items-end gap-3 sm:grid-cols-3">
          <Field label="Add barcode" hint={product?.barcodes.map((b) => b.code).join(", ")}>
            <Input value={barcode} onChange={(e) => setBarcode(e.target.value)} placeholder="Scan or type EAN / UPC" className="font-mono" />
          </Field>
          {product && <Button variant="secondary" disabled={busy} onClick={generate}>Generate in-store barcode</Button>}
        </div>
        <div className="flex gap-5">
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={form.requires_prescription} onChange={(e) => set({ requires_prescription: e.target.checked })} />
            Prescription required
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={form.is_active} onChange={(e) => set({ is_active: e.target.checked })} />
            Active
          </label>
        </div>
      </div>
    </Modal>
  );
}

function ImportModal({ onClose }: { onClose: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<{ created: number; updated: number; errors: { line: number; error: string }[] } | null>(null);
  const { busy, error, run } = useAction();
  const upload = async () => {
    if (!file) return;
    const body = new FormData();
    body.append("file", file);
    setResult((await run(() => api<NonNullable<typeof result>>("/catalog/products/import/", { body }))) ?? null);
  };
  return (
    <Modal title="Import medicines from CSV" onClose={onClose} footer={<Button disabled={!file || busy} onClick={upload}>Import</Button>}>
      <div className="space-y-3">
        <Notice>{error}</Notice>
        <p className="text-muted">Use the same columns as the export. Rows are matched by SKU: existing medicines are updated, new ones are created.</p>
        <input type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        {result && (
          <>
            <Notice tone="ok">{result.created} created, {result.updated} updated.</Notice>
            {result.errors.map((row) => <p key={row.line} className="text-[13px] text-danger">Line {row.line}: {row.error}</p>)}
          </>
        )}
      </div>
    </Modal>
  );
}
