"use client";
import { useEffect, useState } from "react";

import type { AdminRole, AdminUserPage } from "../../../lib/api/types";

export default function AdminUsersPage() {
  const [data, setData] = useState<AdminUserPage | null>(null);
  const [roles, setRoles] = useState<AdminRole[]>([]);
  const [selectedRoleByUser, setSelectedRoleByUser] = useState<Record<number, string>>({});
  const [message, setMessage] = useState("Loading users…");

  async function load() {
    const [usersResponse, rbacResponse] = await Promise.all([
      fetch("/api/admin/users"),
      fetch("/api/admin/rbac"),
    ]);

    if (!usersResponse.ok) {
      setMessage((await usersResponse.json().catch(() => ({}))).detail ?? "User administration unavailable.");
      return;
    }

    setData(await usersResponse.json());
    if (!rbacResponse.ok) {
      setRoles([]);
      setMessage("Users loaded, but role choices are unavailable.");
      return;
    }

    const rbac = await rbacResponse.json() as { roles: AdminRole[] };
    setRoles(rbac.roles);
    setMessage("");
  }

  useEffect(() => {
    void load();
  }, []);

  async function toggle(id: number, active: boolean) {
    if (!window.confirm(`${active ? "Activate" : "Deactivate"} this user?`)) return;

    const response = await fetch(`/api/admin/users/${id}/status`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ isActive: active }),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      setMessage(body.detail ?? "User update failed.");
      return;
    }

    await load();
    setMessage("User status updated.");
  }

  async function assignRole(userId: number) {
    const roleId = selectedRoleByUser[userId];
    if (!roleId) {
      setMessage("Select a role before assigning it.");
      return;
    }

    const response = await fetch(`/api/admin/users/${userId}/roles/${roleId}`, { method: "POST" });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      setMessage(body.detail ?? "Role assignment failed.");
      return;
    }

    setSelectedRoleByUser((current) => ({ ...current, [userId]: "" }));
    await load();
    setMessage("Role assigned.");
  }

  return <main className="shell"><section className="hero"><h1>Users</h1><p>Assign roles in the active organization.</p><p aria-live="polite">{message}</p>{!data ? null : <ul>{data.items.map((user) => {
    const availableRoles = roles.filter((role) => !user.roles.some((assignedRole) => assignedRole.id === role.id));
    const selectedRole = selectedRoleByUser[user.id] ?? "";
    return <li key={user.id}><strong>{user.full_name}</strong> — {user.email} — {user.is_active ? "active" : "inactive"} — {user.roles.map((role) => role.name).join(", ") || "no roles"}<br /><label>Role <select value={selectedRole} onChange={(event) => setSelectedRoleByUser((current) => ({ ...current, [user.id]: event.target.value }))} disabled={availableRoles.length === 0}><option value="">Select a role</option>{availableRoles.map((role) => <option key={role.id} value={role.id}>{role.name}</option>)}</select></label> <button onClick={() => void assignRole(user.id)} disabled={!selectedRole}>Assign role</button> <button onClick={() => void toggle(user.id, !user.is_active)}>{user.is_active ? "Deactivate" : "Activate"}</button></li>;
  })}</ul>}</section></main>;
}
