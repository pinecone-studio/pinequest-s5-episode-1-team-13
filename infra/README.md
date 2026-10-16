# infra — Видео ба Infra (DevOps)

Камерын видеог dashboard хүртэл дамжуулах (MediaMTX) болон бүх сервисийг нэг дор асаах тохиргоо.

Хариуцагч: **Sumer**

```
IP камер / webcam ─► ai-service ─ffmpeg (RTSP)─► MediaMTX ─WebRTC (WHEP)─► web dashboard
browser камер ─WebRTC (WHIP)─► MediaMTX ─RTSP─► ai-service
                                   │
                                   └─ хүсэлт бүрт ─► backend POST /internal/mediamtx/auth
```

## Бүтэц

| Файл | Үүрэг |
|---|---|
| [`infra/mediamtx.yml`](mediamtx.yml) | MediaMTX тохиргоо: портууд, `cam_<camera_id>` path-ууд, backend руу HTTP нэвтрэлт |
| [`infra/edge/factory.yml`](edge/factory.yml) | Үйлдвэрийн компьютер: ai-service + MediaMTX + cloudflared named tunnel (тогтмол домэйн) + edge-announcer |
| [`infra/edge/factory-quick.yml`](edge/factory-quick.yml) | Мөн адил, домэйнгүй: cloudflared quick tunnel (демо) |
| [`infra/edge/factory.base.yml`](edge/factory.base.yml) | Дээрх хоёрын хуваалцсан service-үүд (шууд асаахгүй) |
| [`infra/edge/vps.yml`](edge/vps.yml) | VPS: MediaMTX (RTSPS) + Caddy (HTTPS) + edge-announcer |
| [`infra/edge/ai.yml`](edge/ai.yml) | VPS горимд үйлдвэрийн компьютер: зөвхөн ai-service |
| [`infra/edge/announce.py`](edge/announce.py) | MediaMTX-ийн HTTPS хаягийг backend-д минут тутам мэдэгдэнэ (`PUT /internal/edge`) |

## MediaMTX асаах

Backend-ийг **эхлээд** асаана (8001 порт): MediaMTX publish/read бүрт backend-ээс асуудаг.

```bash
# Mac
brew install mediamtx
mediamtx infra/mediamtx.yml

# Windows: https://github.com/bluenviron/mediamtx/releases -> mediamtx_vX_windows_amd64.zip задлаад
mediamtx.exe infra\mediamtx.yml
```

Бусад сервисийн `.env` утгууд энэ тохиргоотой таарна (өөрчлөх шаардлагагүй):

- `ai-service/.env`: `MEDIAMTX_RTSP_URL=rtsp://localhost:8554`
- `backend/.env`: `MEDIAMTX_PUBLIC_URL=http://localhost:8889`

Backend өөр порт/хост дээр бол `MTX_AUTHHTTPADDRESS=http://<host>:<port>/internal/mediamtx/auth` env-ээр солино.
LAN-ийн өөр компьютерээс үзэх бол `webrtcAdditionalHosts`-д энэ машины IP-г нэмж, `MEDIAMTX_PUBLIC_URL`-ийг тэр IP болгоно.

## Портууд

| Порт | Хэн ашиглана | Хаана тохируулсан |
|---|---|---|
| 8554 | MediaMTX RTSP: ai-service видео publish хийх / browser камерыг унших | `ai-service/.env` `MEDIAMTX_RTSP_URL` |
| 8889 | MediaMTX WebRTC: dashboard видео үзэх (WHEP), browser камер дамжуулах (WHIP) | `backend/.env` `MEDIAMTX_PUBLIC_URL` |
| 8189/udp | MediaMTX WebRTC медиа (ICE) | `infra/mediamtx.yml` `webrtcLocalUDPAddress` |
| 8189/tcp | MediaMTX WebRTC медиа (ICE-TCP, UDP хаалттай сүлжээнд) | `infra/mediamtx.yml` `webrtcLocalTCPAddress` |
| 8001 | backend (FastAPI) | `web/.env.local` `BACKEND_URL` |
| 3000 | web (Next.js) | `backend/.env` `CORS_ORIGINS` |

## MediaMTX нэвтрэлт

MediaMTX нь publish/read хүсэлт бүрт backend-ийн `POST /internal/mediamtx/auth` руу асууна
([`backend/app/api/mediamtx.py`](../backend/app/api/mediamtx.py)):

- **ai-service**: user `ai`, password = `INTERNAL_API_KEY` (publish, read, api)
- **dashboard**: богино хугацаатай Bearer токен, зөвхөн тухайн `cam_<camera_id>` path-д (read)
- **browser камер**: publish токен, зөвхөн тухайн path-д (publish)

Path нэр нь `cam_<camera_id>` байх ба backend, ai-service хоёрт **ижил** байх ёстой.

## Edge-ийг нэг командаар асаах (Docker Compose)

Edge = камертай нэг сүлжээнд ажиллах ai-service + MediaMTX. Backend (Railway) ба web (Vercel) cloud-д байна.
Edge нь MediaMTX-ийн HTTPS хаягаа backend-д минут тутам мэдэгдэнэ (`PUT /internal/edge`). Backend 3 минут мэдэгдэл
аваагүй бол `MEDIAMTX_PUBLIC_URL` руу буцна. Railway-ийн хувьсагчийг гараар солих шаардлагагүй.

| Горим | Хаана | Команд (repo-ийн root-оос) |
|---|---|---|
| Бүгд нэг дор | Үйлдвэрийн компьютер | `docker compose -f infra/edge/factory.yml up -d --build` |
| Бүгд нэг дор, домэйнгүй (демо) | Үйлдвэрийн компьютер | `docker compose -f infra/edge/factory-quick.yml up -d --build` |
| VPS | Public IP-тэй сервер | `docker compose -f infra/edge/vps.yml up -d` |
| VPS горимд AI | Үйлдвэрийн компьютер | `docker compose -f infra/edge/ai.yml up -d --build` |

```
Бүгд нэг дор:  IP камер ─► ai-service ─RTSP─► MediaMTX ◄─ cloudflared named tunnel (https://<MEDIA_DOMAIN>) ◄─ browser
Домэйнгүй:     IP камер ─► ai-service ─RTSP─► MediaMTX ◄─ cloudflared quick tunnel (https://<random>.trycloudflare.com) ◄─ browser
VPS горим:     IP камер ─► ai-service (үйлдвэр) ─RTSPS :8322─► MediaMTX (VPS) ◄─ Caddy (https://<MEDIA_DOMAIN>) ◄─ browser
```

### Бэлтгэл (хоёр горимд)

1. Docker суулгана. Үйлдвэрийн компьютер (Windows/Mac): [Docker Desktop](https://www.docker.com/products/docker-desktop/),
   Settings → General → **Start Docker Desktop when you sign in** (компьютер асахад edge өөрөө асна —
   container бүр `restart: unless-stopped`). Linux/VPS: `curl -fsSL https://get.docker.com | sh`.
2. Repo-г clone хийнэ. `cp infra/edge/.env.example infra/edge/.env` хийгээд бөглөнө (тайлбар файл дотор).
3. AI ажиллах машин дээр (factory/ai): `ai-service/.env` (DB, Supabase, CAMERA_SECRET_KEY) бөглөсөн, модель
   анхдагчаар `ai-service/models/ppe-ours-v2.pt` (git-д байгаа), өөр модель бол `MODEL_PATH=/training/models/<файл>`. `BACKEND_URL`, `INTERNAL_API_KEY`-г `infra/edge/.env`-ээс авна.
4. Backend (Railway): `CAMERA_PROBE_ENABLED=false` (edge-ийн хаягийг дагана).

### Бүгд нэг дор (үйлдвэрийн компьютер)

- `infra/edge/.env`: `BACKEND_URL`, `INTERNAL_API_KEY`, `EDGE_HOSTS=<энэ компьютерийн LAN IP>`, `MODEL_PATH` (заавал биш),
  `MEDIA_DOMAIN`, `CLOUDFLARE_TUNNEL_TOKEN` (доорх "Тогтмол домэйн").
- Firewall (Windows Defender): `8189/udp`, `8189/tcp`-г LAN-д нээнэ. Өөр сүлжээнээс үзэх бол router дээр 8189 udp/tcp-г
  port-forward хийж, `EDGE_HOSTS`-д public IP-г нэмнэ (эсвэл TURN — доорх хэсэг).
- Домэйнгүй үед `factory-quick.yml`: Cloudflare quick tunnel, аккаунтгүй, асах бүрт хаяг солигдоно (edge-announcer шинэ
  хаягийг автоматаар мэдэгдэнэ). `MEDIA_DOMAIN`, `CLOUDFLARE_TUNNEL_TOKEN` хэрэггүй.

### Тогтмол домэйн (Cloudflare named tunnel)

`factory.yml`-ийн MediaMTX нь `https://<MEDIA_DOMAIN>` (жишээ `media.example.com`) гэсэн тогтмол хаягтай. HTTPS сертификатыг
Cloudflare өгнө, router дээр 80/443 нээх шаардлагагүй (cloudflared зөвхөн гадагш холбогдоно). Домэйны DNS Cloudflare дээр байх ёстой.

1. [Cloudflare dashboard](https://dash.cloudflare.com) → **Zero Trust** → **Networks** → **Tunnels** → **Create a tunnel** →
   **Cloudflared**, нэр (жишээ `pinequest-factory`).
2. "Install and run a connector" алхам дээрх командын `--token`-ийн дараах урт утгыг хуулаад `infra/edge/.env`-ийн
   `CLOUDFLARE_TUNNEL_TOKEN`-д тавина (cloudflared-ийг тусад нь суулгахгүй — Docker-т байгаа).
3. **Public Hostname** нэмнэ: Subdomain `media`, Domain `<домэйн>`, Service Type `HTTP`, URL `mediamtx:8889`.
   DNS record-ийг Cloudflare өөрөө үүсгэнэ. `infra/edge/.env`: `MEDIA_DOMAIN=media.<домэйн>`.
4. `docker compose -f infra/edge/factory.yml up -d --build`. Dashboard дээр tunnel **HEALTHY** болно.

edge-announcer нь cloudflared Cloudflare-тэй холбогдсон (`/ready` = 200) үед л хаягийг backend-д мэдэгдэнэ. Tunnel тасарвал
3 минутын дараа backend `MEDIAMTX_PUBLIC_URL` руу буцна.

Token нь tunnel-ийг ажиллуулах эрх — `.env`-д л байна, commit хийхгүй. Алдагдсан бол tunnel-ийн **Refresh token**-оор солино.

### VPS горим

VPS дээр (`vps.yml`):

- DNS: `MEDIA_DOMAIN` (жишээ `media.example.com`)-ий A record → VPS IP. `infra/edge/.env`: `BACKEND_URL`, `INTERNAL_API_KEY`,
  `EDGE_HOSTS=<VPS public IP>`, `MEDIA_DOMAIN`.
- Firewall: `80/tcp`, `443/tcp+udp` (Caddy, Let's Encrypt), `8189/udp+tcp` (WebRTC медиа), `8322/tcp` (RTSPS —
  боломжтой бол зөвхөн үйлдвэрийн public IP-д). `8554` (ил RTSP)-ийг гадагш нээхгүй.
- RTSPS-ийн self-signed сертификатыг анх асахад `rtsps-cert` үүсгэнэ (`rtsps-certs` volume, 10 жил).

Үйлдвэрийн компьютер дээр (`ai.yml`): `infra/edge/.env`-д `BACKEND_URL`, `INTERNAL_API_KEY`, `MODEL_PATH` (заавал биш),
`MEDIAMTX_RTSP_URL=rtsps://<MEDIA_DOMAIN>:8322`. Камерууд руу зөвхөн гарах холболт хэрэгтэй, port-forward шаардлагагүй.

### Шалгах, засвар

```bash
docker compose -f infra/edge/factory.yml ps                     # бүгд running (vps.yml-д rtsps-cert нь exited (0))
docker compose -f infra/edge/factory.yml logs -f edge-announcer # "мэдэгдлээ: https://..." 
docker compose -f infra/edge/factory.yml logs -f mediamtx ai-service
docker compose -f infra/edge/factory.yml pull && docker compose -f infra/edge/factory.yml up -d --build  # шинэчлэх
docker compose -f infra/edge/factory.yml down                   # зогсоох
```

- edge-announcer `HTTP 401` = `INTERNAL_API_KEY` backend-тэй таарахгүй. MediaMTX log-д `authentication failed` = `BACKEND_URL` буруу.
- Named tunnel: edge-announcer "tunnel Cloudflare-тэй холбогдоогүй" гээд хүлээгээд байвал `logs cloudflared`-ийг харна
  (`Provided Tunnel token is not valid` = `CLOUDFLARE_TUNNEL_TOKEN` буруу). `https://<MEDIA_DOMAIN>` дээр Cloudflare-ийн
  алдаа 1033 = tunnel холбогдоогүй, 502 = Public Hostname-ийн Service буруу (`HTTP`, `mediamtx:8889` байх ёстой).
- Dashboard дээр видео гарахгүй бол `chrome://webrtc-internals` (доорх "Шалгах").
- `LOCAL_WEBCAM` (USB камер) Docker Desktop (Windows/Mac) дээр ажиллахгүй — ai-service-ийг Python-оор шууд асаана.
  Linux дээр нэмэлт файл (жишээ `webcam.yml`: `services: {ai-service: {devices: ["/dev/video0:/dev/video0"]}}`) бичээд
  `docker compose -f infra/edge/factory.yml -f webcam.yml up -d` гэж асаана.
- NVIDIA GPU: Dockerfile нь CPU-only PyTorch суулгадаг тул GPU-д ai-service-ийг Python-оор шууд асаах нь энгийн.

## WebRTC NAT traversal (STUN, ICE-TCP, TURN)

SDP (WHEP/WHIP) нь `8889`-ээр (production дээр cloudflared tunnel-ээр) явдаг ч видео өөрөө browser ба MediaMTX-ийн хооронд
**шууд** `8189`-ээр явна. Browser ба MediaMTX хоёр өөр сүлжээнд байвал холболтыг дараах дарааллаар оролдоно:

| Арга | Хэзээ ажиллана | Хаана тохируулсан |
|---|---|---|
| Host (LAN) | Нэг сүлжээнд | `webrtcAdditionalHosts` |
| STUN | Хоёр тал энгийн NAT-ын ард: public IP-гээ олж шууд холбогдоно | Сервер: `webrtcICEServers2`; browser: `WEBRTC_STUN_URLS` |
| ICE-TCP | Browser-ийн сүлжээ UDP хаадаг ч MediaMTX-ийн `8189/tcp` хүрэх боломжтой | `webrtcLocalTCPAddress` |
| TURN | Symmetric NAT, зөвхөн 443 нээлттэй корпорацийн сүлжээ — видеог TURN сервер дамжуулна | Browser: `TURN_URLS` + `TURN_SECRET` (эсвэл `TURN_USERNAME`/`TURN_PASSWORD`) |

Browser-ийн ICE серверүүдийг backend `GET /api/cameras/{id}/webrtc` болон `/publish` хариултын `ice_servers`-ээр өгнө
([`backend/app/services/camera_service.py`](../backend/app/services/camera_service.py) `ice_servers()`).
TURN тохируулаагүй бол зөвхөн STUN-тэй ажиллана. Буруу тохиргоог backend асахдаа log-д анхааруулна.

### TURN (шаардлагатай бол)

`backend/.env`:

```bash
TURN_URLS=turn:turn.example.com:3478?transport=udp,turn:turn.example.com:3478?transport=tcp,turns:turn.example.com:5349
# coturn use-auth-secret (санал болгож буй): нууц нь backend-д үлдэж, browser хугацаатай credential авна
TURN_SECRET=<coturn static-auth-secret>
TURN_CREDENTIAL_TTL_SECONDS=86400
# эсвэл статик credential өгдөг үйлчилгээ (TURN_SECRET хоосон үед)
# TURN_USERNAME=...
# TURN_PASSWORD=...
```

Өөрсдөө coturn ажиллуулах бол (public IP-тэй сервер дээр) `turnserver.conf`-ийн гол мөрүүд:

```
listening-port=3478
tls-listening-port=5349
fingerprint
use-auth-secret
static-auth-secret=<TURN_SECRET-тэй ИЖИЛ>
realm=turn.example.com
external-ip=<серверийн public IP>
```

Firewall: `3478/udp+tcp`, `5349/tcp`, relay-ийн `49152-65535/udp`.
Ихэнх тохиолдолд browser талын TURN хангалттай. MediaMTX ч symmetric NAT-ын ард байвал `mediamtx.yml`-ийн
`webrtcICEServers2`-д тайлбарласан TURN жишээг нээнэ (тэгвэл бүх урсгал TURN-ээр явна).

### Шалгах

- `chrome://webrtc-internals` → тухайн PeerConnection → `candidate-pair` (succeeded): `local/remote candidateType` нь
  `host` (LAN), `srflx` (STUN), `relay` (TURN). ICE-TCP үед `protocol: tcp`.
- TURN сервер ажиллаж байгааг [Trickle ICE](https://webrtc.github.io/samples/src/content/peerconnection/trickle-ice/)
  хуудсанд `TURN_URLS`, credential-ийг оруулж `relay` candidate гарах эсэхээр шалгана.
