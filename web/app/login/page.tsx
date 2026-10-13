"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Camera, ShieldAlert } from "lucide-react";

import { useAuth } from "@/components/providers/auth-provider";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

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
    <div className="login-bg relative isolate grid min-h-screen place-items-center overflow-hidden p-4">
      <div aria-hidden className="login-grid pointer-events-none absolute inset-0 -z-10" />
      <div aria-hidden className="login-scan pointer-events-none absolute inset-x-0 top-0 -z-10" />
      {/* камерын харагдац шиг булангийн тэмдэг */}
      {["left-6 top-6 border-l-2 border-t-2", "right-6 top-6 border-r-2 border-t-2", "bottom-6 left-6 border-b-2 border-l-2", "bottom-6 right-6 border-b-2 border-r-2"].map((c) => (
        <span key={c} aria-hidden className={`pointer-events-none absolute size-10 border-primary/60 ${c}`} />
      ))}
      <div aria-hidden className="pointer-events-none absolute left-8 top-8 hidden items-center gap-2 pl-14 text-[11px] font-semibold tracking-[0.25em] text-red-400/80 sm:flex">
        <span className="size-2 animate-pulse rounded-full bg-red-500" /> REC
      </div>
      <Camera aria-hidden className="pointer-events-none absolute -bottom-16 -right-12 -z-10 size-96 text-white/[0.03]" />
      <Card className="w-full max-w-sm border-white/10 bg-card/80 shadow-2xl shadow-black/50 backdrop-blur">
        <CardHeader className="items-center text-center">
          <ShieldAlert className="mb-2 size-8 text-emerald-400" />
          <CardTitle className="tracking-[0.12em]">ҮЙЛДВЭРИЙН AI ХЯНАЛТ</CardTitle>
          <p className="text-xs text-muted-foreground">Удирдлагын төвд нэвтрэх</p>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="email">Имэйл</Label>
              <Input id="email" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Нууц үг</Label>
              <Input id="password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
            </div>
            {error && <p role="alert" className="text-sm text-red-400">{error}</p>}
            <Button type="submit" className="w-full" disabled={busy}>
              {busy ? "Нэвтэрч байна…" : "Нэвтрэх"}
            </Button>
            {demoEnabled && (
              <Button type="button" variant="outline" className="w-full" disabled={busy} onClick={() => void run(loginDemo)}>
                Demo-гоор үзэх
              </Button>
            )}
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
