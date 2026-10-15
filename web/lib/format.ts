import type { CameraStatus, CameraType, Role, ViolationStatus, ViolationType, ZoneName } from "@/types";

export const VIOLATION_LABEL: Record<ViolationType, string> = {
  NO_HELMET: "Каскгүй",
  NO_WORK_UNIFORM: "Ажлын хувцасгүй",
  OTHER_SAFETY_VIOLATION: "Хориотой бүсэд орсон", // AI зөвхөн хориотой бүсийн зөрчлийг энэ төрлөөр хадгална
};

export const STATUS_LABEL: Record<ViolationStatus, string> = {
  OPEN: "Нээлттэй",
  ACKNOWLEDGED: "Хүлээн авсан",
  RESOLVED: "Шийдвэрлэсэн",
};

export const CAMERA_STATUS_LABEL: Record<CameraStatus, string> = {
  OFFLINE: "Салсан",
  CONNECTING: "Холбогдож байна",
  ONLINE: "Холбогдсон",
  STREAMING: "Дамжуулж байна",
  ERROR: "Алдаа",
  RECONNECTING: "Дахин холбогдож байна",
};

export const CAMERA_TYPE_LABEL: Record<CameraType, string> = {
  DAHUA: "Dahua",
  HIKVISION: "Hikvision",
  GENERIC_RTSP: "RTSP",
  LOCAL_WEBCAM: "Вэбкамер",
  BROWSER: "Browser камер",
};

/** Хүснэгтэд харуулах хаяг: вэбкамерт төхөөрөмжийн дугаар, бусдад IP. */
export function cameraAddress(c: { camera_type: CameraType; ip_address: string }): string {
  if (c.camera_type === "BROWSER") return "Browser";
  return c.camera_type === "LOCAL_WEBCAM" ? `Төхөөрөмж #${c.ip_address}` : c.ip_address;
}

const ZONE_LABEL: Record<ZoneName, string> = { FACTORY: "Үйлдвэр", OFFICE: "Оффис" };

export const ROLE_LABEL: Record<Role, string> = {
  ADMIN: "Админ",
  HUB_EMPLOYEE: "Хяналтын ажилтан",
};

export function zoneLabel(zone: string | null | undefined): string {
  return zone ? (ZONE_LABEL[zone as ZoneName] ?? zone) : "—";
}

const pad = (n: number) => String(n).padStart(2, "0");

/** Орон нутгийн цагаар: YYYY-MM-DD HH:mm:ss */
export function formatTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

export function formatConfidence(value: number | null | undefined): string {
  return value == null ? "—" : `${Math.round(value * 100)}%`;
}

export function cameraTone(status: CameraStatus): "good" | "warn" | "bad" | "idle" {
  if (status === "STREAMING" || status === "ONLINE") return "good";
  if (status === "CONNECTING" || status === "RECONNECTING") return "warn";
  if (status === "ERROR") return "bad";
  return "idle";
}

export const TONE_CLASS = {
  good: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  warn: "bg-amber-500/15 text-amber-400 border-amber-500/30",
  bad: "bg-red-500/15 text-red-400 border-red-500/30",
  idle: "bg-zinc-500/15 text-zinc-400 border-zinc-500/30",
} as const;

export const VIOLATION_STATUS_CLASS: Record<ViolationStatus, string> = {
  OPEN: TONE_CLASS.bad,
  ACKNOWLEDGED: TONE_CLASS.warn,
  RESOLVED: TONE_CLASS.good,
};
