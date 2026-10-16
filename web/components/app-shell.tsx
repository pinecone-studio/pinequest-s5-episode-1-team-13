"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BrainCircuit, Camera, LayoutDashboard, LogOut, Settings, Shield, TriangleAlert, Volume2, VolumeX } from "lucide-react";

import { useAuth } from "@/components/providers/auth-provider";
import { useRealtimeStatus } from "@/components/providers/realtime-provider";
import { Button } from "@/components/ui/button";
import { playAlert, setSoundEnabled, unlockAudio, useSoundEnabled } from "@/lib/alert-sound";
import { ROLE_LABEL } from "@/lib/format";
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
      <aside className="hidden w-60 shrink-0 flex-col border-r border-border bg-background md:flex">
        <div className="flex items-center gap-3 border-b border-border px-4 py-4">
          <span className="grid size-8 shrink-0 place-items-center rounded-md border border-border text-foreground">
            <Shield className="size-4" />
          </span>
          <div className="min-w-0 leading-tight">
            <div className="truncate text-sm font-medium text-foreground">AI хяналт</div>
            <div className="truncate text-xs text-muted-foreground">Удирдлагын төв</div>
          </div>
        </div>
        <nav className="flex flex-1 flex-col gap-1 p-3">
          {nav.map(({ href, label, icon: Icon }) => {
            const active = isActive(pathname, href);
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex h-10 items-center gap-3 rounded-md px-3 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
                  active && "bg-foreground font-medium text-background hover:bg-foreground hover:text-background",
                )}
              >
                <Icon className="size-4 shrink-0" />
                <span className="truncate">{label}</span>
              </Link>
            );
          })}
        </nav>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center gap-4 border-b border-border bg-background px-4 md:px-6">
          <div className="flex min-w-0 flex-1 items-center gap-2">
            <div className="flex items-center gap-0.5 md:hidden">
              {nav.map(({ href, icon: Icon, label }) => {
                const active = isActive(pathname, href);
                return (
                  <Link
                    key={href}
                    href={href}
                    aria-label={label}
                    className={cn(
                      "grid size-9 place-items-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground",
                      active && "bg-foreground text-background hover:bg-foreground hover:text-background",
                    )}
                  >
                    <Icon className="size-4" />
                  </Link>
                );
              })}
            </div>
            <h1 className="truncate text-sm font-medium text-foreground">{title}</h1>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            <button
              type="button"
              aria-pressed={sound}
              aria-label={sound ? "Дуут дохиог унтраах" : "Дуут дохиог асаах"}
              title={sound ? "Зөрчил илрэхэд дуу гарна (дарж унтраана)" : "Дуу унтраалттай (дарж асаана)"}
              onClick={() => { const next = !sound; setSoundEnabled(next); if (next) { unlockAudio(); playAlert(true); } }}
              className="grid size-8 place-items-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              {sound ? <Volume2 className="size-4" /> : <VolumeX className="size-4" />}
            </button>
            <span className="flex items-center gap-2 px-2 text-xs text-muted-foreground" title="Бодит цагийн холболт">
              <span className={cn("size-1.5 rounded-full", connected ? "bg-success" : "animate-pulse bg-danger")} />
              {connected ? "Шууд" : "Дахин холбогдож байна…"}
            </span>
            <span className="mx-1 hidden h-4 w-px bg-border sm:block" />
            <span className="hidden text-right leading-tight sm:block">
              <span className="block text-sm text-foreground">{user.full_name || user.email}</span>
              <span className="block text-xs text-muted-foreground">{ROLE_LABEL[user.role]}</span>
            </span>
            <Button variant="ghost" size="icon" onClick={logout} aria-label="Гарах">
              <LogOut className="size-4" />
            </Button>
          </div>
        </header>
        <main className="flex-1 p-4 md:p-6">{children}</main>
      </div>
    </div>
  );
}
