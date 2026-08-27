"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";

export default function RegisterPage() {
  const [message, setMessage] = useState("");
  const [failed, setFailed] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const response = await fetch("/api/auth/register", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email: form.get("email"), fullName: form.get("fullName"), password: form.get("password") }) });
    const payload = await response.json().catch(() => ({}));
    setFailed(!response.ok);
    setMessage(response.ok ? "Account created. You can now sign in." : typeof payload.detail === "string" ? payload.detail : "Unable to create account");
  }
  return <main className="shell"><section className="hero"><p className="eyebrow">AegisAI</p><h1>Create an account</h1>
    <form className="auth-form" onSubmit={submit}><label>Full name<input name="fullName" autoComplete="name" required minLength={2} /></label><label>Email<input name="email" type="email" autoComplete="email" required /></label><label>Password<input name="password" type="password" autoComplete="new-password" required minLength={8} /></label><button className="primary-action" type="submit">Create account</button></form>
    <p aria-live="polite" className={failed ? "error" : "success"}>{message}</p><p><Link href="/login">Back to sign in</Link></p>
  </section></main>;
}
