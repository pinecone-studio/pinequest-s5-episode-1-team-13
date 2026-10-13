"use client";

import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ViolationStatusBadge, ViolationTypeBadge } from "@/components/status-badges";
import { formatConfidence, formatTime, zoneLabel } from "@/lib/format";
import type { Violation } from "@/types";

export function ViolationTable({ items, onOpen, empty = "Зөрчил алга" }: { items: Violation[]; onOpen: (v: Violation) => void; empty?: string }) {
  return (
    <div className="overflow-x-auto rounded-xl border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Зураг</TableHead>
            <TableHead>Зөрчил</TableHead>
            <TableHead>Камер</TableHead>
            <TableHead>Бүс</TableHead>
            <TableHead>Итгэлцэл</TableHead>
            <TableHead>Илрүүлсэн</TableHead>
            <TableHead>Төлөв</TableHead>
            <TableHead className="text-right">Үйлдэл</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.length === 0 && (
            <TableRow><TableCell colSpan={8} className="py-10 text-center text-muted-foreground">{empty}</TableCell></TableRow>
          )}
          {items.map((v) => (
            <TableRow key={v.id} className="cursor-pointer" onClick={() => onOpen(v)}>
              <TableCell>
                {v.snapshot_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={v.snapshot_url} alt="" className="h-12 w-20 rounded object-cover" loading="lazy" />
                ) : (
                  <div className="grid h-12 w-20 place-items-center rounded bg-muted text-[10px] text-muted-foreground">—</div>
                )}
              </TableCell>
              <TableCell><ViolationTypeBadge type={v.violation_type} /></TableCell>
              <TableCell>{v.camera_name}</TableCell>
              <TableCell>{zoneLabel(v.zone)}</TableCell>
              <TableCell>{formatConfidence(v.confidence)}</TableCell>
              <TableCell className="whitespace-nowrap text-muted-foreground">{formatTime(v.detected_at)}</TableCell>
              <TableCell><ViolationStatusBadge status={v.status} /></TableCell>
              <TableCell className="text-right">
                <Button variant="outline" size="sm" onClick={(e) => { e.stopPropagation(); onOpen(v); }}>Харах</Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
