"use client";

import { useEffect, useMemo, useState, type KeyboardEvent, type ReactNode } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  BarChart3,
  Bell,
  ChevronDown,
  Command,
  LogOut,
  Menu,
  Search,
  Sparkles,
} from "lucide-react";
import { mutate } from "swr";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { cn } from "@/lib/utils";
import { allNavigationItems, navigationGroups } from "@/lib/navigation";
import { useDataset, useSession } from "@/components/providers";

function Brand() {
  return (
    <Link href="/overview" className="brand-lockup" aria-label="RetailMind AI overview">
      <span className="brand-mark"><BarChart3 aria-hidden="true" /></span>
      <span className="brand-name">RetailMind<span>AI</span></span>
    </Link>
  );
}

function NavigationLinks({ activeHref, onNavigate, role }: { activeHref: string; onNavigate?: () => void; role?: string }) {
  return (
    <nav className="navigation-list" aria-label="Main navigation">
      {navigationGroups.map((group) => (
        <section className="navigation-group" key={group.label} aria-label={group.label}>
          <h2 className="navigation-label">{group.label}</h2>
          <div className="navigation-items">
            {group.items.filter((item) => item.href !== "/owner-admin" || role === "owner_admin").map(({ href, label, icon: Icon }) => {
              const active = activeHref === href;
              return (
                <Link
                  className="navigation-link"
                  data-active={active}
                  href={href}
                  key={href}
                  aria-current={active ? "page" : undefined}
                  onClick={onNavigate}
                >
                  <Icon aria-hidden="true" />
                  <span>{label}</span>
                </Link>
              );
            })}
          </div>
        </section>
      ))}
    </nav>
  );
}

function Sidebar({ activeHref, onNavigate, role }: { activeHref: string; onNavigate?: () => void; role?: string }) {
  return (
    <div className="sidebar-inner">
      <div className="sidebar-brand"><Brand /></div>
      <div className="sidebar-scroll"><NavigationLinks activeHref={activeHref} onNavigate={onNavigate} role={role} /></div>
      <div className="sidebar-bottom">
        <div className="sidebar-promo">
          <span className="promo-icon"><Sparkles aria-hidden="true" /></span>
          <strong>Make more of your data</strong>
          <p>Connect your analytics service to unlock your workspace.</p>
          <Link href="/data-connections" className="promo-link" onClick={onNavigate}>View setup guide <span aria-hidden="true">→</span></Link>
        </div>
        <div className="sidebar-footer"><span className="avatar-small">RM</span><div><strong>Retail workspace</strong><span>Local preview</span></div><ChevronDown aria-hidden="true" /></div>
      </div>
    </div>
  );
}

export function AppShell({ children, currentHref, currentLabel }: { children: ReactNode; currentHref: string; currentLabel: string }) {
  const router = useRouter();
  const { session, sessionLoading, sessionError } = useSession();
  const { setDataset } = useDataset();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState("");

  useEffect(() => {
    if (sessionError?.status === 401) {
      router.replace(`/login?next=${encodeURIComponent(currentHref)}`);
    }
  }, [currentHref, router, sessionError]);

  const results = useMemo(() => {
    const query = search.trim().toLowerCase();
    return query ? allNavigationItems.filter((item) => `${item.label} ${item.group}`.toLowerCase().includes(query)).slice(0, 6) : [];
  }, [search]);

  function handleSearchKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key !== "Enter" || event.nativeEvent.isComposing || event.keyCode === 229) return;
    if (results[0]) {
      router.push(results[0].href);
      setSearch("");
      setSearchOpen(false);
    }
  }

  async function handleLogout() {
    if (loggingOut) return;
    setLoggingOut(true);
    setLogoutError("");
    try {
      const response = await fetch("/api/retailmind/auth/logout", { method: "POST" });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || "Could not sign out. Try again.");
      setDataset(null);
      await mutate("/api/retailmind/auth/session", null, { revalidate: false });
      router.replace("/login");
      router.refresh();
    } catch (error) {
      setLogoutError(error instanceof Error ? error.message : "Could not sign out. Try again.");
    } finally {
      setLoggingOut(false);
    }
  }

  if (sessionLoading || (!session && !sessionError) || sessionError?.status === 401) {
    return <div className="auth-loading" role="status">Checking your secure session…</div>;
  }

  if (sessionError) {
    return <div className="auth-loading auth-loading-error" role="alert"><p>{sessionError.message}</p><Link href="/login">Return to sign in</Link></div>;
  }

  return (
    <div className="app-shell">
      <aside className="app-sidebar"><Sidebar activeHref={currentHref} role={session?.role} /></aside>
      <div className="workspace-frame">
        <header className="topbar">
          <div className="topbar-leading">
            <Sheet open={mobileNavOpen} onOpenChange={setMobileNavOpen}>
              <SheetTrigger render={<Button variant="ghost" size="icon" className="mobile-menu" aria-label="Open navigation" />}>
                <Menu aria-hidden="true" />
              </SheetTrigger>
              <SheetContent side="left" className="mobile-sheet" showCloseButton={false}>
                <SheetTitle className="sr-only">RetailMind AI navigation</SheetTitle>
                <SheetDescription className="sr-only">Navigate to an analytics workspace page.</SheetDescription>
                <Sidebar activeHref={currentHref} onNavigate={() => setMobileNavOpen(false)} role={session?.role} />
              </SheetContent>
            </Sheet>
            <div className="breadcrumb"><span>Workspace</span><span className="breadcrumb-slash">/</span><strong>{currentLabel}</strong></div>
          </div>
          <div className="topbar-actions">
            <div className="global-search-wrap">
              <Search className="search-icon" aria-hidden="true" />
              <input
                className="global-search"
                value={search}
                onChange={(event) => { setSearch(event.target.value); setSearchOpen(true); }}
                onFocus={() => setSearchOpen(true)}
                onKeyDown={handleSearchKeyDown}
                onBlur={() => window.setTimeout(() => setSearchOpen(false), 140)}
                placeholder="Search workspace"
                role="combobox"
                aria-label="Search workspace pages"
                aria-autocomplete="list"
                aria-controls="workspace-search-results"
                aria-expanded={searchOpen && results.length > 0}
              />
              <span className="search-shortcut"><Command aria-hidden="true" /> K</span>
              {searchOpen && results.length > 0 ? (
                <div id="workspace-search-results" className="search-results" role="listbox" aria-label="Workspace pages">
                  {results.map((item) => {
                    const Icon = item.icon;
                    return <Link href={item.href} className="search-result" key={item.href} role="option" onMouseDown={() => { setSearch(""); setSearchOpen(false); }}><Icon aria-hidden="true" /><span>{item.label}</span><small>{item.group}</small></Link>;
                  })}
                </div>
              ) : null}
            </div>
            <Link href="/smart-alerts" className={cn(buttonVariants({ variant: "ghost", size: "icon" }), "topbar-icon-button")} aria-label="Open smart alerts"><Bell aria-hidden="true" /><span className="notification-dot" /></Link>
            <Link href="/profile" className="profile-button" aria-label="Open user profile"><span className="profile-avatar">{session?.user.full_name.split(/\s+/).map((part) => part[0]).join("").slice(0, 2).toUpperCase() || "RM"}</span><span className="profile-name">{session?.user.full_name || "My account"}</span><ChevronDown aria-hidden="true" /></Link>
            <Button variant="ghost" size="icon" className="topbar-icon-button" aria-label="Sign out" title="Sign out" disabled={loggingOut} onClick={handleLogout}><LogOut aria-hidden="true" /></Button>
          </div>
        </header>
        <main className="workspace-content">{logoutError ? <div className="backend-notice" role="alert">{logoutError}</div> : null}{children}</main>
        <footer className="workspace-footer"><span>RetailMind AI</span><span>Intelligent Universal Business Analytics Platform</span><Badge variant="outline">Preview</Badge></footer>
      </div>
    </div>
  );
}
