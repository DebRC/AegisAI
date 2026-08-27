"use client";
import { useEffect, useState } from "react";
import type { AdminDocumentPage } from "../../../lib/api/types";
export default function AdminDocumentsPage() { const [data, setData] = useState<AdminDocumentPage | null>(null); useEffect(() => { void fetch("/api/admin/documents").then(r => r.ok ? r.json().then(setData) : null); }, []); return <main className="shell"><section className="hero"><h1>All documents</h1>{!data ? <p>Loading documents…</p> : <ul>{data.items.map(document => <li key={document.id}><strong>{document.title}</strong> — {document.status} — uploader {document.uploader_user_id}{document.processing_error ? ` — ${document.processing_error}` : ""}</li>)}</ul>}</section></main>; }
