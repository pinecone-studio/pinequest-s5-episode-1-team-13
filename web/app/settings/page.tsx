"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";

import { NativeSelect } from "@/components/native-select";
import { useAuth } from "@/components/providers/auth-provider";
import { useRealtimeStatus } from "@/components/providers/realtime-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { API_URL, api } from "@/lib/api";
import { formatTime, ROLE_LABEL } from "@/lib/format";
import type { Role, User } from "@/types";

const ROLES: Role[] = ["ADMIN", "HUB_EMPLOYEE"];

function Users() {
  const { user: me } = useAuth();
  const [users, setUsers] = useState<User[]>([]);
  const [form, setForm] = useState({ email: "", full_name: "", password: "", role: "HUB_EMPLOYEE" as Role });
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.users().then(setUsers).catch((err) => toast.error(err instanceof Error ? err.message : "Хэрэглэгчдийг ачаалж чадсангүй"));
  }, []);

  async function create(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const created = await api.createUser({ ...form, full_name: form.full_name || undefined });
      setUsers((prev) => [...prev, created]);
      setForm({ email: "", full_name: "", password: "", role: "HUB_EMPLOYEE" });
      toast.success("Хэрэглэгч үүслээ");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Амжилтгүй боллоо");
    } finally {
      setBusy(false);
    }
  }

  async function update(user: User, patch: { role?: Role; is_active?: boolean }) {
    try {
      const updated = await api.updateUser(user.id, patch);
      setUsers((prev) => prev.map((u) => (u.id === updated.id ? updated : u)));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Амжилтгүй боллоо");
    }
  }

  return (
    <Card>
      <CardHeader><CardTitle className="text-xs font-semibold tracking-[0.2em] text-muted-foreground">ХЭРЭГЛЭГЧ БА ЭРХ</CardTitle></CardHeader>
      <CardContent className="space-y-6">
        <div className="overflow-x-auto rounded-xl border">
          <Table>
            <TableHeader><TableRow><TableHead>Имэйл</TableHead><TableHead>Нэр</TableHead><TableHead>Эрх</TableHead><TableHead>Сүүлд нэвтэрсэн</TableHead><TableHead>Идэвх</TableHead></TableRow></TableHeader>
            <TableBody>
              {users.map((u) => (
                <TableRow key={u.id}>
                  <TableCell>{u.email}</TableCell>
                  <TableCell>{u.full_name ?? "—"}</TableCell>
                  <TableCell>
                    <NativeSelect className="w-40" aria-label={`${u.email}-ийн эрх`} value={u.role} disabled={u.id === me?.id} onChange={(e) => update(u, { role: e.target.value as Role })}>
                      {ROLES.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
                    </NativeSelect>
                  </TableCell>
                  <TableCell className="text-muted-foreground">{formatTime(u.last_login_at)}</TableCell>
                  <TableCell>
                    <Button size="sm" variant={u.is_active ? "outline" : "destructive"} disabled={u.id === me?.id} onClick={() => update(u, { is_active: !u.is_active })}>
                      {u.is_active ? "Идэвхтэй" : "Идэвхгүй"}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>

        <form onSubmit={create} className="grid gap-4 sm:grid-cols-5">
          <div className="space-y-2 sm:col-span-2"><Label htmlFor="u-email">Имэйл</Label>
            <Input id="u-email" type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></div>
          <div className="space-y-2"><Label htmlFor="u-name">Нэр</Label>
            <Input id="u-name" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} /></div>
          <div className="space-y-2"><Label htmlFor="u-pass">Нууц үг (≥ 10 тэмдэгт)</Label>
            <Input id="u-pass" type="password" minLength={10} required autoComplete="new-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></div>
          <div className="space-y-2"><Label htmlFor="u-role">Эрх</Label>
            <NativeSelect id="u-role" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>
              {ROLES.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
            </NativeSelect></div>
          <div className="sm:col-span-5"><Button type="submit" disabled={busy}>{busy ? "Үүсгэж байна…" : "Хэрэглэгч үүсгэх"}</Button></div>
        </form>
      </CardContent>
    </Card>
  );
}

export default function SettingsPage() {
  const { user, can } = useAuth();
  const connected = useRealtimeStatus();
  if (!user) return null;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader><CardTitle className="text-xs font-semibold tracking-[0.2em] text-muted-foreground">БҮРТГЭЛ БА СИСТЕМ</CardTitle></CardHeader>
        <CardContent className="grid gap-4 text-sm sm:grid-cols-2">
          <div><div className="text-[11px] uppercase tracking-wider text-muted-foreground">Нэвтэрсэн хэрэглэгч</div>{user.full_name || user.email}<div className="text-xs text-muted-foreground">{user.email}</div></div>
          <div><div className="text-[11px] uppercase tracking-wider text-muted-foreground">Эрх</div><Badge variant="outline">{ROLE_LABEL[user.role]}</Badge></div>
          <div><div className="text-[11px] uppercase tracking-wider text-muted-foreground">API</div>{API_URL || "/api (proxy)"}</div>
          <div><div className="text-[11px] uppercase tracking-wider text-muted-foreground">Бодит цагийн холболт</div>{connected ? "Холбогдсон" : "Салсан"}</div>
        </CardContent>
      </Card>
      {can("ADMIN") && <Users />}
    </div>
  );
}
