export type Role = "ADMIN" | "HUB_EMPLOYEE";
export type ZoneName = "FACTORY" | "OFFICE";
export type CameraType = "DAHUA" | "HIKVISION" | "GENERIC_RTSP" | "LOCAL_WEBCAM" | "BROWSER";
export type CameraStatus = "OFFLINE" | "CONNECTING" | "ONLINE" | "STREAMING" | "ERROR" | "RECONNECTING";
export type ViolationType = "NO_HELMET" | "NO_WORK_UNIFORM" | "OTHER_SAFETY_VIOLATION";
export type ViolationStatus = "OPEN" | "ACKNOWLEDGED" | "RESOLVED";

export interface User {
  id: string;
  email: string;
  full_name: string | null;
  role: Role;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
  is_demo: boolean; // demo нэвтрэлт — зөвхөн өөрийн нэмсэн камерыг удирдана (backend DEMO_USER_ROLE=ADMIN үед role=ADMIN ирж бүгдийг)
}

/** Нууц үг, RTSP URL-ийг backend хэзээ ч буцаадаггүй. */
export interface Camera {
  id: string;
  name: string;
  ip_address: string;
  rtsp_port: number;
  username: string;
  camera_type: CameraType;
  channel: number;
  subtype: number;
  zone_id: string | null;
  zone: string | null;
  status: CameraStatus;
  mirror: boolean;
  rotation?: number; // хараа цагийн зүүнд 0/90/180/270°
  ai_enabled: boolean;
  enabled: boolean;
  last_connected_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CameraInput {
  name: string;
  ip_address: string;
  rtsp_port: number;
  username?: string;
  password?: string;
  camera_type: CameraType;
  channel: number;
  subtype: number;
  zone_id: string | null;
  mirror?: boolean;
  rotation?: number;
  ai_enabled?: boolean;
}

export interface ConnectionTestResult {
  success: boolean;
  status: string;
  message: string;
  reason: string | null;
  resolution: string | null;
}

export interface Violation {
  id: string;
  camera_id: string;
  camera_name: string;
  zone_id: string | null;
  zone: ZoneName | null;
  violation_type: ViolationType;
  person_id: string | null;
  confidence: number | null;
  snapshot_url: string | null;
  detected_at: string;
  status: ViolationStatus;
  resolved_at: string | null;
  resolved_by: string | null;
  created_at: string;
}

export interface ViolationPage {
  items: Violation[];
  total: number;
  page: number;
  page_size: number;
}

export interface DashboardStats {
  cameras_total: number;
  cameras_online: number;
  violations_total: number;
  violations_open: number;
  violations_today: number;
  by_type: Record<string, number>;
  by_zone: Record<string, number>;
  ai_status: "ONLINE" | "OFFLINE";
}

/** WebSocket: VIOLATION_CREATED data (spec §23) */
export interface ViolationCreatedData {
  id: string;
  camera_id: string;
  camera_name: string;
  zone: ZoneName | null;
  violation_type: ViolationType;
  person_id: string | null;
  confidence: number | null;
  snapshot_url: string | null;
  detected_at: string;
  status: ViolationStatus;
}

export type RealtimeEvent =
  | { type: "CONNECTED"; data: { role: Role } }
  | { type: "VIOLATION_CREATED"; data: ViolationCreatedData }
  | { type: "VIOLATION_UPDATED"; data: Violation }
  | { type: "VIOLATION_DELETED"; data: { id: string } }
  | { type: "CAMERA_UPDATED"; data: Camera }
  | { type: "CAMERA_DELETED"; data: { id: string } }
  | { type: "DETECTIONS"; data: DetectionsData }
  | { type: "RESTRICTED_AREA_UPDATED"; data: { camera_id: string; areas: AreaPoint[][] } };

/** Хориотой бүсийн цэг: AI-ийн зураг дээр (эргүүлсний дараа, толин тусгалаас өмнө) 0..1 */
export type AreaPoint = [number, number];

export type PPEState = "YES" | "NO" | "UNKNOWN";

/** AI-ийн илрүүлэлт: box нь видеоны хэмжээнд normalize хийгдсэн (0..1) */
export interface DetectionsData {
  camera_id: string;
  people: {
    id: number | null;
    box: [number, number, number, number];
    helmet_box?: [number, number, number, number] | null; // танигдсан каск эсвэл каскгүй толгой
    helmet: PPEState;
    uniform: PPEState;
    violation: boolean;
    helmet_required?: boolean; // оффис зэрэг бүсэд каск заавал биш (байхгүй бол заавал гэж үзнэ)
    restricted?: boolean; // хөл нь хориотой бүс дотор
  }[];
}

export interface Zone {
  id: string;
  name: ZoneName;
  type: ZoneName;
  description: string | null;
}

// ---------- Сургалт ----------
export type TrainClass = "person" | "helmet" | "no_helmet" | "work_uniform" | "no_work_uniform";

export interface LabelBox {
  class_name: TrainClass;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

export interface TrainingStatus {
  collection: { enabled: boolean; interval_seconds: number; max_images: number };
  image_count: number;
  labeled_count: number;
  size_bytes: number;
  models_available: Record<"n" | "s", boolean>;
  min_labeled: number;
  epochs_min: number;
  epochs_max: number;
  interval_min: number;
  interval_max: number;
  classes: TrainClass[];
}

export interface TrainingImage {
  name: string;
  labeled: boolean;
}

export interface TrainState {
  state: "idle" | "running" | "done" | "failed" | "stopped";
  started_at: string | null;
  finished_at: string | null;
  epochs: number | null;
  base: "n" | "s" | null;
  message: string | null;
  epoch: number | null;
  model_file: string | null;
  log_tail: string;
  metrics: {
    map50: number;
    map50_95: number;
    per_class: Record<string, { precision: number; recall: number; map50: number }>;
    images: { train: number; val: number; test: number };
  } | null;
}
