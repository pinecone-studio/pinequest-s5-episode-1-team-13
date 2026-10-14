# AI service image. Same base as backend/Dockerfile.
FROM python:3.12-slim

# ffmpeg: sends camera video to MediaMTX. libgl1 + libglib2.0-0: needed by OpenCV.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# CPU-only PyTorch first: about 5x smaller than the default (CUDA) build. Servers without an NVIDIA GPU don't need CUDA.
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN useradd -m appuser && mkdir -p /models /training /tmp/ultralytics && chown -R appuser /app /models /training /tmp/ultralytics
USER appuser

# Models and training data live outside the image (mount them as volumes).
# YOLO_AUTOINSTALL=False: never pip install at run time; YOLO_CONFIG_DIR: a folder the app user can write.
ENV PYTHONUNBUFFERED=1 \
    YOLO_AUTOINSTALL=False \
    YOLO_CONFIG_DIR=/tmp/ultralytics \
    DATASET_DIR=/training \
    DEVICE=cpu

CMD ["python", "-m", "app.main"]
