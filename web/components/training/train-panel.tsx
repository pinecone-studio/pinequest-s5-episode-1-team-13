"use client";

import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { NativeSelect } from "@/components/native-select";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import { CLASS_INFO } from "@/components/training/labeler";
import type { TrainClass, TrainingStatus, TrainState } from "@/types";

const STATE_LABEL: Record<TrainState["state"], string> = {
  idle: "Сургалт хийгдээгүй", running: "Сургаж байна…", done: "Дууслаа", failed: "Алдаа гарлаа", stopped: "Зогсоосон",
};

export function TrainPanel({ status }: { status: TrainingStatus }) {
  const [state, setState] = useState<TrainState | null>(null);
  const [epochs, setEpochs] = useState(40);
  const [base, setBase] = useState<"n" | "s">("n");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(() => api.trainState().then(setState).catch(() => undefined), []);
  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => {
    if (state?.state !== "running") return;
    const timer = setInterval(refresh, 3000);
    return () => clearInterval(timer);
  }, [state?.state, refresh]);

  const enough = status.labeled_count >= status.min_labeled;
  const running = state?.state === "running";
  const weightsReady = status.models_available[base];

  async function start() {
    setBusy(true);
    try {
      setState(await api.startTraining(epochs, base));
      toast.success("Сургалт эхэллээ");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Сургалт эхлүүлж чадсангүй");
    } finally {
      setBusy(false);
    }
  }

  async function stop() {
    try {
      await api.stopTraining();
      refresh();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Зогсоож чадсангүй");
    }
  }

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader><CardTitle className="text-xs font-semibold tracking-[0.2em] text-muted-foreground">МОДЕЛЬ СУРГАХ</CardTitle></CardHeader>
        <CardContent className="space-y-4 text-sm">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="tr-base">Суурь модель</Label>
              <NativeSelect id="tr-base" value={base} disabled={running} onChange={(e) => setBase(e.target.value as "n" | "s")}>
                <option value="n">YOLO26n — хурдан, жижиг</option>
                <option value="s">YOLO26s — нарийвчлалтай, удаан</option>
              </NativeSelect>
            </div>
            <div className="space-y-2">
              <Label htmlFor="tr-epochs">Epoch ({status.epochs_min}–{status.epochs_max})</Label>
              <Input id="tr-epochs" type="number" min={status.epochs_min} max={status.epochs_max} value={epochs} disabled={running}
                onChange={(e) => setEpochs(Number(e.target.value))} />
            </div>
          </div>

          {!enough && <p className="text-xs text-amber-300">Шошглосон зураг {status.labeled_count}/{status.min_labeled}. «Шошглох» хэсэгт үргэлжлүүлнэ үү.</p>}
          {!weightsReady && <p className="text-xs text-red-300">training/models/base-{base}.pt суурь жин олдсонгүй.</p>}

          <div className="flex gap-2">
            <Button disabled={busy || running || !enough || !weightsReady} onClick={start}>Сургах</Button>
            {running && <Button variant="outline" onClick={stop}>Зогсоох</Button>}
          </div>

          <p className="text-xs text-muted-foreground">
            Сургалт энэ компьютер дээр явагдана (интернэтээс юу ч татахгүй). Apple GPU (MPS) ашиглана; 300 зураг, 40 epoch ойролцоогоор
            10–40 минут. Явагдаж байх хооронд dashboard болон камер хэвийн ажиллана.
          </p>
          <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200">
            Суурь жин нь ерөнхий (COCO) модель тул цөөн зургаар сургавал одоогийн моделоос <b>муу</b> гарч болно. Шинэ моделийг
            заавал доорх test үнэлгээгээр шалгаж, харьцуулж байж идэвхжүүлнэ.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-xs font-semibold tracking-[0.2em] text-muted-foreground">
            ТӨЛӨВ · {state ? STATE_LABEL[state.state] : "…"}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          {running && state?.epochs && (
            <div className="space-y-1">
              <div className="h-2 overflow-hidden rounded-full bg-muted">
                <div className="h-full bg-primary transition-all" style={{ width: `${((state.epoch ?? 0) / state.epochs) * 100}%` }} />
              </div>
              <div className="text-xs text-muted-foreground">Epoch {state.epoch ?? 0} / {state.epochs}</div>
            </div>
          )}
          {state?.message && state.state !== "running" && <p className={state.state === "failed" ? "text-red-300" : "text-muted-foreground"}>{state.message}</p>}

          {state?.state === "done" && state.metrics && (
            <div className="space-y-3">
              <div className="text-xs text-muted-foreground">
                Test өгөгдөл ({state.metrics.images.test} зураг, сургалтад ороогүй): mAP50 <b className="text-foreground">{state.metrics.map50}</b> · mAP50-95 {state.metrics.map50_95}
              </div>
              <div className="overflow-x-auto rounded-xl border">
                <Table>
                  <TableHeader><TableRow><TableHead>Ангилал</TableHead><TableHead>Нарийвчлал</TableHead><TableHead>Илрүүлэлт</TableHead><TableHead>mAP50</TableHead></TableRow></TableHeader>
                  <TableBody>
                    {Object.entries(state.metrics.per_class).map(([cls, m]) => (
                      <TableRow key={cls}>
                        <TableCell>{CLASS_INFO[cls as TrainClass]?.label ?? cls}</TableCell>
                        <TableCell>{m.precision}</TableCell><TableCell>{m.recall}</TableCell><TableCell>{m.map50}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
              <p className="text-xs text-muted-foreground">Test-д байхгүй ангилал дээр дүн гарахгүй. Test цөөн зурагтай бол тоо найдвартай биш.</p>
              <div className="rounded-lg border bg-muted/30 p-3 text-xs">
                <div className="mb-1 font-medium">Идэвхжүүлэх (шинэ моделоо туршихаар шийдсэн бол):</div>
                <ol className="list-decimal space-y-1 pl-4 text-muted-foreground">
                  <li><code>ai-service/.env</code> файлд: <code>MODEL_PATH=../{state.model_file}</code> болгож, <code>CLASS_MAPPING=</code> хоосон үлдээнэ.</li>
                  <li><code>worker</code>-ийг ⌃C-ээр зогсоогоод дахин асаана.</li>
                  <li>Муу гарвал <code>MODEL_PATH=./models/ppe-custom.onnx</code> болгож буцаана (хуучин модель устахгүй).</li>
                </ol>
              </div>
            </div>
          )}

          {state?.log_tail && (
            <pre className="max-h-56 overflow-auto rounded-lg bg-black/60 p-3 text-[11px] leading-snug text-zinc-300">{state.log_tail}</pre>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
