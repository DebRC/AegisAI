"use client";

import { FormEvent, useEffect, useState } from "react";

import type { ManagedApiKey, RetentionPolicy } from "../../../lib/api/types";

type GovernanceData = { apiKeys: ManagedApiKey[]; retention: RetentionPolicy };

export default function GovernancePage() {
  const [data, setData] = useState<GovernanceData | null>(null);
  const [message, setMessage] = useState("Loading governance controls…");
  const [newSecret, setNewSecret] = useState("");

  async function load() { const response = await fetch("/api/governance"); if (!response.ok) { setMessage("Governance access is required."); return; } setData(await response.json() as GovernanceData); setMessage(""); }
  useEffect(() => { void load(); }, []);
  async function createKey(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const form = new FormData(event.currentTarget); const response = await fetch("/api/governance/api-keys", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: form.get("name"), scopes: String(form.get("scopes") ?? "").split(",").map(value => value.trim()).filter(Boolean) }) }); const body = await response.json().catch(() => ({})); setMessage(response.ok ? "API key created. Copy its secret now; it cannot be shown again." : body.detail ?? "API key creation failed."); if (response.ok) { setNewSecret(body.api_key); event.currentTarget.reset(); await load(); } }
  async function updateRetention(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const raw = new FormData(event.currentTarget).get("days"); const days = raw === "" ? null : Number(raw); const response = await fetch("/api/governance/retention", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ document_retention_days: days }) }); setMessage(response.ok ? "Retention policy saved." : "Retention update failed."); if (response.ok) await load(); }

  return <main className="shell"><section className="hero"><p className="eyebrow">Enterprise governance</p><h1>Machine access and retention</h1><p aria-live="polite">{message}</p>{newSecret ? <p className="success"><strong>Copy this API key now:</strong> <code>{newSecret}</code></p> : null}<h2>API keys</h2><form className="auth-form" onSubmit={createKey}><label>Name<input name="name" required maxLength={100} /></label><label>Scopes (comma-separated)<input name="scopes" required placeholder="documents:read" /></label><button className="primary-action">Create key</button></form><ul>{data?.apiKeys.map(key => <li key={key.id}><strong>{key.name}</strong> — {key.key_prefix} — {key.scopes.join(", ")} {key.revoked_at ? "(revoked)" : ""}</li>)}</ul><h2>Retention</h2><form className="auth-form" onSubmit={updateRetention}><label>Document retention in days (blank disables automatic deletion)<input name="days" type="number" min="1" defaultValue={data?.retention.document_retention_days ?? ""} /></label><button className="primary-action">Save retention</button></form></section></main>;
}
