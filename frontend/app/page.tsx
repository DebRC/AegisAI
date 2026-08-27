import Link from "next/link";

export default function HomePage() {
  return (
    <main className="shell">
      <section className="hero" aria-labelledby="page-title">
        <p className="eyebrow">AegisAI</p>
        <h1 id="page-title">Enterprise knowledge, with grounded answers.</h1>
        <p className="summary">
          The secure AegisAI workspace is coming online. Sign in to work with
          documents, search verified knowledge, and use citation-backed chat.
        </p>
        <Link className="primary-action" href="/login">
          Sign in
        </Link>
      </section>
    </main>
  );
}
