"use client";

import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { useAuth } from "@/components/providers/auth-provider";
import { ViolationStatusBadge, ViolationTypeBadge } from "@/components/status-badges";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import { formatConfidence, formatTime, zoneLabel } from "@/lib/format";
import type { Violation } from "@/types";

const head = "h-11 px-3 text-[15px] font-medium text-muted-foreground";
const cell = "px-3 py-2.5 text-[15px]";
const checkClass = "size-4 rounded border-border accent-foreground";

function Snapshot({ url }: { url: string | null }) {
  return (
    <div className="aspect-video w-20 overflow-hidden rounded-lg bg-muted">
      {url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={url} alt="" className="size-full object-cover" loading="lazy" />
      ) : (
        <div className="grid size-full place-items-center text-[10px] text-muted-foreground">—</div>
      )}
    </div>
  );
}

function SelectAll({ checked, indeterminate, onChange }: { checked: boolean; indeterminate: boolean; onChange: () => void }) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = indeterminate;
  }, [indeterminate]);
  return (
    <input
      ref={ref}
      type="checkbox"
      className={checkClass}
      checked={checked}
      onChange={onChange}
      aria-label="Бүгдийг сонгох"
    />
  );
}

export function ViolationTable({
  items, onOpen, onChanged, onDeleted, empty = "Зөрчил алга",
}: {
  items: Violation[];
  onOpen: (v: Violation) => void;
  onChanged?: (v: Violation) => void;
  onDeleted?: (id: string) => void;
  empty?: string;
}) {
  const { can } = useAuth();
  const staff = can("ADMIN", "HUB_EMPLOYEE");
  const admin = can("ADMIN");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const columns = staff ? 9 : 8;

  useEffect(() => {
    const ids = new Set(items.map((v) => v.id));
    setSelected((prev) => {
      let changed = false;
      const next = new Set<string>();
      for (const id of prev) {
        if (ids.has(id)) next.add(id);
        else changed = true;
      }
      return changed ? next : prev;
    });
  }, [items]);

  const chosen = items.filter((v) => selected.has(v.id));
  const openOnes = chosen.filter((v) => v.status === "OPEN");
  const resolvable = chosen.filter((v) => v.status !== "RESOLVED");
  const allChecked = items.length > 0 && items.every((v) => selected.has(v.id));

  function toggle(id: string) {
    setConfirmDelete(false);
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAll() {
    setConfirmDelete(false);
    setSelected(allChecked ? new Set() : new Set(items.map((v) => v.id)));
  }

  async function run(kind: "acknowledge" | "resolve") {
    const targets = kind === "acknowledge" ? openOnes : resolvable;
    if (!targets.length) return;
    setBusy(true);
    const results = await Promise.allSettled(targets.map((v) => (kind === "acknowledge" ? api.acknowledge(v.id) : api.resolve(v.id))));
    let ok = 0;
    results.forEach((result, index) => {
      if (result.status === "fulfilled") {
        ok += 1;
        onChanged?.(result.value);
        setSelected((prev) => {
          const next = new Set(prev);
          next.delete(targets[index].id);
          return next;
        });
      }
    });
    setBusy(false);
    if (ok === targets.length) toast.success(kind === "acknowledge" ? `${ok} зөрчлийг хүлээн авлаа` : `${ok} зөрчлийг шийдвэрлэлээ`);
    else toast.error(`${ok} амжилттай, ${targets.length - ok} амжилтгүй`);
  }

  async function remove() {
    if (!chosen.length) return;
    setBusy(true);
    const results = await Promise.allSettled(chosen.map((v) => api.deleteViolation(v.id)));
    let ok = 0;
    results.forEach((result, index) => {
      if (result.status === "fulfilled") {
        ok += 1;
        onDeleted?.(chosen[index].id);
        setSelected((prev) => {
          const next = new Set(prev);
          next.delete(chosen[index].id);
          return next;
        });
      }
    });
    setBusy(false);
    setConfirmDelete(false);
    if (ok === chosen.length) toast.success(`${ok} зөрчлийг устгалаа`);
    else toast.error(`${ok} устгасан, ${chosen.length - ok} амжилтгүй`);
  }

  return (
    <div className="max-w-full overflow-hidden rounded-xl border border-border bg-card shadow-surface">
      {staff && chosen.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 border-b border-border bg-muted px-3 py-2.5">
          <span className="text-[15px] font-medium text-foreground">{chosen.length} сонгосон</span>
          <div className="ml-auto flex flex-wrap items-center justify-end gap-2">
            {confirmDelete ? (
              <>
                <span className="text-[15px] text-danger">Сонгосон зөрчлийг бүрмөсөн устгах уу?</span>
                <Button variant="destructive" className="h-8 px-2.5 text-[15px]" disabled={busy} onClick={remove}>Тийм, устгах</Button>
                <Button variant="ghost" className="h-8 px-2.5 text-[15px]" disabled={busy} onClick={() => setConfirmDelete(false)}>Болих</Button>
              </>
            ) : (
              <>
                {openOnes.length > 0 && (
                  <Button variant="outline" className="h-8 px-2.5 text-[15px]" disabled={busy} onClick={() => run("acknowledge")}>Хүлээн авах</Button>
                )}
                {resolvable.length > 0 && (
                  <Button className="h-8 px-2.5 text-[15px]" disabled={busy} onClick={() => run("resolve")}>Шийдвэрлэх</Button>
                )}
                {admin && (
                  <Button variant="ghost" className="h-8 px-2.5 text-[15px] text-danger hover:text-danger" disabled={busy} onClick={() => setConfirmDelete(true)}>Устгах</Button>
                )}
                <Button variant="ghost" className="h-8 px-2.5 text-[15px]" disabled={busy} onClick={() => setSelected(new Set())}>Болих</Button>
              </>
            )}
          </div>
        </div>
      )}
      <Table>
        <TableHeader className="bg-muted">
          <TableRow className="border-border hover:bg-transparent">
            {staff && (
              <TableHead className={`${head} w-11`}>
                <SelectAll checked={allChecked} indeterminate={!allChecked && chosen.length > 0} onChange={toggleAll} />
              </TableHead>
            )}
            <TableHead className={`${head} sticky left-0 z-10 bg-muted`}>Зураг</TableHead>
            <TableHead className={head}>Зөрчил</TableHead>
            <TableHead className={head}>Камер</TableHead>
            <TableHead className={head}>Бүс</TableHead>
            <TableHead className={`${head} text-right`}>Итгэлцэл</TableHead>
            <TableHead className={head}>Илрүүлсэн</TableHead>
            <TableHead className={head}>Төлөв</TableHead>
            <TableHead className={`${head} text-right`}>Үйлдэл</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.length === 0 && (
            <TableRow className="hover:bg-transparent">
              <TableCell colSpan={columns} className="py-8 text-center text-sm text-muted-foreground">{empty}</TableCell>
            </TableRow>
          )}
          {items.map((v) => (
            <TableRow key={v.id} className="group cursor-pointer border-border hover:bg-muted" onClick={() => onOpen(v)}>
              {staff && (
                <TableCell className={cell} onClick={(e) => e.stopPropagation()}>
                  <input
                    type="checkbox"
                    className={checkClass}
                    checked={selected.has(v.id)}
                    onChange={() => toggle(v.id)}
                    aria-label={`${v.camera_name} зөрчлийг сонгох`}
                  />
                </TableCell>
              )}
              <TableCell className={`${cell} sticky left-0 bg-card group-hover:bg-muted`}><Snapshot url={v.snapshot_url} /></TableCell>
              <TableCell className={cell}><ViolationTypeBadge type={v.violation_type} className="h-6 px-2.5 text-[13px]" /></TableCell>
              <TableCell className={`${cell} max-w-40`}>
                <span className="block truncate" title={v.camera_name}>{v.camera_name}</span>
              </TableCell>
              <TableCell className={`${cell} text-muted-foreground`}>{zoneLabel(v.zone)}</TableCell>
              <TableCell className={`${cell} text-right tabular-nums`}>{formatConfidence(v.confidence)}</TableCell>
              <TableCell className={`${cell} whitespace-nowrap tabular-nums text-muted-foreground`}>{formatTime(v.detected_at)}</TableCell>
              <TableCell className={cell}><ViolationStatusBadge status={v.status} className="h-6 px-2.5 text-[13px]" /></TableCell>
              <TableCell className={`${cell} text-right`}>
                <Button variant="ghost" size="sm" className="h-8 px-2.5 text-[15px]" onClick={(e) => { e.stopPropagation(); onOpen(v); }}>Харах</Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
