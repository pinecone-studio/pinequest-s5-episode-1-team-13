"use client";

import { useState } from "react";
import { toast } from "sonner";

import { NativeSelect } from "@/components/native-select";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import type { TrainingStatus } from "@/types";

const INTERVALS = [5, 10, 30, 60, 300];

export function CollectionPanel({ status, onChanged }: { status: TrainingStatus; onChanged: () => void }) {
  const { collection } = status;
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  async function update(enabled: boolean, interval: number) {
    setBusy(true);
    try {
      await api.setCollection(enabled, interval);
      toast.success(enabled ? "Өгөгдөл цуглуулалт асалаа (10 секундын дотор хэрэгжинэ)" : "Өгөгдөл цуглуулалт унтарлаа");
      onChanged();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Амжилтгүй боллоо");
    } finally {
      setBusy(false);
    }
  }

  async function removeAll() {
    if (!confirmDelete) { setConfirmDelete(true); return; }
    setBusy(true);
    try {
      const res = await api.deleteAllTrainingImages();
      toast.success(`${res.deleted} зураг (шошготой нь хамт) устгагдлаа`);
      setConfirmDelete(false);
      onChanged();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Устгаж чадсангүй");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card>
        <CardHeader><CardTitle className="text-xs font-semibold tracking-[0.2em] text-muted-foreground">ӨГӨГДӨЛ ЦУГЛУУЛАЛТ</CardTitle></CardHeader>
        <CardContent className="space-y-4 text-sm">
          <label className="flex cursor-pointer items-center gap-3">
            <input type="checkbox" className="size-4 accent-primary" checked={collection.enabled} disabled={busy}
              onChange={(e) => update(e.target.checked, collection.interval_seconds)} />
            <span className="font-medium">Ажиллаж буй камеруудаас зураг цуглуулах</span>
          </label>
          <div className="flex items-center gap-3">
            <span className="text-muted-foreground">Хүн харагдахад</span>
            <NativeSelect className="w-36" value={collection.interval_seconds} disabled={busy}
              onChange={(e) => update(collection.enabled, Number(e.target.value))} aria-label="Давтамж">
              {[...new Set([...INTERVALS, collection.interval_seconds])].sort((a, b) => a - b).map((s) => (
                <option key={s} value={s}>{s} сек тутам</option>
              ))}
            </NativeSelect>
          </div>
          <p className="text-xs text-muted-foreground">
            Хүн байхгүй зургийг 5 дахин ховор авна (AI-ийн худал дохиог бууруулах «хоосон» жишээ). Дээд хязгаар {collection.max_images} зураг.
            Хязгаарт хүрвэл цуглуулалт өөрөө зогсоно.
          </p>
          <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200">
            Зурагт хүмүүсийн царай орно. Зургууд зөвхөн энэ компьютерийн <code>training/datasets/</code> хавтсанд хадгалагдаж, git-д орохгүй.
            Асаахаасаа өмнө ажилтнуудад мэдэгдсэн эсэхээ шалгана уу.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-xs font-semibold tracking-[0.2em] text-muted-foreground">ЦУГЛУУЛСАН ӨГӨГДӨЛ</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-3 gap-3 text-center">
            <Stat label="Нийт зураг" value={status.image_count} />
            <Stat label="Шошглосон" value={status.labeled_count} />
            <Stat label="Хэмжээ" value={`${(status.size_bytes / 1048576).toFixed(0)} MB`} />
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-muted">
            <div className="h-full bg-primary" style={{ width: `${Math.min(100, (status.labeled_count / status.min_labeled) * 100)}%` }} />
          </div>
          <p className="text-xs text-muted-foreground">
            Сургахад дор хаяж {status.min_labeled} шошглосон зураг хэрэгтэй. Чанартай үр дүнд 300+ зураг, ажлын хувцас болон бусад
            нөхцөлийг (гэрэл, өнцөг, хувцасгүй хүн) хамарсан байх нь зүйтэй.
          </p>
          <Button variant={confirmDelete ? "destructive" : "outline"} size="sm" disabled={busy || status.image_count === 0} onClick={removeAll}
            onBlur={() => setConfirmDelete(false)}>
            {confirmDelete ? "Баталгаажуулах: бүгдийг устгах" : "Бүх зургийг устгах"}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-lg border p-3">
      <div className="text-2xl font-semibold">{value}</div>
      <div className="text-[11px] text-muted-foreground">{label}</div>
    </div>
  );
}
