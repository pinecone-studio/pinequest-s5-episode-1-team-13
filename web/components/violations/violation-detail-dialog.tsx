"use client";

import { useState } from "react";
import { toast } from "sonner";

import { ViolationStatusBadge, ViolationTypeBadge } from "@/components/status-badges";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useAuth } from "@/components/providers/auth-provider";
import { api } from "@/lib/api";
import { formatConfidence, formatTime, VIOLATION_LABEL, zoneLabel } from "@/lib/format";
import type { Violation } from "@/types";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      <div className="text-sm">{children}</div>
    </div>
  );
}

export function ViolationDetailDialog({
  violation, onClose, onChanged, onDeleted,
}: { violation: Violation | null; onClose: () => void; onChanged: (v: Violation) => void; onDeleted: (id: string) => void }) {
  const { can } = useAuth();
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const staff = can("ADMIN", "HUB_EMPLOYEE");
  const admin = can("ADMIN");

  async function remove() {
    if (!violation) return;
    setBusy(true);
    try {
      await api.deleteViolation(violation.id);
      onDeleted(violation.id);
      toast.success("Зөрчлийг устгалаа");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Устгаж чадсангүй");
    } finally {
      setBusy(false);
      setConfirmDelete(false);
    }
  }

  async function act(kind: "acknowledge" | "resolve") {
    if (!violation) return;
    setBusy(true);
    try {
      const updated = await (kind === "acknowledge" ? api.acknowledge(violation.id) : api.resolve(violation.id));
      onChanged(updated);
      toast.success(kind === "acknowledge" ? "Зөрчлийг хүлээн авлаа" : "Зөрчлийг шийдвэрлэлээ");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Үйлдэл амжилтгүй боллоо");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={!!violation} onOpenChange={(open) => { if (!open) { setConfirmDelete(false); onClose(); } }}>
      <DialogContent className="sm:max-w-3xl">
        {violation && (
          <>
            <DialogHeader>
              <DialogTitle>{VIOLATION_LABEL[violation.violation_type]}</DialogTitle>
              <DialogDescription>{violation.camera_name} · {formatTime(violation.detected_at)}</DialogDescription>
            </DialogHeader>
            <div className="overflow-hidden rounded-lg border bg-black">
              {violation.snapshot_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={violation.snapshot_url} alt="Зөрчлийн зураг" className="max-h-[60vh] w-full object-contain" />
              ) : (
                <div className="grid h-48 place-items-center text-sm text-muted-foreground">Зураг байхгүй</div>
              )}
            </div>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
              <Field label="Зөрчлийн төрөл"><ViolationTypeBadge type={violation.violation_type} /></Field>
              <Field label="Камер">{violation.camera_name}</Field>
              <Field label="Бүс">{zoneLabel(violation.zone)}</Field>
              <Field label="Итгэлцэл">{formatConfidence(violation.confidence)}</Field>
              <Field label="Хүний ID">{violation.person_id ?? "—"}</Field>
              <Field label="Илрүүлсэн цаг">{formatTime(violation.detected_at)}</Field>
              <Field label="Төлөв"><ViolationStatusBadge status={violation.status} /></Field>
              {violation.resolved_at && <Field label="Шийдвэрлэсэн">{formatTime(violation.resolved_at)} · {violation.resolved_by}</Field>}
            </div>
            {(admin || (staff && violation.status !== "RESOLVED")) && (
              <div className="flex flex-wrap items-center justify-end gap-2">
                {admin && (
                  confirmDelete ? (
                    <div className="mr-auto flex items-center gap-2">
                      <span className="text-sm text-danger">Зураг, бүртгэл бүрмөсөн устна. Итгэлтэй байна уу?</span>
                      <Button variant="destructive" disabled={busy} onClick={remove}>Тийм, устгах</Button>
                      <Button variant="ghost" disabled={busy} onClick={() => setConfirmDelete(false)}>Болих</Button>
                    </div>
                  ) : (
                    <Button variant="ghost" className="mr-auto text-danger hover:text-danger" disabled={busy} onClick={() => setConfirmDelete(true)}>Устгах</Button>
                  )
                )}
                {staff && violation.status === "OPEN" && (
                  <Button variant="outline" disabled={busy} onClick={() => act("acknowledge")}>Хүлээн авах</Button>
                )}
                {staff && violation.status !== "RESOLVED" && (
                  <Button disabled={busy} onClick={() => act("resolve")}>Шийдвэрлэх</Button>
                )}
              </div>
            )}
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
