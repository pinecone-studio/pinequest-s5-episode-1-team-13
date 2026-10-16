"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BrainCircuit, Camera, LayoutDashboard, LogOut, Settings, ShieldAlert, TriangleAlert, Volume2, VolumeX } from "lucide-react";

import { useAuth } from "@/components/providers/auth-provider";
import { useRealtimeStatus } from "@/components/providers/realtime-provider";
import { Button } from "@/components/ui/button";
import { playAlert, setSoundEnabled, unlockAudio, useSoundEnabled } from "@/lib/alert-sound";
import { ROLE_LABEL } from "@/lib/format";
import { IN_APP_HINT, useInAppBrowser } from "@/lib/in-app-browser";
import { cn } from "@/lib/utils";

const NAV: { href: string; label: string; icon: typeof Camera; adminOnly?: boolean }[] = [
  { href: "/", label: "Хяналтын самбар", icon: LayoutDashboard },
  { href: "/cameras", label: "Камерууд", icon: Camera },
  { href: "/violations", label: "Зөрчлүүд", icon: TriangleAlert },
  { href: "/training", label: "Сургалт", icon: BrainCircuit, adminOnly: true },
  { href: "/settings", label: "Тохиргоо", icon: Settings },
];

function isActive(pathname: string, href: string) {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}

function InAppBrowserBanner() {
  const inApp = useInAppBrowser();
  if (!inApp) return null;
  return (
    <div role="alert" className="mb-4 rounded-lg border border-warning/30 bg-warning/10 px-4 py-3 text-sm text-warning">
      {IN_APP_HINT}
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { user, loading, logout, can } = useAuth();
  const connected = useRealtimeStatus();
  const sound = useSoundEnabled();

  if (pathname === "/login") return <>{children}</>;
  if (loading || !user) {
    return <div className="grid min-h-screen place-items-center text-sm text-muted-foreground">Ачаалж байна…</div>;
  }

  const nav = NAV.filter((item) => !item.adminOnly || can("ADMIN"));
  const title = nav.find((item) => isActive(pathname, item.href))?.label ?? "Хяналтын самбар";

  return (
    <div className="flex min-h-screen bg-background">
      <aside className="sticky top-0 hidden h-dvh w-60 shrink-0 flex-col border-r border-border bg-white md:flex">
        <div className="flex items-center gap-2 px-4 pt-6">
          <ShieldAlert className="size-4 text-foreground" />
          <div className="leading-tight">
            <div className="text-sm font-medium text-foreground">AI хяналт</div>
            <div className="text-xs text-muted-foreground">Удирдлагын төв</div>
          </div>
        </div>
        <nav className="mt-5 flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto px-3">
          {nav.map(({ href, label, icon: Icon }) => {
            const active = isActive(pathname, href);
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex h-9 items-center gap-2 rounded-xl px-3 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground [&_svg]:text-sidebar-foreground",
                  active && "bg-foreground font-medium text-white hover:bg-foreground hover:text-white [&_svg]:text-white",
                )}
              >
                <Icon className="size-4 shrink-0" />
                <span className="truncate">{label}</span>
              </Link>
            );
          })}
        </nav>
        <div className="mt-auto flex items-center gap-2 border-t border-border p-3">
          <div className="min-w-0 flex-1 leading-tight">
            <div className="truncate text-sm font-medium text-foreground">{user.full_name || user.email}</div>
            <div className="truncate text-xs text-muted-foreground">{ROLE_LABEL[user.role]}</div>
          </div>
          <Button variant="ghost" size="icon" onClick={logout} aria-label="Гарах">
            <LogOut className="size-4" />
          </Button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col p-5 md:p-6">
        <header className="mb-5 flex items-center gap-2 max-sm:flex-wrap max-sm:gap-y-2 sm:gap-4">
          <div className="order-1 flex items-center gap-1 md:hidden">
            {nav.map(({ href, icon: Icon, label }) => {
              const active = isActive(pathname, href);
              return (
                <Link
                  key={href}
                  href={href}
                  aria-label={label}
                  className={cn(
                    "grid size-10 place-items-center rounded-lg text-sidebar-foreground hover:bg-card",
                    active && "bg-foreground text-white hover:bg-foreground hover:text-white",
                  )}
                >
                  <Icon className="size-4" />
                </Link>
              );
            })}
          </div>
          <h1 className="order-2 min-w-0 flex-1 truncate text-2xl font-semibold tracking-tight text-foreground max-sm:order-3 max-sm:w-full max-sm:flex-none">{title}</h1>
          <div className="order-3 flex shrink-0 items-center gap-1 max-sm:order-2 max-sm:ml-auto">
            <button
              type="button"
              aria-pressed={sound}
              aria-label={sound ? "Дуут дохиог унтраах" : "Дуут дохиог асаах"}
              title={sound ? "Зөрчил илрэхэд дуу гарна (дарж унтраана)" : "Дуу унтраалттай (дарж асаана)"}
              onClick={() => { const next = !sound; setSoundEnabled(next); if (next) { unlockAudio(); playAlert(true); } }}
              className="grid size-10 place-items-center rounded-lg text-muted-foreground transition-colors hover:bg-card hover:text-foreground sm:size-8"
            >
              {sound ? <Volume2 className="size-4" /> : <VolumeX className="size-4" />}
            </button>
            <span className="flex items-center gap-2 text-xs text-muted-foreground" title={connected ? "Шууд холбогдсон" : "Дахин холбогдож байна"}>
              <span className={cn("size-2 rounded-full", connected ? "bg-success" : "bg-danger animate-pulse")} />
              <span className="hidden sm:inline">{connected ? "Шууд" : "Дахин холбогдож байна…"}</span>
            </span>
            <span className="mx-1 hidden h-4 w-px bg-border sm:max-md:block" />
            <span className="hidden text-right leading-tight sm:max-md:block">
              <span className="block text-sm text-foreground">{user.full_name || user.email}</span>
              <span className="block text-xs text-muted-foreground">{ROLE_LABEL[user.role]}</span>
            </span>
            <Button variant="ghost" size="icon" className="size-10 sm:size-8 md:hidden" onClick={logout} aria-label="Гарах">
              <LogOut className="size-4" />
            </Button>
          </div>
        </header>
        <main className="min-w-0 flex-1"><InAppBrowserBanner />{children}</main>
      </div>
    </div>
  );
}
