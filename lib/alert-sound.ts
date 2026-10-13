import { useSyncExternalStore } from "react";

/** Зөрчлийн дуут дохио: Web Audio-оор үүсгэнэ (файл татахгүй). Унтраалтыг localStorage-д хадгална. */
const KEY = "alert-sound";
const MIN_GAP_MS = 3000; // олон зөрчил дараалан ирэхэд дуу давтагдахгүй
const listeners = new Set<() => void>();
let ctx: AudioContext | null = null;
let lastPlayed = 0;

function soundEnabled(): boolean {
  try {
    return localStorage.getItem(KEY) !== "off";
  } catch {
    return true;
  }
}

export function setSoundEnabled(on: boolean): void {
  try {
    localStorage.setItem(KEY, on ? "on" : "off");
  } catch {
    /* хадгалах боломжгүй бол энэ сессэд л үйлчилнэ */
  }
  listeners.forEach((l) => l());
}

export function useSoundEnabled(): boolean {
  return useSyncExternalStore(
    (cb) => { listeners.add(cb); return () => { listeners.delete(cb); }; },
    soundEnabled,
    () => true,
  );
}

function context(): AudioContext | null {
  if (!ctx) {
    const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctor) return null;
    ctx = new Ctor();
  }
  return ctx;
}

/** Browser хэрэглэгчийн үйлдлийн дараа л дуу гаргахыг зөвшөөрдөг: эхний дарралт/товчлуурын дараа идэвхжүүлнэ. */
export function unlockAudio(): void {
  const c = context();
  if (c && c.state === "suspended") void c.resume();
}

/** «Дий-дий-дий»: өндөр авиатай гурван богино дохио. force=true бол унтраалт/давтамжийг үл хамаарна (шалгах товч). */
const BEEPS = 3;
const BEEP_STEP = 0.2; // секунд: дохио тутмын хоорондох зай
const BEEP_LENGTH = 0.11;
const BEEP_FREQ = 1760; // A6: цоолмог, шууд анхаарал татна

export function playAlert(force = false): void {
  if (!force && (!soundEnabled() || Date.now() - lastPlayed < MIN_GAP_MS)) return;
  const c = context();
  if (!c) return;
  if (c.state === "suspended") void c.resume();
  if (c.state !== "running" && !force) return; // хараахан зөвшөөрөгдөөгүй
  lastPlayed = Date.now();
  const start = c.currentTime + 0.02;
  for (let i = 0; i < BEEPS; i++) {
    const osc = c.createOscillator();
    const gain = c.createGain();
    const t = start + i * BEEP_STEP;
    osc.type = "square";
    osc.frequency.value = BEEP_FREQ;
    gain.gain.setValueAtTime(0.0001, t);
    gain.gain.exponentialRampToValueAtTime(0.16, t + 0.008); // хурц эхлэл
    gain.gain.setValueAtTime(0.16, t + BEEP_LENGTH - 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + BEEP_LENGTH);
    osc.connect(gain).connect(c.destination);
    osc.start(t);
    osc.stop(t + BEEP_LENGTH + 0.01);
  }
}
