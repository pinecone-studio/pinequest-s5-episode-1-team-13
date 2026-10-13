"use client";

import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { useAuth } from "@/components/providers/auth-provider";
import { CollectionPanel } from "@/components/training/collection-panel";
import { Labeler } from "@/components/training/labeler";
import { TrainPanel } from "@/components/training/train-panel";
import { api } from "@/lib/api";
import type { TrainingStatus } from "@/types";

const TABS = [
  { id: "collect", label: "1. Цуглуулалт" },
  { id: "label", label: "2. Шошглох" },
  { id: "train", label: "3. Сургах" },
] as const;

export default function TrainingPage() {
  const { can } = useAuth();
  const [tab, setTab] = useState<(typeof TABS)[number]["id"]>("collect");
  const [status, setStatus] = useState<TrainingStatus | null>(null);

  const reload = useCallback(() => {
    api.trainingStatus().then(setStatus).catch((err) => toast.error(err instanceof Error ? err.message : "Ачаалж чадсангүй"));
  }, []);
  useEffect(() => { if (can("ADMIN")) reload(); }, [can, reload]);

  if (!can("ADMIN")) {
    return <p className="p-6 text-sm text-muted-foreground">Энэ хэсэг зөвхөн админд зориулагдсан.</p>;
  }

  return (
    <div className="space-y-5 p-4 md:p-6">
      <div>
        <h2 className="text-lg font-semibold">Моделийн сургалт</h2>
        <p className="text-sm text-muted-foreground">
          Камерын бодит зургаар каск, ажлын хувцсыг таних моделийг сайжруулна: зураг цуглуулах → шошглох → сургах.
        </p>
      </div>

      <div className="flex gap-1 border-b">
        {TABS.map((t) => (
          <button key={t.id} type="button" onClick={() => setTab(t.id)}
            className={`-mb-px border-b-2 px-4 py-2 text-sm transition ${tab === t.id ? "border-primary font-medium text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}>
            {t.label}
            {t.id === "label" && status ? <span className="ml-2 text-xs text-muted-foreground">{status.labeled_count}/{status.image_count}</span> : null}
          </button>
        ))}
      </div>

      {!status ? (
        <p className="text-sm text-muted-foreground">Ачаалж байна…</p>
      ) : tab === "collect" ? (
        <CollectionPanel status={status} onChanged={reload} />
      ) : tab === "label" ? (
        <Labeler onChanged={reload} />
      ) : (
        <TrainPanel status={status} />
      )}
    </div>
  );
}
