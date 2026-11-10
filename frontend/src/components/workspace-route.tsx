"use client";

import { AppShell } from "@/components/app-shell";
import { DashboardRuntime } from "@/components/dashboard-runtime";
import { FeaturePage } from "@/components/feature-pages";
import { getNavigationItem } from "@/lib/navigation";

export function WorkspaceRoute({ section }: { section: string }) {
  const item = getNavigationItem(section);
  if (!item) return null;

  return (
    <AppShell currentHref={item.href} currentLabel={item.label}>
      {section === "overview" ? <DashboardRuntime /> : <FeaturePage item={item} />}
    </AppShell>
  );
}
