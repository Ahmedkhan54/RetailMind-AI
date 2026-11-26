"use client";

import { useEffect, useState, type FormEvent, type KeyboardEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useSWRConfig } from "swr";
import { ArrowRight, BarChart3, Eye, EyeOff, LockKeyhole, ShieldCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useDataset, useSession } from "@/components/providers";

type AuthMode = "login" | "register";
type RecoveryMode = "forgot" | "resend" | "reset" | "verify" | null;

function recoveryFromLocation(): { mode: RecoveryMode; token: string } {
  if (typeof window === "undefined") return { mode: null, token: "" };
  const params = new URLSearchParams(window.location.search);
  const token = params.get("token") || "";
  const action = params.get("action");
  if (!token) return { mode: null, token: "" };
  return { mode: action === "password-reset" ? "reset" : action === "email-verification" ? "verify" : null, token };
}

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
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [recoveryMode, setRecoveryMode] = useState<RecoveryMode>(() => recoveryFromLocation().mode);
  const [recoveryToken, setRecoveryToken] = useState(() => recoveryFromLocation().token);
  const [notice, setNotice] = useState("");
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
      if (recoveryMode === "reset" && password !== confirmPassword) throw new Error("Passwords do not match.");
      const endpoint = recoveryMode === "forgot" ? "password-reset/request" : recoveryMode === "resend" ? "email-verification/resend" : recoveryMode === "reset" ? "password-reset/confirm" : recoveryMode === "verify" ? "email-verification/confirm" : mode === "login" ? "login" : "register";
      const body = recoveryMode === "forgot" || recoveryMode === "resend" ? { email: email.trim() }
        : recoveryMode === "reset" ? { token: recoveryToken, new_password: password }
        : recoveryMode === "verify" ? { token: recoveryToken }
        : mode === "login" ? { email: email.trim(), password }
        : { full_name: fullName.trim(), email: email.trim(), phone: phone.trim() || null, password };
      const response = await fetch(`/api/retailmind/auth/${endpoint}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || "Authentication could not be completed.");
      if (recoveryMode) {
        setNotice(payload.message || "Request completed.");
        if (recoveryMode === "reset" || recoveryMode === "verify") { setRecoveryMode(null); setRecoveryToken(""); setPassword(""); setConfirmPassword(""); }
      } else {
        resetDatasetSelection();
        await mutate("/api/retailmind/auth/session", payload, { revalidate: false });
        router.replace(redirectTo);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Authentication could not be completed.");
    } finally {
      setSubmitting(false);
    }
  }

  const isRecovery = recoveryMode !== null;
  const title = recoveryMode === "forgot" ? "Reset your password" : recoveryMode === "resend" ? "Resend confirmation" : recoveryMode === "reset" ? "Choose a new password" : recoveryMode === "verify" ? "Confirm your email" : mode === "login" ? "Welcome back" : "Create your account";
  const subtitle = recoveryMode === "forgot" ? "Enter your work email and we will send a secure reset link if an account exists." : recoveryMode === "resend" ? "Enter your work email and we will send a new confirmation link if an account exists." : recoveryMode === "reset" ? "Use a strong password of at least 12 characters." : recoveryMode === "verify" ? "Confirm your email address to complete account setup." : mode === "login" ? "Sign in to continue to your business overview." : "Use your work email to create a private workspace.";

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
                <h2>{title}</h2>
                <p>{subtitle}</p>
              </div>

              {!isRecovery ? <div className="login-mode-toggle" role="group" aria-label="Account access">
                <button type="button" aria-pressed={mode === "login"} onClick={() => { setMode("login"); setError(""); }}>Sign in</button>
                <button type="button" aria-pressed={mode === "register"} onClick={() => { setMode("register"); setError(""); }}>Create account</button>
              </div> : null}

              <form className="login-form" onSubmit={submit} onKeyDown={guardComposition}>
                {mode === "register" && !isRecovery ? <div className="login-field"><label htmlFor="full-name">Full name</label><Input id="full-name" autoComplete="name" value={fullName} onChange={(event) => setFullName(event.target.value)} maxLength={150} required /></div> : null}
                {recoveryMode !== "reset" && recoveryMode !== "verify" ? <div className="login-field"><label htmlFor="email">Work email</label><Input id="email" type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} maxLength={254} required /></div> : null}
                {mode === "register" && !isRecovery ? <div className="login-field"><label htmlFor="phone">Phone <span>(optional)</span></label><Input id="phone" type="tel" autoComplete="tel" value={phone} onChange={(event) => setPhone(event.target.value)} maxLength={40} /></div> : null}
                {recoveryMode !== "forgot" && recoveryMode !== "verify" ? <div className="login-field"><label htmlFor="password">Password {(mode === "register" || recoveryMode === "reset") ? <span>(12 characters minimum)</span> : null}</label><span className="password-input-wrap"><Input id="password" type={showPassword ? "text" : "password"} autoComplete={mode === "login" ? "current-password" : "new-password"} value={password} onChange={(event) => setPassword(event.target.value)} minLength={(mode === "register" || recoveryMode === "reset") ? 12 : 1} maxLength={1024} required /><button className="password-visibility" type="button" onClick={() => setShowPassword((shown) => !shown)} aria-label={showPassword ? "Hide password" : "Show password"} aria-pressed={showPassword}>{showPassword ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}</button></span></div> : null}
                {recoveryMode === "reset" ? <div className="login-field"><label htmlFor="confirm-password">Confirm new password</label><Input id="confirm-password" type={showPassword ? "text" : "password"} autoComplete="new-password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} minLength={12} maxLength={1024} required /></div> : null}
                {mode === "login" && !isRecovery ? <div className="login-assistance"><button className="forgot-password-link" type="button" onClick={() => { setRecoveryMode("forgot"); setError(""); setNotice(""); }}>Forgot password?</button><button className="forgot-password-link" type="button" onClick={() => { setRecoveryMode("resend"); setError(""); setNotice(""); }}>Resend confirmation email</button></div> : null}
                {error ? <p className="login-error" role="alert">{error}</p> : null}
                {notice ? <p className="login-notice" role="status">{notice}</p> : null}
                <Button className="login-submit" type="submit" disabled={submitting || sessionLoading}>
                  {submitting ? "Please wait…" : recoveryMode === "forgot" ? "Send reset link" : recoveryMode === "resend" ? "Resend confirmation" : recoveryMode === "reset" ? "Update password" : recoveryMode === "verify" ? "Confirm email" : mode === "login" ? "Sign in to workspace" : "Create account"}
                  {!submitting ? <ArrowRight data-icon="inline-end" aria-hidden="true" /> : null}
                </Button>
              </form>

              {isRecovery ? <button className="forgot-password-link login-return" type="button" onClick={() => { setRecoveryMode(null); setRecoveryToken(""); setError(""); setNotice(""); }}>Back to sign in</button> : null}

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
