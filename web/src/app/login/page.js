"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangleIcon, LockIcon, MicIcon } from "../icons";

export default function LoginPage() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      if (!res.ok) throw new Error("Incorrect password");
      router.push("/");
      router.refresh();
    } catch (err) {
      setError(err.message);
      setSubmitting(false);
    }
  }

  return (
    <div className="login-shell">
      <div className="card login-card">
        <div className="brand" style={{ marginBottom: 4 }}>
          <div className="brand-mark"><MicIcon size={22} /></div>
          <div>
            <h1>Subtitle Burner</h1>
            <p className="subtitle">Enter the password to continue.</p>
          </div>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="section">
            <div className="section-label"><LockIcon size={14} /> Password</div>
            <input
              type="password"
              autoFocus
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          <button className="btn btn-primary" type="submit" disabled={submitting || !password}>
            {submitting ? "Checking..." : "Log in"}
          </button>
          {error && (
            <div className="error-banner">
              <AlertTriangleIcon size={17} />
              <span>{error}</span>
            </div>
          )}
        </form>
      </div>
    </div>
  );
}
