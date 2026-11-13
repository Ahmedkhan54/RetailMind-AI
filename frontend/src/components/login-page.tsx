"use client";

import { useEffect, useState, type FormEvent, type KeyboardEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useSWRConfig } from "swr";
import { ArrowRight, BarChart3, LockKeyhole, ShieldCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useDataset, useSession } from "@/components/providers";

type AuthMode = "login" | "register";

export function LoginPage({ redirectTo }: { redirectTo: string }) {
  const router = useRouter();
  const { mutate } = useSWRConfig();
  const { session, sessionError, sessionLoading } = useSession();
  const { resetDatasetSelection } = useDataset();
  const [mode, setMode] = useState<AuthMode>("login");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (session && !sessionError) router.replace(redirectTo);
  }, [redirectTo, router, session, sessionError]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    setError("");
    try {
      const response = await fetch(`/api/retailmind/auth/${mode === "login" ? "login" : "register"}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(mode === "login"
          ? { email: email.trim(), password }
          : { full_name: fullName.trim(), email: email.trim(), phone: phone.trim() || null, password }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || "Authentication could not be completed.");
      resetDatasetSelection();
      await mutate("/api/retailmind/auth/session", payload, { revalidate: false });
      router.replace(redirectTo);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Authentication could not be completed.");
    } finally {
      setSubmitting(false);
    }
  }

  function guardComposition(event: KeyboardEvent<HTMLFormElement>) {
    if (event.key === "Enter" && (event.nativeEvent.isComposing || event.keyCode === 229)) event.preventDefault();
  }

  return (
    <main className="login-page">
      <section className="login-story" aria-label="RetailMind AI product overview">
        <Link className="login-brand" href="/login" aria-label="RetailMind AI sign in">
          <span className="brand-mark"><BarChart3 aria-hidden="true" /></span>
          <span className="brand-name">RetailMind<span>AI</span></span>
        </Link>
        <div className="login-story-copy">
          <Badge variant="outline" className="login-story-badge">Business intelligence, in focus</Badge>
          <h1>Turn business data into your next clear decision.</h1>
          <p>One calm workspace for sales, customers, inventory, and the questions that move your business forward.</p>
        </div>
        <div className="login-visual" aria-hidden="true">
          <div className="visual-topline"><span>Retail performance</span><span className="visual-period">LIVE DATA</span></div>
          <div className="visual-bars"><span /><span /><span /><span /><span /><span /><span /><span /><span /><span /><span /><span /></div>
          <div className="visual-bottomline"><span><i /> Sales trend</span><span><i /> Profit trend</span></div>
        </div>
        <div className="login-story-footer"><span>Private by design</span><span>Built for informed decisions</span></div>
      </section>

      <section className="login-panel" aria-label="Sign in to RetailMind AI">
        <div className="login-card-wrap">
          <div className="login-mobile-brand">
            <span className="brand-mark"><BarChart3 aria-hidden="true" /></span>
            <span className="brand-name">RetailMind<span>AI</span></span>
          </div>
          <Card className="login-card">
            <CardContent>
              <div className="login-heading">
                <span className="login-heading-icon"><LockKeyhole aria-hidden="true" /></span>
                <p className="eyebrow">Your analytics workspace</p>
                <h2>{mode === "login" ? "Welcome back" : "Create your account"}</h2>
                <p>{mode === "login" ? "Sign in to continue to your business overview." : "Use your work email to create a private workspace."}</p>
              </div>

              <div className="login-mode-toggle" role="group" aria-label="Account access">
                <button type="button" aria-pressed={mode === "login"} onClick={() => { setMode("login"); setError(""); }}>Sign in</button>
                <button type="button" aria-pressed={mode === "register"} onClick={() => { setMode("register"); setError(""); }}>Create account</button>
              </div>

              <form className="login-form" onSubmit={submit} onKeyDown={guardComposition}>
                {mode === "register" ? <div className="login-field"><label htmlFor="full-name">Full name</label><Input id="full-name" autoComplete="name" value={fullName} onChange={(event) => setFullName(event.target.value)} maxLength={150} required /></div> : null}
                <div className="login-field"><label htmlFor="email">Work email</label><Input id="email" type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} maxLength={254} required /></div>
                {mode === "register" ? <div className="login-field"><label htmlFor="phone">Phone <span>(optional)</span></label><Input id="phone" type="tel" autoComplete="tel" value={phone} onChange={(event) => setPhone(event.target.value)} maxLength={40} /></div> : null}
                <div className="login-field"><label htmlFor="password">Password {mode === "register" ? <span>(12 characters minimum)</span> : null}</label><Input id="password" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} value={password} onChange={(event) => setPassword(event.target.value)} minLength={mode === "register" ? 12 : 1} maxLength={1024} required /></div>
                {error ? <p className="login-error" role="alert">{error}</p> : null}
                <Button className="login-submit" type="submit" disabled={submitting || sessionLoading}>
                  {submitting ? "Please wait…" : mode === "login" ? "Sign in to workspace" : "Create account"}
                  {!submitting ? <ArrowRight data-icon="inline-end" aria-hidden="true" /> : null}
                </Button>
              </form>

              <div className="login-assurance"><ShieldCheck aria-hidden="true" /><span>Passwords are hashed and sessions are verified by the existing MySQL-backed account service.</span></div>
              <p className="login-access-note">Owner access is assigned separately by your workspace administrator.</p>
            </CardContent>
          </Card>
          <p className="login-footer">RetailMind AI · Intelligent Universal Business Analytics Platform</p>
        </div>
      </section>
    </main>
  );
}
