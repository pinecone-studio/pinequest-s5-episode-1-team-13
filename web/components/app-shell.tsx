"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BrainCircuit, Camera, LayoutDashboard, LogOut, Settings, ShieldAlert, TriangleAlert, Volume2, VolumeX } from "lucide-react";

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

  return (
    <div className="flex min-h-screen">
      <aside className="hidden w-60 shrink-0 flex-col border-r bg-card/40 md:flex">
        <div className="flex items-center gap-2 border-b px-5 py-4">
          <ShieldAlert className="size-5 text-primary" />
          <div className="leading-tight">
            <div className="text-sm font-semibold tracking-wide">AI ХЯНАЛТ</div>
            <div className="text-[11px] text-muted-foreground">Удирдлагын төв</div>
          </div>
        </div>
        <nav className="flex flex-1 flex-col gap-1 p-3">
          {nav.map(({ href, label, icon: Icon }) => {
            const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
                  active && "bg-primary/10 font-medium text-primary",
                )}
              >
                <Icon className="size-4" />
                {label}
              </Link>
            );
          })}
        </nav>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between gap-4 border-b px-4 py-3 md:px-6">
          <div className="flex items-center gap-1 md:hidden">
            {nav.map(({ href, icon: Icon, label }) => (
              <Link key={href} href={href} aria-label={label} className="rounded-md p-2 text-muted-foreground hover:bg-muted">
                <Icon className="size-4" />
              </Link>
            ))}
          </div>
          <h1 className="hidden text-sm font-semibold tracking-[0.2em] text-muted-foreground md:block">
            ҮЙЛДВЭРИЙН AI ХЯНАЛТЫН ТӨВ
          </h1>
          <div className="flex items-center gap-4 text-sm">
            <button
              type="button" aria-pressed={sound} aria-label={sound ? "Дуут дохиог унтраах" : "Дуут дохиог асаах"}
              title={sound ? "Зөрчил илрэхэд дуу гарна (дарж унтраана)" : "Дуу унтраалттай (дарж асаана)"}
              onClick={() => { const next = !sound; setSoundEnabled(next); if (next) { unlockAudio(); playAlert(true); } }}
              className="grid size-8 place-items-center rounded-full text-muted-foreground transition hover:bg-muted hover:text-foreground"
            >
              {sound ? <Volume2 className="size-4" /> : <VolumeX className="size-4" />}
            </button>
            <span className="flex items-center gap-2 text-xs text-muted-foreground" title="Бодит цагийн холболт">
              <span className={cn("size-2 rounded-full", connected ? "bg-emerald-400" : "bg-red-400 animate-pulse")} />
              {connected ? "Шууд" : "Дахин холбогдож байна…"}
            </span>
            <span className="hidden text-right leading-tight sm:block">
              <span className="block text-sm">{user.full_name || user.email}</span>
              <span className="block text-[11px] text-muted-foreground">{ROLE_LABEL[user.role]}</span>
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
