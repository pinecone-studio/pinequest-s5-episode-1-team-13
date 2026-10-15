# Model training

Trains the PPE detector (helmet / no helmet / work uniform / no work uniform) on **per-person crops** of labeled camera frames.
Person detection itself uses a COCO-pretrained YOLO at inference time, so the PPE model is trained on exactly the same
geometry (person box + margin, enlarged to 512 px).

```
training/
  datasets/raw/*.jpg          collected frames                  (not committed: contains people's faces)
  datasets/labels/*.txt       confirmed YOLO labels, 0..4 = person, helmet, no_helmet, work_uniform, no_work_uniform
  models/base-n.pt            COCO YOLO26n weights (person detector + training base)   (not committed)
  runs/                       logs, state.json, temporary crop dataset                   (not committed)
  dataset_split.py            train / val / test split by consecutive blocks
  person_crops.py, crops.py   crop geometry and crop dataset builder
  train.py                    training, test evaluation, ONNX export
  watch.sh, watch_status.py   live terminal monitor
```

## Pipeline
1. **Split** (`dataset_split.py`): sorted frames are cut into blocks (7 train : 2 val : 1 test). Neighbouring frames of the same camera
   never land in different splits, so the test score is not inflated.
2. **Crops** (`crops.py`): every person gets 2 variants (normal, and a degraded "far away" one). PPE boxes are converted to crop
   coordinates; items that do not belong to this person (a helmet on a shelf) are dropped.
3. **Train** (`train.py`): fine-tunes `models/base-n.pt` on the crops, evaluates on the test split and exports
   `models/ppe-trained-<timestamp>.onnx` and `.pt`.

## Usage
```bash
cd training
pip install -r requirements.txt
python train.py --base models/base-n.pt --epochs 40 --imgsz 512 --batch 8
./watch.sh                      # in a second terminal
python -m pytest tests          # unit tests (no GPU, no weights needed)
```

`train.py` writes its progress to `runs/state.json` (`state`: running | done | failed | stopped, plus epoch and metrics) so a web UI
can poll it. It needs at least 30 labeled frames and never downloads anything during training.

## Notes
- With only a few dozen images the fine-tuned model can be worse than a model trained on a large dataset. Always check the per-class
  test report and add varied images (lighting, angles, people with and without helmets and uniforms).
- Do not commit `datasets/`, `models/` weights or `runs/`; `.gitignore` already excludes them.
