"use client";

import { useCallback, useEffect, useState } from "react";

import { NativeSelect } from "@/components/native-select";
import { useRealtimeEvents } from "@/components/providers/realtime-provider";
import { Button } from "@/components/ui/button";
import { ViolationDetailDialog } from "@/components/violations/violation-detail-dialog";
import { ViolationTable } from "@/components/violations/violation-table";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { Violation, ViolationStatus, ViolationType, ZoneName } from "@/types";

const PAGE_SIZE = 15;
const STATUSES: { label: string; value: ViolationStatus | "" }[] = [
  { label: "Бүгд", value: "" }, { label: "Нээлттэй", value: "OPEN" },
  { label: "Хүлээн авсан", value: "ACKNOWLEDGED" }, { label: "Шийдвэрлэсэн", value: "RESOLVED" },
];

export default function ViolationsPage() {
  const [status, setStatus] = useState<ViolationStatus | "">("");
  const [zone, setZone] = useState<ZoneName | "">("");
  const [type, setType] = useState<ViolationType | "">("");
  const [page, setPage] = useState(1);
  const [items, setItems] = useState<Violation[]>([]);
  const [total, setTotal] = useState(0);
  const [selected, setSelected] = useState<Violation | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .violations({ status: status || undefined, zone: zone || undefined, violation_type: type || undefined, page, page_size: PAGE_SIZE })
      .then((r) => { setItems(r.items); setTotal(r.total); setError(null); })
      .catch((err) => setError(err instanceof Error ? err.message : "Ачаалж чадсангүй"));
  }, [status, zone, type, page]);

  useEffect(load, [load]);

  // Шинэ violation ирэхэд эхний хуудсыг шууд шинэчилнэ
  useRealtimeEvents((event) => {
    if (event.type === "VIOLATION_CREATED" && page === 1) load();
    if (event.type === "VIOLATION_DELETED") {
      setItems((prev) => prev.filter((v) => v.id !== event.data.id));
      setSelected((cur) => (cur?.id === event.data.id ? null : cur));
      load(); // нийт тоо, хуудаслалтыг шинэчилнэ
    }
    if (event.type === "VIOLATION_UPDATED") {
      setItems((prev) => prev.map((v) => (v.id === event.data.id ? event.data : v)));
      setSelected((cur) => (cur?.id === event.data.id ? event.data : cur));
    }
  });

  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const change = <T,>(setter: (v: T) => void) => (value: T) => { setter(value); setPage(1); };

  return (
    <div className="min-w-0 space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex h-10 items-center rounded-lg border border-border bg-white p-1">
          {STATUSES.map((s) => (
            <button
              key={s.label}
              type="button"
              onClick={() => change(setStatus)(s.value)}
              className={cn("h-full rounded-md px-4 text-sm text-muted-foreground transition-colors hover:text-foreground", status === s.value && "bg-muted font-medium text-foreground")}
            >
              {s.label}
            </button>
          ))}
        </div>
        <NativeSelect className="h-10 w-40" aria-label="Бүс" value={zone} onChange={(e) => change(setZone)(e.target.value as ZoneName | "")}>
          <option value="">Бүх бүс</option><option value="FACTORY">Үйлдвэр</option><option value="OFFICE">Оффис</option>
        </NativeSelect>
        <NativeSelect className="h-10 w-48" aria-label="Зөрчлийн төрөл" value={type} onChange={(e) => change(setType)(e.target.value as ViolationType | "")}>
          <option value="">Бүх зөрчил</option><option value="NO_HELMET">Каскгүй</option><option value="NO_WORK_UNIFORM">Ажлын хувцасгүй</option>
          <option value="OTHER_SAFETY_VIOLATION">Хориотой бүсэд орсон</option>
        </NativeSelect>
        <span className="ml-auto text-sm text-muted-foreground">нийт {total}</span>
      </div>

      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
      <ViolationTable items={items} onOpen={setSelected} />

      <div className="flex items-center justify-end gap-2">
        <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Өмнөх</Button>
        <span className="text-sm text-muted-foreground">Хуудас {page} / {pages}</span>
        <Button variant="outline" size="sm" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>Дараах</Button>
      </div>

      <ViolationDetailDialog
        violation={selected}
        onClose={() => setSelected(null)}
        onChanged={(v) => { setSelected(v); setItems((prev) => prev.map((x) => (x.id === v.id ? v : x))); }}
        onDeleted={(id) => { setSelected(null); setItems((prev) => prev.filter((x) => x.id !== id)); load(); }}
      />
    </div>
  );
}
