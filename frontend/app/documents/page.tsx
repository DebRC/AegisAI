"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import type { DocumentPage } from "../../lib/api/types";

export default function DocumentsPage() {
  const [page, setPage] = useState<DocumentPage | null>(null);
  const [message, setMessage] = useState("");
  async function load() {
    const response = await fetch("/api/documents", { cache: "no-store" });
    if (!response.ok) { setMessage(response.status === 401 ? "Sign in to view documents." : "Unable to load documents."); return; }
    setPage(await response.json());
  }
  useEffect(() => { void load(); }, []);
  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const response = await fetch("/api/documents", { method: "POST", body: new FormData(event.currentTarget) });
    setMessage(response.ok ? "Upload accepted; processing has started." : (await response.json().catch(() => ({}))).detail ?? "Upload failed.");
    if (response.ok) { event.currentTarget.reset(); await load(); }
  }
  return <main className="shell"><section className="hero"><p className="eyebrow">AegisAI workspace</p><h1>Documents</h1><p><Link href="/tenants">Switch organization</Link></p>
    <form className="auth-form" onSubmit={upload}><label>Upload document<input name="file" type="file" required accept=".txt,.md,.pdf,.docx,text/plain,text/markdown,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" /></label><button className="primary-action">Upload</button></form><p aria-live="polite">{message}</p>
    {!page ? <p>Loading documents…</p> : page.items.length === 0 ? <p>No readable documents yet.</p> : <ul>{page.items.map((document) => <li key={document.id}><Link href={`/documents/${document.id}`}><strong>{document.title}</strong></Link> — {document.status} — {document.original_filename}</li>)}</ul>}
  </section></main>;
}
