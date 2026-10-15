# Нууц түлхүүр, мониторинг, alert

## Яаралтай: git түүхэнд задарсан түлхүүрүүдийг солих

Repo **public**. `6edc58d`, `d88caf6`, `ac55346` commit-уудын `backend/.env.example`, `ai-service/.env.example`-д
жинхэнэ утгууд орсон (PR #48-аар placeholder болгосон ч түүхэнд хэвээр, хэн ч уншиж болно):
`DATABASE_URL` (нууц үгтэй), `SUPABASE_SERVICE_ROLE_KEY`, `JWT_SECRET`, `INTERNAL_API_KEY`, `CAMERA_SECRET_KEY`.
Түүхийг дахин бичихгүй — **бүгдийг доорх "Түлхүүр солих" дагуу солино**. Хуучин түлхүүр ажиллахаа больсны дараа
түүхэнд үлдэх нь аюулгүй.

## Нууц утга хаана байх вэ

| Хаана | Юу |
|---|---|
| Railway → backend → Variables | `backend/.env.example`-ийн бүх утга, `ALERT_WEBHOOK_URL` |
| Vercel → Settings → Environment Variables | `BACKEND_URL`, `NEXT_PUBLIC_*` (зөвхөн нийтэд ил байж болох утга) |
| Edge машин: `ai-service/.env`, `infra/edge/.env` | ai-service-ийн DB, Supabase, `CAMERA_SECRET_KEY`, `INTERNAL_API_KEY`, tunnel token |
| Багийн password manager (Bitwarden, 1Password г.м) | **Үнэн эх сурвалж**: бүх production утга |

## Дүрэм

- `.env`, `.env.local`-ийг **хэзээ ч** commit хийхгүй (`.gitignore` хаасан). Repo-д зөвхөн placeholder-тэй
  `.env.example` (`CHANGE_ME`, `YOUR_...`).
- Нууц утгыг **chat-д бичихгүй** (Slack, Discord, Messenger, AI chat — Cursor/ChatGPT г.м), screenshot, issue, PR-ийн
  тайлбар, log-д оруулахгүй. Хуваалцах цорын ганц зам — password manager-ийн shared vault.
- `NEXT_PUBLIC_*` утга browser-т очдог — тэнд нууц утга хэзээ ч тавихгүй.
- Шинэ түлхүүр үүсгэх:
  - `JWT_SECRET`, `INTERNAL_API_KEY`: `python -c "import secrets; print(secrets.token_urlsafe(48))"`
  - `CAMERA_SECRET_KEY`: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- Нууц утга задарсан (commit, chat, screenshot) гэж сэжиглэвэл **тэр даруй солино**, дараа нь багт мэдэгдэнэ.

## Задрахаас сэргийлэх

- **CI**: [`.github/workflows/ci.yml`](.github/workflows/ci.yml)-ийн `secrets` job push бүрийн шинэ commit-уудыг
  [gitleaks](https://github.com/gitleaks/gitleaks)-ээр шалгана ([`.gitleaks.toml`](.gitleaks.toml): үндсэн дүрмүүд +
  нууц үгтэй `postgres://` URL, Discord webhook). Олдвол CI унана → `main`-д merge хийгдэхгүй.
- **Локал (санал болгож буй)**: commit хийхээс өмнө шалгана ([`.pre-commit-config.yaml`](.pre-commit-config.yaml)):
  ```bash
  pip install pre-commit && pre-commit install
  ```
- **GitHub** → Settings → Code security → **Secret Protection** болон **Push protection** асаана (public repo-д үнэгүй):
  GitHub-ийн таньдаг түлхүүртэй push-ийг шууд хаана.
- gitleaks хуурамч илрүүлэлт хийвэл (жишээ нь тестийн өгөгдөл) тухайн мөрөнд `# gitleaks:allow` нэмнэ — жинхэнэ
  түлхүүрт хэзээ ч биш.
- Commit хийсэн нууц утгыг дараагийн commit-оор устгах нь хангалтгүй — түүхэнд үлддэг. **Заавал солино.**

## Түлхүүр солих

Шинэ утгыг эхлээд password manager-т хадгална, дараа нь бүх газарт зэрэг солино. Edge машин дээр
`.env`-ийг сольсны дараа ai-service-ийг дахин асаана (`docker compose -f infra/edge/<mode>.yml up -d`).

| Түлхүүр | Хаана үүсгэх | Хаана солих | Үр дагавар |
|---|---|---|---|
| `DATABASE_URL` (нууц үг) | Supabase → Project Settings → Database → **Reset database password** | Railway, `ai-service/.env` | Хуучин холболт тасарна |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase → Project Settings → API Keys → **Create new secret key** (`sb_secret_...`), дараа нь legacy `service_role`/`anon` түлхүүрүүдийг **Disable** | Railway, `ai-service/.env` | — |
| `JWT_SECRET` | `secrets.token_urlsafe(48)` | Railway | Бүх хэрэглэгч дахин нэвтэрнэ |
| `INTERNAL_API_KEY` | `secrets.token_urlsafe(48)` | Railway, `ai-service/.env`, `infra/edge/.env` | Солих хооронд AI/edge 401 авна |
| `CAMERA_SECRET_KEY` | `Fernet.generate_key()` | Доорх дарааллаар | DB дахь камерын нууц үгийг дахин шифрлэнэ |
| `ALERT_WEBHOOK_URL`, `CLOUDFLARE_TUNNEL_TOKEN`, `TURN_SECRET` | Discord/Slack/Telegram-д webhook-ийг устгаж шинээр, Cloudflare tunnel → Refresh token, coturn `static-auth-secret` | Railway, `infra/edge/.env` | — |

Supabase service key-ийг сольсны дараа шалгана: `/health` → `"database": "connected"`, dashboard дээр зөрчлийн
snapshot зураг харагдаж (Storage) байгаа. Шинэ `sb_secret_` түлхүүр ажиллахгүй бол оронд нь Supabase → JWT Keys →
legacy JWT secret-ийг rotate хийж (anon, service_role хоёулаа шинэчлэгдэнэ) шинэ `service_role`-ийг тавина.

### `CAMERA_SECRET_KEY` солих

Камерын RTSP нууц үгс DB-д энэ түлхүүрээр шифрлэгдсэн тул зүгээр солих боломжгүй —
[`backend/scripts/rotate_camera_key.py`](backend/scripts/rotate_camera_key.py) бүгдийг нэг transaction-аар дахин шифрлэнэ
(аль нэг нь тайлагдахгүй бол юу ч өөрчлөхгүй).

1. Edge дээр ai-service-ийг зогсооно.
2. Production DB-тэй `backend/.env` (одоогийн хуучин `CAMERA_SECRET_KEY`-тэй) машин дээр:
   ```bash
   cd backend
   python -m scripts.rotate_camera_key --dry-run   # шинэ түлхүүрийг нуугдмалаар асууна, зөвхөн шалгана
   python -m scripts.rotate_camera_key             # дахин шифрлэнэ
   ```
   (Эсвэл `NEW_CAMERA_SECRET_KEY` env-ээр өгнө. Түлхүүрийг shell history-д үлдээхгүйн тулд асуулгаар нь оруулах нь дээр.)
3. Railway, `backend/.env`, `ai-service/.env`-ийн `CAMERA_SECRET_KEY`-г шинэ утгаар солиод backend, ai-service-ийг асаана.

## Мониторинг ба alert

```
backend alert_loop (минут тутам) ─► DB, AI heartbeat, камер, edge tunnel ─► ALERT_WEBHOOK_URL (Discord/Slack/Telegram)
UptimeRobot (5 минут тутам)      ─► https://<backend>/health, https://<web>  ─► мөн тэр channel (backend өөрөө унасан үед)
```

### Backend alert ([`backend/app/services/alerts.py`](backend/app/services/alerts.py))

| Шалгалт | Асуудал гэж үзэх |
|---|---|
| Database | `select 1` амжилтгүй (энэ үед бусдыг шалгахгүй) |
| AI service | 30 секундээс дээш heartbeat ирээгүй |
| Камер (идэвхтэй бүр) | Төлөв `OFFLINE` эсвэл `ERROR` |
| Edge tunnel | `CAMERA_PROBE_ENABLED=false` үед edge 180 секундээс дээш мэдэгдэл илгээгээгүй |

Дараалсан 2 шалгалтад асуудалтай бол `[АСУУДАЛ] ...`, сэргэхэд `[СЭРГЭЛЭЭ] ...` нэг удаа илгээнэ. Backend асахад аль
хэдийн унтарсан байсан зүйлийг мэдэгдэхгүй (redeploy бүрт spam болохгүй). Илгээж чадаагүй мессежийг дараагийн
минутад дахин оролдоно.

Тохируулах (Railway → backend → Variables):

- `ALERT_WEBHOOK_URL` (НУУЦ — URL дотор token бий, log-д бичигдэхгүй):
  - **Discord**: channel → Edit Channel → Integrations → Webhooks → New Webhook → Copy Webhook URL
  - **Slack**: [Incoming Webhooks](https://api.slack.com/messaging/webhooks) app → channel сонгоод URL
  - **Telegram**: [@BotFather](https://t.me/BotFather)-оор bot үүсгэж token авна, bot-ыг group-д нэмнэ, chat id-г
    `https://api.telegram.org/bot<TOKEN>/getUpdates`-ээс олно →
    `https://api.telegram.org/bot<TOKEN>/sendMessage?chat_id=<CHAT_ID>`
  - Бусад (`{"text": "..."}` хүлээн авдаг webhook)
- `ALERT_CHECK_SECONDS` (анхдагч 60).

Шалгах: backend-ийн log-д `Alert: 60 сек тутам шалгаж discord.com руу илгээнэ`. Туршихдаа ai-service-ийг 2-3 минут
зогсооход `[АСУУДАЛ] AI service`, асаахад `[СЭРГЭЛЭЭ] AI service` ирнэ.

### Гаднаас (UptimeRobot)

Backend өөрөө унавал дотоод alert ажиллахгүй тул гаднаас шалгана. [UptimeRobot](https://uptimerobot.com) (үнэгүй, 5 минут):

1. **Keyword** monitor: `https://<backend>.up.railway.app/health`, keyword `"status":"ok"` → байхгүй бол alert
   (DB тасарсан үед `/health` 200 боловч `"status":"degraded"` буцаадаг тул keyword шаардлагатай).
2. **HTTP(s)** monitor: Vercel дээрх web хаяг.
3. Alert Contacts: Discord/Slack/Telegram integration эсвэл email — дээрхтэй ижил channel.

### Log

- Backend: Railway → Deployments → Logs (`ERROR`, `WARNING`-ийг шүүнэ). URL дахь нууц үг log-д `***` болно.
- Edge: `docker compose -f infra/edge/<mode>.yml logs -f` (`infra/README.md`).
