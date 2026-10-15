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
| `docker-compose.yml` (root, төлөвлөгдсөн) | backend, ai-service, web, MediaMTX-ийг нэг дор асаана |

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
