"use client";

import { CircleAlert } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function WorkspaceError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main className="auth-loading auth-loading-error" role="alert">
      <CircleAlert aria-hidden="true" style={{ width: 24, height: 24, margin: "0 auto" }} />
      <h1 style={{ fontSize: 18, fontWeight: 650 }}>This page could not be displayed</h1>
      <p>The workspace hit an unexpected error. Your account and uploaded data are unchanged.</p>
      <div className="auth-loading-actions">
        <Button type="button" variant="outline" size="sm" onClick={reset}>Retry this page</Button>
        <Link href="/overview">Return to overview</Link>
      </div>
    </main>
  );
}