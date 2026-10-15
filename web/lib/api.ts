import type {
  Camera, CameraInput, ConnectionTestResult, DashboardStats, LabelBox, Role, TrainingImage, TrainingStatus, TrainState, User, Violation, ViolationPage,
  ViolationStatus, ViolationType, Zone, ZoneName,
} from "@/types";

// Хоосон = өөрийн домэйн (/api/* -> next.config.ts rewrites -> BACKEND_URL). Шууд backend руу бол NEXT_PUBLIC_API_URL.
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

const KNOWN_ERRORS: Record<string, string> = {
  "Invalid email or password": "Имэйл эсвэл нууц үг буруу байна",
  "Not authenticated": "Нэвтрээгүй байна",
  "Insufficient permissions": "Таны эрх энэ үйлдэлд хүрэлцэхгүй байна",
  "Camera not found": "Камер олдсонгүй",
  "Violation not found": "Зөрчил олдсонгүй",
  "User not found": "Хэрэглэгч олдсонгүй",
  "No recent frame": "Саяхны зураг алга",
  "Origin not allowed": "Хүсэлтийн эх сурвалж зөвшөөрөгдөөгүй",
  "Unknown zone_id": "Тодорхойгүй бүс",
};

function describe(detail: unknown): string {
  if (typeof detail === "string") return KNOWN_ERRORS[detail] ?? detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => `${(d?.loc ?? []).slice(1).join(".") || "талбар"}: ${d?.msg ?? "буруу утга"}`)
      .join("; ");
  }
  return "Хүсэлт амжилтгүй боллоо";
}

async function request<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, headers, ...rest } = init;
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      credentials: "include", // httpOnly cookie
      ...rest,
      headers: { ...(json !== undefined ? { "Content-Type": "application/json" } : {}), ...headers },
      body: json !== undefined ? JSON.stringify(json) : rest.body,
    });
  } catch {
    // Сервер унтарсан / хаяг буруу / сүлжээ тасарсан үед browser зөвхөн "Failed to fetch" гэдэг
    throw new ApiError(0, "Серверт холбогдож чадсангүй. `worker` (backend) ажиллаж байгаа эсэхийг шалгана уу.");
  }
  if (response.status === 401 && !path.startsWith("/api/auth/login")) {
    window.dispatchEvent(new Event("auth:unauthorized"));
  }
  if (!response.ok) {
    let detail: unknown = response.statusText;
    try {
      detail = (await response.json()).detail;
    } catch { }
    throw new ApiError(response.status, describe(detail));
  }
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}

export const api = {
  login: (email: string, password: string) => request<User>("/api/auth/login", { method: "POST", json: { email, password } }),
  demoStatus: () => request<{ enabled: boolean }>("/api/auth/demo"),
  demoLogin: () => request<User>("/api/auth/demo", { method: "POST" }),
  logout: () => request<void>("/api/auth/logout", { method: "POST" }),
  me: () => request<User>("/api/auth/me"),
  wsToken: () => request<{ token: string; expires_in: number }>("/api/auth/ws-token"),

  stats: () => request<DashboardStats>("/api/dashboard/stats"),

  zones: () => request<Zone[]>("/api/zones"),

  cameras: () => request<Camera[]>("/api/cameras"),
  createCamera: (input: CameraInput) => request<Camera>("/api/cameras", { method: "POST", json: input }),
  updateCamera: (id: string, input: Partial<CameraInput>) => request<Camera>(`/api/cameras/${id}`, { method: "PUT", json: input }),
  deleteCamera: (id: string, force = false) => request<void>(`/api/cameras/${id}${force ? "?force=true" : ""}`, { method: "DELETE" }),
  testCamera: (id: string) => request<ConnectionTestResult>(`/api/cameras/${id}/test-connection`, { method: "POST" }),
  testCameraInput: (input: CameraInput) => request<ConnectionTestResult>("/api/cameras/test-connection", { method: "POST", json: input }),
  connectCamera: (id: string) => request<Camera>(`/api/cameras/${id}/connect`, { method: "POST" }),
  disconnectCamera: (id: string) => request<Camera>(`/api/cameras/${id}/disconnect`, { method: "POST" }),
  /** Шууд видеоны WebRTC (WHEP) хаяг + богино хугацаатай токен */
  webrtc: (id: string) =>
    request<{ whep_url: string; token: string; expires_in: number; ice_servers?: RTCIceServer[] }>(`/api/cameras/${id}/webrtc`),
  /** BROWSER камер: энэ browser-ийн камерыг дамжуулах WHIP хаяг + publish токен */
  publish: (id: string) =>
    request<{ whip_url: string; token: string; expires_in: number; ice_servers?: RTCIceServer[] }>(`/api/cameras/${id}/publish`),

  violations: (params: { status?: ViolationStatus; zone?: ZoneName; violation_type?: ViolationType; page?: number; page_size?: number }) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => v !== undefined && query.set(k, String(v)));
    return request<ViolationPage>(`/api/violations?${query}`);
  },
  acknowledge: (id: string) => request<Violation>(`/api/violations/${id}/acknowledge`, { method: "PATCH" }),
  resolve: (id: string) => request<Violation>(`/api/violations/${id}/resolve`, { method: "PATCH" }),
  deleteViolation: (id: string) => request<void>(`/api/violations/${id}`, { method: "DELETE" }),

  // Сургалт (зөвхөн ADMIN)
  trainingStatus: () => request<TrainingStatus>("/api/training/status"),
  setCollection: (enabled: boolean, interval_seconds: number) =>
    request<TrainingStatus["collection"]>("/api/training/collection", { method: "PUT", json: { enabled, interval_seconds } }),
  trainingImages: (filter: "all" | "unlabeled" | "labeled", offset: number, limit: number) =>
    request<{ total: number; items: TrainingImage[] }>(`/api/training/images?filter=${filter}&offset=${offset}&limit=${limit}`),
  trainingImageUrl: (name: string) => `${API_URL}/api/training/images/${encodeURIComponent(name)}`,
  trainingLabels: (name: string) =>
    request<{ boxes: LabelBox[]; source: "manual" | "auto" | "none" }>(`/api/training/images/${encodeURIComponent(name)}/labels`),
  saveTrainingLabels: (name: string, boxes: LabelBox[]) =>
    request<{ saved: number }>(`/api/training/images/${encodeURIComponent(name)}/labels`, { method: "PUT", json: { boxes } }),
  deleteTrainingImage: (name: string) => request<void>(`/api/training/images/${encodeURIComponent(name)}`, { method: "DELETE" }),
  deleteAllTrainingImages: () => request<{ deleted: number }>("/api/training/images", { method: "DELETE" }),
  trainState: () => request<TrainState>("/api/training/train"),
  startTraining: (epochs: number, base: "n" | "s") => request<TrainState>("/api/training/train", { method: "POST", json: { epochs, base } }),
  stopTraining: () => request<{ stopped: boolean }>("/api/training/train/stop", { method: "POST" }),

  users: () => request<User[]>("/api/users"),
  createUser: (input: { email: string; full_name?: string; password: string; role: Role }) =>
    request<User>("/api/users", { method: "POST", json: input }),
  updateUser: (id: string, input: { role?: Role; is_active?: boolean; password?: string }) =>
    request<User>(`/api/users/${id}`, { method: "PATCH", json: input }),
};
