"use client";

/* eslint-disable @next/next/no-img-element -- зураг нь нэвтрэлттэй API-аас ирдэг тул next/image ашиглахгүй */

import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { NativeSelect } from "@/components/native-select";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import type { LabelBox, TrainClass, TrainingImage } from "@/types";

// Хүн (person) шошглолтод байхгүй: AI/COCO моделоор автоматаар нэмэгдэнэ. Зөв (каск, хувцас) = ногоон, буруу = улаан.
const CLASS_ORDER: TrainClass[] = ["helmet", "no_helmet", "work_uniform", "no_work_uniform"];
export const CLASS_INFO: Record<TrainClass, { label: string; color: string; hint: string }> = {
  helmet: { label: "Каск", color: "#4ade80", hint: "Каск өмссөн толгой (зөвхөн каскийг)" },
  no_helmet: { label: "Каскгүй", color: "#f87171", hint: "Каск өмсөөгүй хүний толгой" },
  work_uniform: { label: "Ажлын хувцас", color: "#16a34a", hint: "Ажлын хувцастай их бие" },
  no_work_uniform: { label: "Ажлын хувцасгүй", color: "#dc2626", hint: "Энгийн хувцастай их бие" },
  person: { label: "Хүн", color: "#3b82f6", hint: "Автоматаар нэмэгдэнэ" },
};

interface Box extends LabelBox { id: number }
type Corner = "nw" | "ne" | "sw" | "se";
type Drag =
  | { kind: "draw"; id: number; sx: number; sy: number }
  | { kind: "move"; id: number; dx: number; dy: number }
  | { kind: "resize"; id: number; corner: Corner }
  | null;

const PAGE = 24;
const MIN_SIZE = 0.012;
const clamp = (v: number, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, v));
const CORNERS: { corner: Corner; cls: string }[] = [
  { corner: "nw", cls: "-left-1.5 -top-1.5 cursor-nwse-resize" },
  { corner: "ne", cls: "-right-1.5 -top-1.5 cursor-nesw-resize" },
  { corner: "sw", cls: "-bottom-1.5 -left-1.5 cursor-nesw-resize" },
  { corner: "se", cls: "-bottom-1.5 -right-1.5 cursor-nwse-resize" },
];

export function Labeler({ onChanged }: { onChanged: () => void }) {
  const [filter, setFilter] = useState<"all" | "unlabeled" | "labeled">("unlabeled");
  const [items, setItems] = useState<TrainingImage[]>([]);
  const [total, setTotal] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [boxes, setBoxes] = useState<Box[]>([]);
  const [source, setSource] = useState<"manual" | "auto" | "none">("none");
  const [activeId, setActiveId] = useState<number | null>(null);
  const [drawClass, setDrawClass] = useState<TrainClass>("work_uniform");
  const [aspect, setAspect] = useState(16 / 9);
  const [busy, setBusy] = useState(false);

  const surfaceRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<Drag>(null);
  const nextId = useRef(1);

  const loadList = useCallback(async (f: typeof filter, offset: number, append: boolean) => {
    try {
      const page = await api.trainingImages(f, offset, PAGE);
      setTotal(page.total);
      setItems((prev) => (append ? [...prev, ...page.items] : page.items));
      return page.items;
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Зургийн жагсаалтыг ачаалж чадсангүй");
      return [];
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    api.trainingImages(filter, 0, PAGE).then((page) => {
      if (cancelled) return;
      setTotal(page.total);
      setItems(page.items);
      setSelected((cur) => cur ?? page.items[0]?.name ?? null);
    }).catch((err) => toast.error(err instanceof Error ? err.message : "Зургийн жагсаалтыг ачаалж чадсангүй"));
    return () => { cancelled = true; };
  }, [filter]);

  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    api.trainingLabels(selected).then((res) => {
      if (cancelled) return;
      setBoxes(res.boxes.filter((b) => b.class_name !== "person").map((b) => ({ ...b, id: nextId.current++ }))); // хүн шошглолтод харагдахгүй
      setSource(res.source);
      setActiveId(null);
    }).catch((err) => toast.error(err instanceof Error ? err.message : "Шошгыг ачаалж чадсангүй"));
    return () => { cancelled = true; };
  }, [selected]);

  const patch = (id: number, change: Partial<LabelBox>) =>
    setBoxes((prev) => prev.map((b) => (b.id === id ? { ...b, ...change } : b)));

  const point = (e: React.PointerEvent) => {
    const r = surfaceRef.current!.getBoundingClientRect();
    return { x: clamp((e.clientX - r.left) / r.width), y: clamp((e.clientY - r.top) / r.height) };
  };

  function onPointerDown(e: React.PointerEvent) {
    if (!selected || e.button !== 0) return;
    const target = e.target as HTMLElement;
    const handle = target.closest<HTMLElement>("[data-corner]");
    const boxEl = target.closest<HTMLElement>("[data-box-id]");
    const p = point(e);
    surfaceRef.current!.setPointerCapture(e.pointerId);
    if (handle && boxEl) {
      const id = Number(boxEl.dataset.boxId);
      setActiveId(id);
      dragRef.current = { kind: "resize", id, corner: handle.dataset.corner as Corner };
    } else if (boxEl) {
      const id = Number(boxEl.dataset.boxId);
      const b = boxes.find((x) => x.id === id)!;
      setActiveId(id);
      dragRef.current = { kind: "move", id, dx: p.x - b.x1, dy: p.y - b.y1 };
    } else {
      const id = nextId.current++;
      setBoxes((prev) => [...prev, { id, class_name: drawClass, x1: p.x, y1: p.y, x2: p.x, y2: p.y }]);
      setActiveId(id);
      dragRef.current = { kind: "draw", id, sx: p.x, sy: p.y };
    }
  }

  function onPointerMove(e: React.PointerEvent) {
    const drag = dragRef.current;
    if (!drag) return;
    const p = point(e);
    if (drag.kind === "draw") {
      patch(drag.id, { x1: Math.min(drag.sx, p.x), y1: Math.min(drag.sy, p.y), x2: Math.max(drag.sx, p.x), y2: Math.max(drag.sy, p.y) });
    } else if (drag.kind === "move") {
      setBoxes((prev) => prev.map((b) => {
        if (b.id !== drag.id) return b;
        const w = b.x2 - b.x1, h = b.y2 - b.y1;
        const x1 = clamp(p.x - drag.dx, 0, 1 - w), y1 = clamp(p.y - drag.dy, 0, 1 - h);
        return { ...b, x1, y1, x2: x1 + w, y2: y1 + h };
      }));
    } else {
      setBoxes((prev) => prev.map((b) => {
        if (b.id !== drag.id) return b;
        const west = drag.corner.includes("w"), north = drag.corner.includes("n");
        const ax = west ? b.x2 : b.x1, ay = north ? b.y2 : b.y1; // эсрэг булан тогтмол
        return { ...b, x1: Math.min(ax, p.x), x2: Math.max(ax, p.x), y1: Math.min(ay, p.y), y2: Math.max(ay, p.y) };
      }));
    }
  }

  function onPointerUp() {
    const drag = dragRef.current;
    dragRef.current = null;
    if (drag?.kind === "draw") {
      setBoxes((prev) => {
        const b = prev.find((x) => x.id === drag.id);
        if (b && (b.x2 - b.x1 < MIN_SIZE || b.y2 - b.y1 < MIN_SIZE)) { setActiveId(null); return prev.filter((x) => x.id !== drag.id); }
        return prev;
      });
    }
  }

  function setClass(cls: TrainClass) {
    setDrawClass(cls);
    if (activeId !== null) patch(activeId, { class_name: cls });
  }

  function removeActive() {
    if (activeId === null) return;
    setBoxes((prev) => prev.filter((b) => b.id !== activeId));
    setActiveId(null);
  }

  const move = (delta: number) => {
    const i = items.findIndex((x) => x.name === selected);
    const next = items[i + delta];
    if (next) setSelected(next.name);
    else if (delta > 0 && items.length < total) loadList(filter, items.length, true).then((l) => l[0] && setSelected(l[0].name));
    else toast.info(delta > 0 ? "Сүүлийн зураг боллоо" : "Эхний зураг боллоо");
  };

  async function save(list: Box[], advance = true) {
    if (!selected || busy) return;
    setBusy(true);
    try {
      await api.saveTrainingLabels(selected, list.map(({ class_name, x1, y1, x2, y2 }) => ({ class_name, x1, y1, x2, y2 })));
      setItems((prev) => prev.map((x) => (x.name === selected ? { ...x, labeled: true } : x)));
      setSource("manual");
      onChanged();
      if (advance) move(1);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Хадгалж чадсангүй");
    } finally {
      setBusy(false);
    }
  }

  async function removeImage() {
    if (!selected) return;
    try {
      await api.deleteTrainingImage(selected);
      const i = items.findIndex((x) => x.name === selected);
      const rest = items.filter((x) => x.name !== selected);
      setItems(rest);
      setTotal((t) => t - 1);
      setSelected(rest[Math.min(i, rest.length - 1)]?.name ?? null);
      onChanged();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Устгаж чадсангүй");
    }
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA" || e.metaKey || e.ctrlKey) return;
      if (e.key === "Delete" || e.key === "Backspace") { e.preventDefault(); removeActive(); }
      else if (e.key >= "1" && e.key <= "4") setClass(CLASS_ORDER[Number(e.key) - 1]);
      else if (e.key === "s" || e.key === "S" || e.key === "Enter") { e.preventDefault(); save(boxes); }
      else if (e.key === "ArrowRight") move(1);
      else if (e.key === "ArrowLeft") move(-1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  return (
    <div className="grid gap-4 lg:grid-cols-[220px_minmax(0,1fr)]">
      <div className="min-w-0 space-y-3">
        <NativeSelect value={filter} onChange={(e) => { setSelected(null); setFilter(e.target.value as typeof filter); }} aria-label="Шүүлтүүр">
          <option value="unlabeled">Шошгогүй</option>
          <option value="labeled">Шошглосон</option>
          <option value="all">Бүгд</option>
        </NativeSelect>
        <div className="text-xs text-muted-foreground">{total} зураг</div>
        <div className="grid max-h-[60vh] grid-cols-3 content-start gap-1.5 overflow-y-auto pr-1 lg:grid-cols-2">
          {items.map((it) => (
            <button key={it.name} type="button" onClick={() => setSelected(it.name)} title={it.name}
              className={`relative aspect-video overflow-hidden rounded-md border-2 ${selected === it.name ? "border-primary" : "border-transparent"}`}>
              <img src={api.trainingImageUrl(it.name)} alt="" loading="lazy" className="size-full object-cover" />
              {it.labeled && <span className="absolute right-1 top-1 rounded bg-emerald-500 px-1 text-[10px] font-bold text-white">✓</span>}
            </button>
          ))}
        </div>
        {items.length < total && (
          <Button variant="outline" size="sm" className="w-full" onClick={() => loadList(filter, items.length, true)}>Цааш үзэх</Button>
        )}
      </div>

      <div className="min-w-0 space-y-3">
        {!selected ? (
          <div className="grid h-64 place-items-center rounded-xl border border-dashed text-sm text-muted-foreground">
            Зураг алга. «Цуглуулалт» хэсгээс өгөгдөл цуглуулалтыг асаана уу.
          </div>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-2">
              {CLASS_ORDER.map((c, i) => (
                <button key={c} type="button" onClick={() => setClass(c)} title={CLASS_INFO[c].hint}
                  className={`flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs transition ${drawClass === c ? "border-primary bg-primary/10 font-semibold" : "hover:bg-muted"}`}>
                  <span className="size-3 rounded-sm" style={{ background: CLASS_INFO[c].color }} />
                  {CLASS_INFO[c].label}
                  <kbd className="rounded bg-muted px-1 text-[10px] text-muted-foreground">{i + 1}</kbd>
                </button>
              ))}
            </div>

            <div
              ref={surfaceRef}
              className="relative w-full cursor-crosshair touch-none select-none overflow-hidden rounded-xl border bg-black"
              style={{ aspectRatio: aspect }}
              onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerCancel={onPointerUp}
            >
              <img src={api.trainingImageUrl(selected)} alt="" draggable={false} className="pointer-events-none size-full object-fill"
                onLoad={(e) => setAspect(e.currentTarget.naturalWidth / e.currentTarget.naturalHeight)} />
              {boxes.map((b) => {
                const info = CLASS_INFO[b.class_name];
                const active = b.id === activeId;
                return (
                  <div key={b.id} data-box-id={b.id} className="absolute cursor-move"
                    style={{ left: `${b.x1 * 100}%`, top: `${b.y1 * 100}%`, width: `${(b.x2 - b.x1) * 100}%`, height: `${(b.y2 - b.y1) * 100}%`,
                      border: `${active ? 2.5 : 1.5}px solid ${info.color}`, background: active ? `${info.color}26` : "transparent" }}>
                    <span className="pointer-events-none absolute -top-5 left-0 whitespace-nowrap rounded px-1 text-[11px] font-semibold text-white" style={{ background: info.color }}>
                      {info.label}
                    </span>
                    {active && CORNERS.map(({ corner, cls }) => (
                      <span key={corner} data-corner={corner} className={`absolute size-3 rounded-sm border border-white ${cls}`} style={{ background: info.color }} />
                    ))}
                  </div>
                );
              })}
            </div>

            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="text-xs text-muted-foreground">
                {source === "auto" && <span className="mr-2 rounded-md border border-warning/30 bg-warning/10 px-2 py-0.5 text-xs font-medium text-warning">AI санал — шалгаж засаад хадгална уу</span>}
                {source === "manual" && <span className="mr-2 rounded bg-emerald-500/15 px-2 py-0.5 font-medium text-emerald-300">Баталсан</span>}
                {boxes.length} хайрцаг · зураг дээр чирж хайрцаг зурна, хайрцгийг чирж зөөнө, булангаас нь размер өөрчилнө
              </div>
              <div className="flex flex-wrap gap-2">
                <Button variant="ghost" size="sm" onClick={removeActive} disabled={activeId === null}>Хайрцаг устгах</Button>
                <Button variant="ghost" size="sm" onClick={removeImage}>Зураг устгах</Button>
                <Button variant="outline" size="sm" disabled={busy} onClick={() => { setBoxes([]); save([]); }}>Юу ч байхгүй</Button>
                <Button size="sm" disabled={busy} onClick={() => save(boxes)}>Хадгалаад дараагийн <kbd className="ml-1 text-[10px] opacity-70">S</kbd></Button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
