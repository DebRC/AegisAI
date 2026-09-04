"use client";

import { FormEvent, useEffect, useState } from "react";

import type { AdminPermission, AdminRole } from "../../../lib/api/types";

type RbacData = { roles: AdminRole[]; permissions: AdminPermission[] };
type RoleTemplate = { name: string; description: string; permissionCodes: string[] };

const roleTemplates: RoleTemplate[] = [
  {
    name: "knowledge-reader",
    description: "Search, chat with, and view documents shared with this user.",
    permissionCodes: ["documents:read"],
  },
  {
    name: "knowledge-contributor",
    description: "Read knowledge and upload or manage documents they can edit.",
    permissionCodes: ["documents:read", "documents:write"],
  },
  {
    name: "rbac-manager",
    description: "View users and manage role assignments without document administration.",
    permissionCodes: ["roles:read", "roles:manage", "roles:assign", "users:read"],
  },
];

export default function RbacPage() {
  const [data, setData] = useState<RbacData | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [permissionCodes, setPermissionCodes] = useState<string[]>([]);
  const [message, setMessage] = useState("Loading RBAC configuration…");

  async function load(): Promise<boolean> {
    const response = await fetch("/api/admin/rbac");
    if (!response.ok) {
      setMessage((await response.json().catch(() => ({}))).detail ?? "RBAC administration unavailable.");
      return false;
    }
    setData(await response.json());
    setMessage("");
    return true;
  }

  useEffect(() => {
    void load();
  }, []);

  function applyTemplate(template: RoleTemplate) {
    setName(template.name);
    setDescription(template.description);
    setPermissionCodes(template.permissionCodes);
    setMessage(`Template ready: ${template.name}. Review its permissions, then create the role.`);
  }

  function toggleCreatePermission(permissionCode: string) {
    setPermissionCodes((current) => current.includes(permissionCode)
      ? current.filter((code) => code !== permissionCode)
      : [...current, permissionCode]);
  }

  async function createRole(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const response = await fetch("/api/admin/rbac/roles", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, description }),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      setMessage(body.detail ?? "Role creation failed.");
      return;
    }

    const role = body as { id: number; name: string };
    const selectedPermissions = data?.permissions.filter((permission) => permissionCodes.includes(permission.code)) ?? [];
    const grantResults = await Promise.all(selectedPermissions.map(async (permission) => {
      const grantResponse = await fetch(`/api/admin/rbac/roles/${role.id}/permissions/${permission.id}`, { method: "POST" });
      return grantResponse.ok;
    }));
    const grantedCount = grantResults.filter(Boolean).length;
    const refreshed = await load();
    setMessage(
      grantedCount === selectedPermissions.length
        ? `Role “${role.name}” created with ${grantedCount} permission${grantedCount === 1 ? "" : "s"}.`
        : `Role “${role.name}” was created, but ${selectedPermissions.length - grantedCount} permission changes need review.`,
    );
    if (refreshed) {
      setName("");
      setDescription("");
      setPermissionCodes([]);
    }
  }

  async function changePermission(role: AdminRole, permission: AdminPermission, grant: boolean) {
    const response = await fetch(
      `/api/admin/rbac/roles/${role.id}/permissions/${permission.id}`,
      { method: grant ? "POST" : "DELETE" },
    );
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      setMessage(body.detail ?? "Role permission update failed.");
      return;
    }
    await load();
    setMessage(`${permission.code} ${grant ? "granted to" : "revoked from"} ${role.name}.`);
  }

  return <main className="shell"><section className="hero"><h1>Roles and permissions</h1><p>Roles bundle permissions. Assign roles to people from <a href="/admin/users">Users</a>.</p><p aria-live="polite">{message}</p>{!data ? null : <><h2>Create a custom role</h2><p>Start with a least-privilege template, or choose individual permissions.</p><p>{roleTemplates.map((template) => <button key={template.name} type="button" onClick={() => applyTemplate(template)}>Use {template.name}</button>)}</p><form onSubmit={(event) => void createRole(event)}><label>Role name <input value={name} onChange={(event) => setName(event.target.value)} minLength={2} maxLength={100} required /></label><br /><label>Description <input value={description} onChange={(event) => setDescription(event.target.value)} maxLength={255} /></label><fieldset><legend>Permissions</legend>{data.permissions.map((permission) => <label key={permission.id}><input type="checkbox" checked={permissionCodes.includes(permission.code)} onChange={() => toggleCreatePermission(permission.code)} /> {permission.code} — {permission.description}</label>)}</fieldset><button type="submit">Create role</button></form><h2>Existing roles</h2><ul>{data.roles.map((role) => <li key={role.id}><strong>{role.name}</strong> ({role.user_count} users) — {role.description ?? "No description"}{role.is_system ? <p>System role: its permissions are protected from UI editing.</p> : <details><summary>Manage permissions</summary><ul>{data.permissions.map((permission) => { const granted = role.permission_codes.includes(permission.code); return <li key={permission.id}><strong>{permission.code}</strong> — {permission.description} <button type="button" onClick={() => void changePermission(role, permission, !granted)}>{granted ? "Revoke" : "Grant"}</button></li>; })}</ul></details>}</li>)}</ul></>}</section></main>;
}
