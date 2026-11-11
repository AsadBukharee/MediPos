"use client";

import { useState } from "react";
import { Badge, Button, DataTable, Field, Input, Modal, Notice, PageHeader, Select } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dateTime } from "@/lib/format";
import { useAction, useApi, useList } from "@/lib/hooks";

interface Account {
  id: number;
  username: string;
  first_name: string;
  last_name: string;
  email: string;
  role: string;
  branches: number[];
  max_discount_percent: string;
  is_active: boolean;
  last_login: string | null;
}

interface Role {
  role: string;
  label: string;
}

export default function UsersPage() {
  const users = useList<Account>("/auth/users/");
  const roles = useApi<Role[]>("/auth/roles/");
  const [editing, setEditing] = useState<Account | "new" | null>(null);
  const label = (role: string) => roles.data?.find((r) => r.role === role)?.label ?? role;
  return (
    <>
      <PageHeader title="Users" subtitle="Roles decide what each person can see and do, in the branches you assign.">
        <Button onClick={() => setEditing("new")}>New user</Button>
      </PageHeader>
      <DataTable
        rows={users.rows}
        rowKey={(r) => r.id}
        loading={users.loading}
        error={users.error}
        onRowClick={setEditing}
        columns={[
          { header: "User", cell: (r) => (<><span className="font-medium">{r.username}</span> <span className="text-muted">{r.first_name} {r.last_name}</span></>) },
          { header: "Role", cell: (r) => label(r.role) },
          { header: "Max discount", align: "right", cell: (r) => `${Number(r.max_discount_percent)}%` },
          { header: "Last sign-in", cell: (r) => dateTime(r.last_login) },
          { header: "Status", cell: (r) => <Badge tone={r.is_active ? "ok" : "danger"}>{r.is_active ? "active" : "disabled"}</Badge> },
        ]}
      />
      {editing && <UserForm account={editing === "new" ? null : editing} roles={roles.data ?? []} onClose={() => (setEditing(null), users.reload())} />}
    </>
  );
}

function UserForm({ account, roles, onClose }: { account: Account | null; roles: Role[]; onClose: () => void }) {
  const { user } = useAuth();
  const [form, setForm] = useState({
    username: account?.username ?? "", first_name: account?.first_name ?? "", last_name: account?.last_name ?? "",
    email: account?.email ?? "", role: account?.role ?? "cashier", max_discount_percent: account?.max_discount_percent ?? "0",
    is_active: account?.is_active ?? true, password: "",
  });
  const [branches, setBranches] = useState<number[]>(account?.branches ?? []);
  const { busy, error, run } = useAction();
  const bind = (name: "username" | "first_name" | "last_name" | "email" | "max_discount_percent" | "password") => ({
    value: form[name],
    onChange: (e: React.ChangeEvent<HTMLInputElement>) => setForm((f) => ({ ...f, [name]: e.target.value })),
  });
  const save = async () => {
    const body: Record<string, unknown> = { ...form, branches };
    if (!form.password) delete body.password;
    const done = await run(() => (account ? api(`/auth/users/${account.id}/`, { method: "PATCH", body }) : api("/auth/users/", { body })));
    if (done) onClose();
  };
  return (
    <Modal
      title={account ? `Edit ${account.username}` : "New user"}
      onClose={onClose}
      footer={<Button disabled={busy || !form.username.trim() || (!account && form.password.length < 8)} onClick={save}>Save</Button>}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="sm:col-span-2"><Notice>{error}</Notice></div>
        <Field label="Username"><Input {...bind("username")} autoFocus autoComplete="off" /></Field>
        <Field label={account ? "New password (optional)" : "Password"} hint="At least 8 characters.">
          <Input type="password" {...bind("password")} autoComplete="new-password" />
        </Field>
        <Field label="First name"><Input {...bind("first_name")} /></Field>
        <Field label="Last name"><Input {...bind("last_name")} /></Field>
        <Field label="Email" hint="Used for password reset."><Input type="email" {...bind("email")} /></Field>
        <Field label="Role">
          <Select value={form.role} onChange={(e) => setForm((f) => ({ ...f, role: e.target.value }))}>
            {roles.map((r) => <option key={r.role} value={r.role}>{r.label}</option>)}
          </Select>
        </Field>
        <Field label="Max invoice discount %"><Input {...bind("max_discount_percent")} inputMode="decimal" className="num" /></Field>
        <label className="flex items-center gap-2 self-end pb-2">
          <input type="checkbox" checked={form.is_active} onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))} /> Active
        </label>
        <fieldset className="sm:col-span-2">
          <legend className="mb-1 text-[13px] font-medium text-muted">Branches</legend>
          <div className="flex flex-wrap gap-x-4 gap-y-1">
            {user?.branches.map((b) => (
              <label key={b.id} className="flex items-center gap-1.5">
                <input
                  type="checkbox"
                  checked={branches.includes(b.id)}
                  onChange={(e) => setBranches((ids) => (e.target.checked ? [...ids, b.id] : ids.filter((id) => id !== b.id)))}
                />
                {b.name}
              </label>
            ))}
          </div>
        </fieldset>
      </div>
    </Modal>
  );
}
