"use client";

import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ViolationStatusBadge, ViolationTypeBadge } from "@/components/status-badges";
import { formatConfidence, formatTime, zoneLabel } from "@/lib/format";
import type { Violation } from "@/types";

const head = "h-9 px-3 text-xs font-medium text-muted-foreground";
const cell = "px-3 py-2";

function Snapshot({ url }: { url: string | null }) {
  return (
    <div className="aspect-video w-20 overflow-hidden rounded-md bg-muted">
      {url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={url} alt="" className="size-full object-cover" loading="lazy" />
      ) : (
        <div className="grid size-full place-items-center text-[10px] text-muted-foreground">—</div>
      )}
    </div>
  );
}

export function ViolationTable({ items, onOpen, empty = "Зөрчил алга" }: { items: Violation[]; onOpen: (v: Violation) => void; empty?: string }) {
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card">
      <Table>
        <TableHeader className="bg-muted">
          <TableRow className="border-border hover:bg-transparent">
            <TableHead className={head}>Зураг</TableHead>
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
              <TableCell colSpan={8} className="py-8 text-center text-sm text-muted-foreground">{empty}</TableCell>
            </TableRow>
          )}
          {items.map((v) => (
            <TableRow key={v.id} className="cursor-pointer border-border hover:bg-muted/40" onClick={() => onOpen(v)}>
              <TableCell className={cell}><Snapshot url={v.snapshot_url} /></TableCell>
              <TableCell className={cell}><ViolationTypeBadge type={v.violation_type} /></TableCell>
              <TableCell className={`${cell} max-w-40`}>
                <span className="block truncate" title={v.camera_name}>{v.camera_name}</span>
              </TableCell>
              <TableCell className={`${cell} text-muted-foreground`}>{zoneLabel(v.zone)}</TableCell>
              <TableCell className={`${cell} text-right tabular-nums`}>{formatConfidence(v.confidence)}</TableCell>
              <TableCell className={`${cell} whitespace-nowrap tabular-nums text-muted-foreground`}>{formatTime(v.detected_at)}</TableCell>
              <TableCell className={cell}><ViolationStatusBadge status={v.status} /></TableCell>
              <TableCell className={`${cell} text-right`}>
                <Button variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={(e) => { e.stopPropagation(); onOpen(v); }}>Харах</Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
