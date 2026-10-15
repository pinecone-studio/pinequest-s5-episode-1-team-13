# pinequest-s5-episode-1-team-13

[![CI](https://github.com/pinecone-studio/pinequest-s5-episode-1-team-13/actions/workflows/ci.yml/badge.svg)](https://github.com/pinecone-studio/pinequest-s5-episode-1-team-13/actions/workflows/ci.yml)

Үйлдвэрийн IP камераас ажилчдын **дуулга** болон **ажлын хувцсыг** AI-аар бодит цагт шалгаж, зөрчил илэрвэл
snapshot авч dashboard дээр шууд мэдэгддэг систем.

```
IP камер ─RTSP─► ai-service (YOLO) ─► backend /internal/* ─► WebSocket ─► web dashboard
                     │                     │
                     ▼                     ▼
               MediaMTX (видео)     Supabase (PostgreSQL + Storage)
                     │
                     └──────────── WebRTC ───────────────► web dashboard
```

## Бүтэц

| Хавтас | Үүрэг | Стек |
|---|---|---|
| [`backend/`](backend/) | REST API, WebSocket, нэвтрэлт ба эрх, камер, зөрчил, сургалтын API | FastAPI, SQLAlchemy |
| [`web/`](web/) | Dashboard: шууд видео, зөрчил, камер, сургалт, тохиргоо | Next.js 16, Tailwind, shadcn/ui |
| [`ai-service/`](ai-service/) | Камер унших, YOLO-оор PPE илрүүлэх, зөрчил бүртгэх, видео MediaMTX руу дамжуулах | Python, Ultralytics, OpenCV |
| [`training/`](training/) | Шошглосон зургаар PPE модель сургаж ONNX экспортлох | Ultralytics |

## Шаардлага

- Python 3.12, Node.js 20+
- ffmpeg (`brew install ffmpeg`): ai-service видео дамжуулахад
- MediaMTX (`brew install mediamtx`): шууд видео
- Supabase project (PostgreSQL + `violation-snapshots` storage bucket)

## Локалд асаах

Сервис бүрийг тусдаа терминалд асаана. Backend-ийг **8001** порт дээр асаавал `web/.env.local.example`-ийн
утгатай шууд таарна.

**1. Backend**

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                       # утгуудыг бөглөнө
python -m scripts.create_admin             # анхны ADMIN хэрэглэгч
uvicorn app.main:app --reload --port 8001
```

**2. AI service**

```bash
cd ai-service
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                       # BACKEND_URL=http://localhost:8001
# Моделийн .pt файлаа models/ руу хуулаад .env-д MODEL_PATH=models/<model>.pt гэж тохируулна
python -m scripts.check_model             # модель уншигдаж байгааг шалгана
python -m app.main
```

**3. Web**

```bash
cd web
npm install
cp .env.local.example .env.local
npm run dev                                # http://localhost:3000
```

Сургалтын заавар: [`training/README.md`](training/README.md).

## Орчны хувьсагч

- `.env`, `.env.local` файлуудыг **хэзээ ч commit хийхгүй**. Root-ийн `.gitignore` хааж байгаа.
- Жишээ файлууд: `backend/.env.example`, `ai-service/.env.example`, `web/.env.local.example`
- `INTERNAL_API_KEY` ба `CAMERA_SECRET_KEY` нь `backend/.env` болон `ai-service/.env` хоёрт **ижил** байх ёстой.
- Бодит утгуудыг зөвхөн багийн password manager-аас авна — chat, мессежээр хэзээ ч дамжуулахгүй.
- Нууц түлхүүр удирдах, солих, мониторинг ба alert: [`SECURITY.md`](SECURITY.md).

## Тест

```bash
(cd backend && python -m pytest)
(cd ai-service && python -m pytest)
(cd training && python -m pytest tests)
(cd web && npm run lint && npm run typecheck)
```

## CI/CD

Push бүрт (бүх branch) [GitHub Actions](.github/workflows/ci.yml) 5 job ажиллуулна: `secrets` (шинэ commit-д нууц
утга байгаа эсэх, gitleaks), `backend`, `ai-service`, `training` (pytest, CPU-only PyTorch), `web` (lint, typecheck, build).
CI дээр `.env` байхгүй тул DB-тэй тестүүд алгасагдана.

Deploy-ийг платформуудын GitHub integration хийнэ, GitHub-д нууц token хадгалахгүй:

| Сервис | Хаана | Хэзээ |
|---|---|---|
| backend | Railway | `main` руу merge хийгдэж, CI давсны дараа (`backend/` өөрчлөгдсөн үед л) |
| web | Vercel | `main` → production, бусад branch → preview (`web/` өөрчлөгдсөн үед л) |

Нэг удаагийн тохиргоо (dashboard дээр):

- **GitHub** → Settings → Actions → General: **Allow all actions and reusable workflows** (байгууллагын түвшинд
  унтраалттай бол org owner асаана). Push хийсний дараа Actions tab-д CI run гарч ирэхгүй бол энэ тохиргоог шалгана.
- **Railway** → backend service → Settings: Root Directory `backend`, Config-as-code path `/backend/railway.json`
  ([`backend/railway.json`](backend/railway.json): Dockerfile, `/health` healthcheck, зөвхөн `/backend/**` өөрчлөгдөхөд deploy),
  Deploy → **Wait for CI** асаана (CI унавал deploy хийхгүй).
- **Vercel** → project → Settings: Root Directory `web`, Production Branch `main`
  ([`web/vercel.json`](web/vercel.json): `web/` өөрчлөгдөөгүй commit-ийг build хийхгүй).
- **GitHub** → Settings → Branches → `main` rule: **Require a pull request before merging**,
  **Require status checks to pass**: `secrets`, `backend`, `ai-service`, `training`, `web`. Vercel CI хүлээдэггүй тул production-ийг
  энэ дүрэм хамгаална.

## Хамтран ажиллах дүрэм

- `main` руу шууд push хийхгүй. Branch → PR → review → merge.
- Том ажлыг жижиг PR болгон хуваана (`backend-1-core`, `backend-2-auth`, ...). Stacked PR бол доороосоо
  эхэлж дарааллаар нь merge хийнэ.
- Commit message: [Conventional Commits](https://www.conventionalcommits.org/) хэлбэр,
  жишээ нь `feat(backend): ...`, `fix(ai): ...`, `docs(web): ...`

## Баг

| Үүрэг | Гишүүн | Хавтас |
|---|---|---|
| Frontend | Duuree | `web/` |
| Backend API | Tsolmon | `backend/` |
| Data, Supabase | Tugserdem | `database/` |
| AI detection | Anar | `ai-service/` |
| ML, dataset | Tsenguun | `training/` |
| Video, Infra (DevOps) | Sumer | `infra/`, `docker-compose.yml` |

## Хийгдэж буй

- `database/schema.sql`: DB schema (backend-ийн модель үүнтэй 1:1)
- `infra/`, `docker-compose.yml`: MediaMTX тохиргоо, бүх сервисийг нэг дор асаах
