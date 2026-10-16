"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ShieldAlert } from "lucide-react";

import { useAuth } from "@/components/providers/auth-provider";
import { api } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const fieldClass =
  "h-11 w-full rounded-[11px] border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.015)] px-3 text-[14px] text-white shadow-none placeholder:text-[#A1A1AA] focus-visible:border-[rgba(255,255,255,0.3)] focus-visible:ring-0 md:text-[14px]";

export default function LoginPage() {
  const { user, loading, login, loginDemo } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [demoEnabled, setDemoEnabled] = useState(false);

  useEffect(() => {
    if (!loading && user) router.replace("/");
  }, [loading, user, router]);

  useEffect(() => {
    api.demoStatus().then((s) => setDemoEnabled(s.enabled)).catch(() => setDemoEnabled(false));
  }, []);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      router.replace("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Нэвтэрч чадсангүй");
    } finally {
      setBusy(false);
    }
  }

  function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    void run(() => login(email, password));
  }

  return (
    <div
      className="flex min-h-dvh w-full items-center justify-center overflow-y-auto px-5 py-8"
      style={{ background: "linear-gradient(120deg, #1C1C1E, #292929, #1B1B1D)" }}
    >
        <form onSubmit={onSubmit} className="flex w-full max-w-[340px] flex-col items-center">
          <div className="grid size-11 place-items-center rounded-xl bg-white/8 text-white">
            <ShieldAlert className="size-5" />
          </div>
          <h1 className="mt-5 text-[23px] font-medium leading-none text-white">Тавтай морил</h1>
          <p className="mt-2 text-[13px] text-[#A1A1AA]">Удирдлагын төвд нэвтрэх</p>

          <div className="mt-8 flex w-full flex-col gap-3">
            <div>
              <Label htmlFor="email" className="sr-only">Имэйл</Label>
              <Input
                id="email"
                type="email"
                autoComplete="username"
                required
                placeholder="Имэйл"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className={fieldClass}
              />
            </div>
            <div>
              <Label htmlFor="password" className="sr-only">Нууц үг</Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                placeholder="Нууц үг"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className={fieldClass}
              />
            </div>
          </div>

          {error && <p role="alert" className="mt-3 w-full text-center text-[13px] text-white">{error}</p>}

          <button
            type="submit"
            disabled={busy}
            className="mt-3 h-11 w-full rounded-[11px] bg-white text-[13px] font-medium text-[#111111] transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy ? "Нэвтэрч байна…" : "Нэвтрэх"}
          </button>

          {demoEnabled && (
            <button
              type="button"
              disabled={busy}
              onClick={() => void run(loginDemo)}
              className="mt-6 h-11 w-full rounded-[11px] border border-white/10 bg-transparent text-[13px] font-medium text-white transition-colors hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Demo-гоор үзэх
            </button>
          )}
        </form>
    </div>
  );
}
