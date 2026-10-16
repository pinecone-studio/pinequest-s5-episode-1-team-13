import { Activity, Camera, TriangleAlert } from "lucide-react";

import { cn } from "@/lib/utils";
import type { DashboardStats } from "@/types";

function Stat({
  icon: Icon,
  label,
  value,
  hint,
  alert,
}: {
  icon: typeof Camera;
  label: string;
  value: React.ReactNode;
  hint: string;
  alert?: boolean;
}) {
  return (
    <div className="flex h-full min-h-36 flex-col rounded-xl border border-border bg-card p-4 transition-colors duration-150 hover:bg-muted">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
          {alert && <span className="size-1.5 rounded-full bg-danger" />}
          {label}
        </div>
        <Icon className="size-4 shrink-0 text-muted-foreground" />
      </div>
      <div className="mt-4 text-3xl font-semibold leading-none tracking-tight text-foreground">{value}</div>
      <div className="mt-auto pt-3 text-xs text-muted-foreground">{hint}</div>
    </div>
  );
}

export function StatCards({ stats }: { stats: DashboardStats | null }) {
  const ai = stats?.ai_status === "ONLINE";
  const open = stats?.violations_open ?? 0;

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
      <Stat
        icon={Camera}
        label="Камерууд"
        value={stats ? <>{stats.cameras_online}<span className="text-xl font-medium text-muted-foreground"> / {stats.cameras_total}</span></> : "—"}
        hint="холбогдсон / нийт"
      />
      <Stat
        icon={TriangleAlert}
        label="Зөрчлүүд"
        alert={stats != null && open > 0}
        value={stats ? stats.violations_open : "—"}
        hint={stats ? `нээлттэй · өнөөдөр ${stats.violations_today} · нийт ${stats.violations_total}` : ""}
      />
      <Stat
        icon={Activity}
        label="AI төлөв"
        value={
          stats ? (
            <span className="inline-flex items-center gap-2 text-lg font-medium">
              <span className={cn("size-1.5 rounded-full", ai ? "bg-success" : "bg-danger")} />
              {ai ? "Ажиллаж байна" : "Салсан"}
            </span>
          ) : (
            "—"
          )
        }
        hint="AI үйлчилгээний дохио"
      />
    </div>
  );
}
