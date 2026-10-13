import { useEffect, useState, type RefObject } from "react";

/** Элементийн (өргөн, өндөр) px-ийг хянана: эргүүлсэн видеог талбайд яг багтаахад хэрэгтэй. */
export function useElementSize(ref: RefObject<HTMLElement | null>): { w: number; h: number } {
  const [size, setSize] = useState({ w: 0, h: 0 });
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => setSize({ w: entry.contentRect.width, h: entry.contentRect.height }));
    observer.observe(el);
    return () => observer.disconnect();
  }, [ref]);
  return size;
}
