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
| 8001 | backend (FastAPI) | `web/.env.local` `BACKEND_URL` |
| 3000 | web (Next.js) | `backend/.env` `CORS_ORIGINS` |

## MediaMTX нэвтрэлт

MediaMTX нь publish/read хүсэлт бүрт backend-ийн `POST /internal/mediamtx/auth` руу асууна
([`backend/app/api/mediamtx.py`](../backend/app/api/mediamtx.py)):

- **ai-service**: user `ai`, password = `INTERNAL_API_KEY` (publish, read, api)
- **dashboard**: богино хугацаатай Bearer токен, зөвхөн тухайн `cam_<camera_id>` path-д (read)
- **browser камер**: publish токен, зөвхөн тухайн path-д (publish)

Path нэр нь `cam_<camera_id>` байх ба backend, ai-service хоёрт **ижил** байх ёстой.
