"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

type FormState = "idle" | "submitting" | "success" | "error";

export default function LoginPage() {
  const router = useRouter();
  const [state, setState] = useState<FormState>("idle");
  const [message, setMessage] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setState("submitting");
    const form = new FormData(event.currentTarget);
    const response = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: form.get("email"), password: form.get("password") }),
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      setMessage(typeof payload.detail === "string" ? payload.detail : "Unable to sign in");
      setState("error");
      return;
    }
    setMessage("Opening your workspace…");
    setState("success");
    router.replace("/documents");
  }

  return (
    <main className="shell"><section className="hero"><p className="eyebrow">AegisAI</p><h1>Sign in</h1>
      <form className="auth-form" onSubmit={submit}>
        <label>Email<input name="email" type="email" autoComplete="email" required /></label>
        <label>Password<input name="password" type="password" autoComplete="current-password" required /></label>
        <button className="primary-action" disabled={state === "submitting"} type="submit">{state === "submitting" ? "Signing in…" : "Sign in"}</button>
      </form>
      <p aria-live="polite" className={state === "error" ? "error" : "success"}>{message}</p>
      <p>New to AegisAI? <Link href="/register">Create an account</Link>.</p>
      <p className="divider">or continue with</p>
      <div className="provider-links"><a href="/api/auth/sso/google">Google</a><a href="/api/auth/sso/github">GitHub</a><a href="/api/auth/sso/microsoft_entra">Microsoft</a></div>
    </section></main>
  );
}
