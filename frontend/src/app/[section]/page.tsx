import { notFound } from "next/navigation";
import { WorkspaceRoute } from "@/components/workspace-route";
import { allNavigationItems, getNavigationItem } from "@/lib/navigation";

export function generateStaticParams() {
  return allNavigationItems.map((item) => ({ section: item.href.slice(1) }));
}

export default async function WorkspacePage({ params }: { params: Promise<{ section: string }> }) {
  const { section } = await params;
  const item = getNavigationItem(section);
  if (!item) notFound();

  return <WorkspaceRoute section={section} />;
}
