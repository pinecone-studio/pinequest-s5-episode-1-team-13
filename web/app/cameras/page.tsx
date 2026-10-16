"use client";

import { useCallback, useEffect, useState } from "react";
import { Plus } from "lucide-react";
import { toast } from "sonner";

import { CameraFormDialog } from "@/components/cameras/camera-form-dialog";
import { useAuth } from "@/components/providers/auth-provider";
import { useRealtimeEvents } from "@/components/providers/realtime-provider";
import { CameraStatusBadge } from "@/components/status-badges";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import { CAMERA_TYPE_LABEL, cameraAddress, formatTime, zoneLabel } from "@/lib/format";
import type { Camera, Zone } from "@/types";

export default function CamerasPage() {
  const { canManageCameras: admin } = useAuth();
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [zones, setZones] = useState<Zone[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Camera | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [deleting, setDeleting] = useState<Camera | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.cameras(), api.zones()])
      .then(([c, z]) => { setCameras(c); setZones(z); })
      .catch((err) => setError(err instanceof Error ? err.message : "Ачаалж чадсангүй"));
  }, []);

  const upsert = useCallback((camera: Camera) => {
    setCameras((prev) => (prev.some((c) => c.id === camera.id) ? prev.map((c) => (c.id === camera.id ? camera : c)) : [...prev, camera]));
  }, []);

  useRealtimeEvents((event) => {
    if (event.type === "CAMERA_UPDATED") upsert(event.data);
    if (event.type === "CAMERA_DELETED") setCameras((prev) => prev.filter((c) => c.id !== event.data.id));
  });

  async function run(camera: Camera, action: () => Promise<unknown>, success?: string) {
    setBusyId(camera.id);
    try {
      await action();
      if (success) toast.success(success);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Үйлдэл амжилтгүй боллоо");
    } finally {
      setBusyId(null);
    }
  }

  const test = (camera: Camera) =>
    run(camera, async () => {
      const result = await api.testCamera(camera.id);
      (result.success ? toast.success : toast.error)(result.success ? "Камер амжилттай холбогдлоо" : "RTSP stream-д холбогдож чадсангүй", { description: result.reason ?? result.resolution ?? undefined });
    });

  return (
    <div className="min-w-0 space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">Нийт {cameras.length} камер</p>
        {admin && (
          <Button onClick={() => { setEditing(null); setFormOpen(true); }}><Plus className="size-4" /> Камер нэмэх</Button>
        )}
      </div>
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}

      <div className="overflow-hidden rounded-lg border border-border bg-card">
        <Table>
          <TableHeader className="bg-muted [&_th]:h-9 [&_th]:px-3 [&_th]:text-xs [&_th]:font-medium [&_th]:text-muted-foreground">
            <TableRow className="border-border hover:bg-transparent">
              <TableHead>Камерын нэр</TableHead><TableHead>IP хаяг</TableHead><TableHead>Порт</TableHead>
              <TableHead>Төрөл</TableHead><TableHead>Бүс</TableHead><TableHead>Төлөв</TableHead>
              <TableHead>Сүүлд холбогдсон</TableHead>{admin && <TableHead className="text-right">Үйлдэл</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {cameras.length === 0 && (
              <TableRow><TableCell colSpan={8} className="py-10 text-center text-muted-foreground">Камер алга</TableCell></TableRow>
            )}
            {cameras.map((c) => (
              <TableRow key={c.id}>
                <TableCell className="font-medium">{c.name}</TableCell>
                <TableCell>{cameraAddress(c)}</TableCell>
                <TableCell>{c.camera_type === "LOCAL_WEBCAM" || c.camera_type === "BROWSER" ? "—" : c.rtsp_port}</TableCell>
                <TableCell>{CAMERA_TYPE_LABEL[c.camera_type]}</TableCell>
                <TableCell>{zoneLabel(c.zone)}</TableCell>
                <TableCell><CameraStatusBadge status={c.status} /></TableCell>
                <TableCell className="whitespace-nowrap text-muted-foreground">{formatTime(c.last_connected_at)}</TableCell>
                {admin && (
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-1.5">
                      <Button size="sm" variant="outline" disabled={busyId === c.id} onClick={() => test(c)}>Шалгах</Button>
                      {c.enabled ? (
                        <Button size="sm" variant="outline" disabled={busyId === c.id} onClick={() => run(c, async () => upsert(await api.disconnectCamera(c.id)), "Камерыг салгалаа")}>Салгах</Button>
                      ) : (
                        <Button size="sm" variant="outline" disabled={busyId === c.id} onClick={() => run(c, async () => upsert(await api.connectCamera(c.id)), "Камер холбогдож байна")}>Холбох</Button>
                      )}
                      <Button size="sm" variant="outline" onClick={() => { setEditing(c); setFormOpen(true); }}>Засах</Button>
                      <Button size="sm" variant="destructive" onClick={() => setDeleting(c)}>Устгах</Button>
                    </div>
                  </TableCell>
                )}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <CameraFormDialog open={formOpen} camera={editing} zones={zones} onClose={() => setFormOpen(false)} onSaved={upsert} />

      <Dialog open={!!deleting} onOpenChange={(o) => !o && setDeleting(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>«{deleting?.name}» камерыг устгах уу?</DialogTitle>
            <DialogDescription>
              Камерт зөрчлийн бүртгэл байвал нотолгоо устахаас сэргийлж устгахгүй. Тэр тохиолдолд «Салгах» товчийг ашиглана уу.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDeleting(null)}>Болих</Button>
            <Button
              variant="destructive"
              onClick={() => {
                const target = deleting!;
                setDeleting(null);
                run(target, async () => { await api.deleteCamera(target.id); setCameras((prev) => prev.filter((c) => c.id !== target.id)); }, "Камерыг устгалаа");
              }}
            >
              Устгах
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
