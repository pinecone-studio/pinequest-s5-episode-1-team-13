"use client";

import { useState } from "react";
import { toast } from "sonner";

import { NativeSelect } from "@/components/native-select";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import { zoneLabel } from "@/lib/format";
import type { Camera, CameraInput, CameraType, ConnectionTestResult, Zone } from "@/types";

const EMPTY: CameraInput = {
  name: "", ip_address: "", rtsp_port: 554, username: "", password: "",
  camera_type: "DAHUA", channel: 1, subtype: 0, zone_id: null, mirror: false, ai_enabled: true,
};

function initialForm(camera: Camera | null, zones: Zone[]): CameraInput {
  return camera
    ? { name: camera.name, ip_address: camera.ip_address, rtsp_port: camera.rtsp_port, username: camera.username, password: "",
        camera_type: camera.camera_type, channel: camera.channel, subtype: camera.subtype, zone_id: camera.zone_id, mirror: camera.mirror, ai_enabled: camera.ai_enabled }
    : { ...EMPTY, zone_id: zones[0]?.id ?? null };
}

interface Props { camera: Camera | null; zones: Zone[]; onClose: () => void; onSaved: (c: Camera) => void }

/** Dialog нээгдэх бүрт шинээр mount хийгдэх тул form-ын төлөв автоматаар цэвэрлэгдэнэ. */
function CameraFormBody({ camera, zones, onClose, onSaved }: Props) {
  const [form, setForm] = useState<CameraInput>(() => initialForm(camera, zones));
  const [busy, setBusy] = useState(false);
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<ConnectionTestResult | null>(null);
  const editing = !!camera;
  const browser = form.camera_type === "BROWSER";
  const webcam = form.camera_type === "LOCAL_WEBCAM" || browser; // хоёуланд IP/нууц үг хэрэггүй

  const set = <K extends keyof CameraInput>(key: K, value: CameraInput[K]) => setForm((f) => ({ ...f, [key]: value }));
  const num = (key: "rtsp_port" | "channel" | "subtype") => (e: React.ChangeEvent<HTMLInputElement>) => set(key, Number(e.target.value));

  async function test() {
    setTesting(true);
    setResult(null);
    try {
      // Нууц үг шинээр оруулсан бол оруулсан утгаар, үгүй бол хадгалагдсан камераар шалгана
      setResult(webcam || form.password ? await api.testCameraInput(form) : camera ? await api.testCamera(camera.id) : null);
      if (!webcam && !form.password && !camera) toast.error("Нууц үгээ оруулна уу");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Шалгалт амжилтгүй боллоо");
    } finally {
      setTesting(false);
    }
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const payload = { ...form, password: webcam ? undefined : form.password || undefined, username: webcam ? undefined : form.username };
      const saved = camera ? await api.updateCamera(camera.id, payload) : await api.createCamera(payload);
      toast.success(camera ? "Камерын мэдээллийг шинэчиллээ" : "Камер нэмэгдлээ");
      onSaved(saved);
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Хадгалж чадсангүй");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
        <form onSubmit={submit} className="grid grid-cols-2 gap-4">
          <div className="col-span-2 space-y-2">
            <Label htmlFor="cam-name">Камерын нэр</Label>
            <Input id="cam-name" required value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="Factory-Camera-01" />
          </div>
          <div className="space-y-2">
            <Label htmlFor="cam-type">Камерын төрөл</Label>
            <NativeSelect id="cam-type" value={form.camera_type} onChange={(e) => {
              const type = e.target.value as CameraType;
              const local = (t: CameraType) => t === "LOCAL_WEBCAM" || t === "BROWSER";
              setForm((f) => ({ ...f, camera_type: type, ip_address: type === "LOCAL_WEBCAM" ? "0" : type === "BROWSER" ? "browser" : local(f.camera_type) ? "" : f.ip_address }));
              setResult(null);
            }}>
              <option value="DAHUA">Dahua (RTSP)</option><option value="HIKVISION">Hikvision (RTSP)</option><option value="LOCAL_WEBCAM">Вэбкамер (AI service-ийн машин)</option><option value="BROWSER">Browser камер (дурын төхөөрөмж)</option>
            </NativeSelect>
          </div>
          <div className="space-y-2">
            <Label htmlFor="cam-zone">Бүс</Label>
            <NativeSelect id="cam-zone" required value={form.zone_id ?? ""} onChange={(e) => set("zone_id", e.target.value || null)}>
              <option value="" disabled>Бүс сонгох</option>
              {zones.map((z) => <option key={z.id} value={z.id}>{zoneLabel(z.name)}</option>)}
            </NativeSelect>
          </div>
          {browser ? (
            <div className="col-span-2 space-y-2">
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" className="size-4 accent-primary" checked={!!form.mirror} onChange={(e) => set("mirror", e.target.checked)} />
                Толин тусгал (selfie шиг баруун-зүүн эргүүлэх)
              </label>
              <p className="text-xs text-muted-foreground">Хадгалсны дараа dashboard дээр &quot;Энэ төхөөрөмжөөс дамжуулах&quot; дарахад энэ browser-ийн камер (Mac, ноутбук, утас) системд холбогдоно. Хуудсыг хаавал дамжуулалт зогсоно.</p>
            </div>
          ) : webcam ? (
            <div className="col-span-2 space-y-2">
              <Label htmlFor="cam-ip">Төхөөрөмжийн дугаар</Label>
              <Input id="cam-ip" type="number" min={0} max={9} required value={form.ip_address} onChange={(e) => set("ip_address", e.target.value)} />
              <label className="flex items-center gap-2 pt-1 text-sm">
                <input type="checkbox" className="size-4 accent-primary" checked={!!form.mirror} onChange={(e) => set("mirror", e.target.checked)} />
                Толин тусгал (selfie шиг баруун-зүүн эргүүлэх)
              </label>
              <p className="text-xs text-muted-foreground">Ихэвчлэн 0 — суурилуулсан FaceTime камер. Өөр камер (жишээ нь iPhone) бол 1, 2 гэж оролдоно. macOS камерын зөвшөөрөл асууж магадгүй.</p>
            </div>
          ) : (
            <>
              <div className="space-y-2">
                <Label htmlFor="cam-ip">{form.camera_type === "GENERIC_RTSP" ? "IP эсвэл бүтэн RTSP хаяг" : "IP хаяг"}</Label>
                <Input id="cam-ip" required value={form.ip_address} onChange={(e) => set("ip_address", e.target.value)}
                  placeholder={form.camera_type === "GENERIC_RTSP" ? "rtsp://192.168.1.50:8080/h264.sdp" : "192.168.1.100"} />
                {form.camera_type === "GENERIC_RTSP" && (
                  <p className="text-xs text-muted-foreground">Утасны апп гэх мэт өөр замтай камерт бүтэн хаяг бичнэ. Нэр, нууц үгийг хаягт биш доорх талбарт.</p>
                )}
              </div>
              <div className="space-y-2">
                <Label htmlFor="cam-port">RTSP порт</Label>
                <Input id="cam-port" type="number" min={1} max={65535} required value={form.rtsp_port} onChange={num("rtsp_port")} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="cam-user">Хэрэглэгчийн нэр</Label>
                <Input id="cam-user" required autoComplete="off" value={form.username} onChange={(e) => set("username", e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="cam-pass">Нууц үг</Label>
                <Input id="cam-pass" type="password" autoComplete="new-password" required={!editing} value={form.password ?? ""}
                  onChange={(e) => set("password", e.target.value)} placeholder={editing ? "өөрчлөхгүй" : ""} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="cam-channel">Суваг (channel)</Label>
                <Input id="cam-channel" type="number" min={1} required value={form.channel} onChange={num("channel")} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="cam-subtype">Урсгал (0 үндсэн, 1 туслах)</Label>
                <Input id="cam-subtype" type="number" min={0} max={9} required value={form.subtype} onChange={num("subtype")} />
              </div>
            </>
          )}

          <div className="col-span-2 rounded-lg border bg-muted/30 p-3">
            <label className="flex cursor-pointer items-start gap-3 text-sm">
              <input type="checkbox" className="mt-0.5 size-4 accent-primary" checked={form.ai_enabled !== false} onChange={(e) => set("ai_enabled", e.target.checked)} />
              <span>
                <span className="font-medium">AI-тай холбох</span>
                <span className="block text-xs text-muted-foreground">Асаалттай үед хүн, каск, ажлын хувцсыг илрүүлж зөрчил бүртгэнэ. Унтраавал зөвхөн шууд видео харагдана.</span>
              </span>
            </label>
          </div>

          {result && (
            <div role="status" className={`col-span-2 rounded-lg border p-3 text-sm ${result.success ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300" : "border-red-500/30 bg-red-500/10 text-red-300"}`}>
              <div className="font-medium">{result.success ? "Камер амжилттай холбогдлоо" : "RTSP stream-д холбогдож чадсангүй"}{result.resolution ? ` · ${result.resolution}` : ""}</div>
              {result.reason && <div className="mt-1 text-xs opacity-90">{result.reason}</div>}
            </div>
          )}

          <div className="col-span-2 flex justify-between gap-2 pt-2">
            <Button type="button" variant="outline" disabled={testing || !form.ip_address || (!webcam && (!form.username || (!editing && !form.password)))} onClick={test}>
              {testing ? "Шалгаж байна…" : "Холболт шалгах"}
            </Button>
            <div className="flex gap-2">
              <Button type="button" variant="ghost" onClick={onClose}>Болих</Button>
              <Button type="submit" disabled={busy}>{busy ? "Хадгалж байна…" : "Хадгалах"}</Button>
            </div>
          </div>
        </form>
    </>
  );
}

export function CameraFormDialog({ open, ...props }: Props & { open: boolean }) {
  return (
    <Dialog open={open} onOpenChange={(o) => !o && props.onClose()}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{props.camera ? "Камер засах" : "Камер нэмэх"}</DialogTitle>
          <DialogDescription>Нууц үг шифрлэгдэж хадгалагдах бөгөөд дахин харагдахгүй.</DialogDescription>
        </DialogHeader>
        {open && <CameraFormBody key={props.camera?.id ?? "new"} {...props} />}
      </DialogContent>
    </Dialog>
  );
}
