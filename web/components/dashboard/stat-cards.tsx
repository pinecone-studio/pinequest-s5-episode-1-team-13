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
    <div className="flex h-full flex-col rounded-2xl bg-[#111111] p-5 text-white shadow-surface transition-colors duration-150 hover:bg-[#1a1a1a]">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-[15px] font-medium leading-none text-white">
          {alert && <span className="size-1.5 rounded-full bg-[#f87171]" />}
          {label}
        </div>
        <Icon className="size-6 shrink-0 text-white/55" />
      </div>
      <div className="mt-3 flex min-h-10 items-center text-[40px] font-semibold leading-none tracking-tight text-white">{value}</div>
      <div className="mt-2 text-[15px] leading-snug text-white/45">{hint}</div>
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
        value={stats ? <span className="inline-flex items-baseline gap-1.5">{stats.cameras_online}<span className="text-2xl font-medium text-white/40">/ {stats.cameras_total}</span></span> : "—"}
        hint="холбогдсон / нийт"
      />
      <Stat
        icon={TriangleAlert}
        label="Зөрчлүүд"
        alert={stats != null && open > 0}
        value={stats ? <span className={open > 0 ? "text-[#f87171]" : undefined}>{stats.violations_open}</span> : "—"}
        hint={stats ? `нээлттэй · өнөөдөр ${stats.violations_today} · нийт ${stats.violations_total}` : ""}
      />
      <Stat
        icon={Activity}
        label="AI төлөв"
        value={
          stats ? (
            <span className={cn("inline-flex items-center gap-2 text-[22px] font-semibold", ai ? "text-[#4ade80]" : "text-[#f87171]")}>
              <span className={cn("size-2 rounded-full", ai ? "bg-[#4ade80]" : "bg-[#f87171]")} />
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
