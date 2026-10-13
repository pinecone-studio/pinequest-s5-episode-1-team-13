import { Activity, Camera, TriangleAlert } from "lucide-react";

import { cn } from "@/lib/utils";
import type { DashboardStats } from "@/types";

function Stat({ icon: Icon, label, value, hint, accent }: { icon: typeof Camera; label: string; value: React.ReactNode; hint: string; accent: string }) {
  return (
    <div className="relative overflow-hidden rounded-2xl border bg-card p-5">
      <span className={cn("absolute inset-y-0 left-0 w-1.5", accent)} />
      <div className="flex items-start justify-between">
        <div className="text-[11px] font-semibold tracking-[0.2em] text-muted-foreground">{label}</div>
        <Icon className="size-5 text-muted-foreground" />
      </div>
      <div className="mt-3 text-4xl font-bold leading-none tracking-tight">{value}</div>
      <div className="mt-2 text-sm text-muted-foreground">{hint}</div>
    </div>
  );
}

export function StatCards({ stats }: { stats: DashboardStats | null }) {
  const ai = stats?.ai_status === "ONLINE";
  return (
    <div className="grid gap-4 sm:grid-cols-3">
      <Stat
        icon={Camera} label="КАМЕРУУД" accent="bg-primary"
        value={stats ? <>{stats.cameras_online}<span className="text-2xl text-muted-foreground"> / {stats.cameras_total}</span></> : "—"}
        hint="холбогдсон / нийт"
      />
      <Stat
        icon={TriangleAlert} label="ЗӨРЧЛҮҮД" accent={stats && stats.violations_open > 0 ? "bg-red-500" : "bg-emerald-500"}
        value={<span className={stats && stats.violations_open > 0 ? "text-red-400" : undefined}>{stats ? stats.violations_open : "—"}</span>}
        hint={stats ? `нээлттэй · өнөөдөр ${stats.violations_today} · нийт ${stats.violations_total}` : ""}
      />
      <Stat
        icon={Activity} label="AI ТӨЛӨВ" accent={ai ? "bg-emerald-500" : "bg-zinc-600"}
        value={<span className={ai ? "text-emerald-400" : stats ? "text-red-400" : undefined}>{stats ? (ai ? "АЖИЛЛАЖ БАЙНА" : "САЛСАН") : "—"}</span>}
        hint="AI үйлчилгээний дохио"
      />
    </div>
  );
}
