"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import type { TenantMembership } from "../../lib/api/types";

export default function TenantsPage() {
  const [items, setItems] = useState<TenantMembership[]>([]);
  const [message, setMessage] = useState("Loading organizations…");

  useEffect(() => { void fetch("/api/tenants").then(async response => {
    if (!response.ok) { setMessage("Sign in to manage your organization context."); return; }
    setItems(await response.json() as TenantMembership[]); setMessage("");
  }); }, []);

  async function selectTenant(tenantId: number, tenantName: string) {
    const response = await fetch(`/api/tenants/${tenantId}/select`, { method: "POST" });
    setMessage(response.ok ? `${tenantName} is now active.` : "Unable to switch organization.");
  }

  return <main className="shell"><section className="hero"><p className="eyebrow">Organization context</p><h1>Switch workspace</h1><p>Selecting an organization replaces the server-managed session with a tenant-scoped token pair.</p><p aria-live="polite">{message}</p><ul>{items.map(({ tenant }) => <li key={tenant.id}><strong>{tenant.name}</strong> <small>({tenant.slug})</small> <button onClick={() => void selectTenant(tenant.id, tenant.name)}>Use this workspace</button></li>)}</ul><p><Link href="/documents">Return to documents</Link></p></section></main>;
}
