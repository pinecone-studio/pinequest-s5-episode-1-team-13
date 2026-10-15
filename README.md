# pinequest-s5-episode-1-team-13

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
- Бодит утгуудыг багаасаа password manager эсвэл хувийн мессежээр авна.

## Тест

```bash
cd backend && python -m pytest
cd ai-service && python -m pytest
cd training && python -m pytest tests
cd web && npm run lint && npm run typecheck
```

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
