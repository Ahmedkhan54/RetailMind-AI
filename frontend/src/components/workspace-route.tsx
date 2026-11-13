"use client";

import dynamic from "next/dynamic";
import { AppShell } from "@/components/app-shell";
import { getNavigationItem } from "@/lib/navigation";

function WorkspaceLoading() {
  return (
    <div className="page-stack" aria-live="polite" aria-busy="true">
      <span className="sr-only">Loading workspace module</span>
      <div className="loading-panel" />
    </div>
  );
}

// Route modules are fetched only when that section is opened. Previously every
// dashboard and feature page (including charts and maps) shared one client bundle.
const DashboardRuntime = dynamic(
  () => import("@/components/dashboard-runtime").then((module) => module.DashboardRuntime),
  { ssr: false, loading: WorkspaceLoading },
);

const FeaturePage = dynamic(
  () => import("@/components/feature-pages").then((module) => module.FeaturePage),
  { ssr: false, loading: WorkspaceLoading },
);

export function WorkspaceRoute({ section }: { section: string }) {
  const item = getNavigationItem(section);
  if (!item) return null;

  return (
    <AppShell currentHref={item.href} currentLabel={item.label}>
      {section === "overview" ? <DashboardRuntime /> : <FeaturePage item={item} />}
    </AppShell>
  );
}
