import { useSyncExternalStore } from "react";

// Instagram, Facebook, Messenger, TikTok, Snapchat, LINE, KakaoTalk-ийн доторх browser: камер (getUserMedia) болон
// WebRTC видеог ихэвчлэн хаадаг. Ийм үед хэрэглэгчид Chrome/Safari-д нээхийг зөвлөнө.
const IN_APP = /Instagram|FBAN|FBAV|FB_IAB|FBIOS|Messenger|musical_ly|TikTok|Bytedance|Snapchat|\bLine\/|KAKAOTALK/i;

export function isInAppBrowser(userAgent: string): boolean {
  return IN_APP.test(userAgent);
}

const noop = () => () => {};

/** Client дээр л шалгана (server render үед false) */
export function useInAppBrowser(): boolean {
  return useSyncExternalStore(noop, () => isInAppBrowser(navigator.userAgent), () => false);
}

export const IN_APP_HINT = "Instagram/Facebook зэрэг аппын доторх browser камер, шууд видеог хаадаг. ⋮ цэснээс «Chrome-д нээх» (iPhone: Safari) сонгоно уу.";
