import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export default function Home() {
  return (
    <main className="grid min-h-screen place-items-center px-6">
      <div className="flex max-w-md flex-col items-center gap-3 text-center">
        <h1 className="text-2xl font-semibold tracking-tight">RetailMind AI</h1>
        <p className="text-sm text-muted-foreground">Intelligent Universal Business Analytics Platform</p>
        <Link className={cn(buttonVariants({ size: "lg" }), "mt-2")} href="/overview">Open workspace</Link>
      </div>
    </main>
  );
}
