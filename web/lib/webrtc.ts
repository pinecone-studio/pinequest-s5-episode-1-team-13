/**
 * WHEP (WebRTC-HTTP Egress Protocol) клиент — MediaMTX-ээс камерын видеог авна.
 * Нэвтрэлт: backend-ийн өгсөн богино хугацаатай Bearer токен (тухайн камерын path-д л хүчинтэй).
 */
export async function startWhep(
  whepUrl: string,
  token: string,
  onStream: (stream: MediaStream) => void,
  onClosed: () => void,
): Promise<RTCPeerConnection> {
  // STUN: MediaMTX өөр сүлжээнд (NAT-ын ард) байхад public хаягаа олж шууд холбогдоно
  const pc = new RTCPeerConnection({ iceServers: [{ urls: "stun:stun.l.google.com:19302" }] });
  pc.addTransceiver("video", { direction: "recvonly" });
  pc.ontrack = (event) => {
    // Browser-ийн буферийг (jitter buffer) хамгийн бага болгоно: видео илрүүлэлтийн хайрцгаас хоцрохгүй, гацахгүй
    const receiver = event.receiver as RTCRtpReceiver & { jitterBufferTarget?: number | null; playoutDelayHint?: number | null };
    try {
      receiver.jitterBufferTarget = 0;
      receiver.playoutDelayHint = 0;
    } catch {
      /* дэмжигдээгүй browser: өгөгдмөл буфер */
    }
    onStream(event.streams[0]);
  };
  pc.onconnectionstatechange = () => {
    // "disconnected" ихэвчлэн түр зуурын (ICE өөрөө сэргэнэ); сэргэхгүй бол "failed" болно
    if (["failed", "closed"].includes(pc.connectionState)) onClosed();
  };

  try {
    await pc.setLocalDescription(await pc.createOffer());
    // ICE candidate-үүдийг цуглуулж дуустал (хамгийн ихдээ 1.5 сек) хүлээнэ
    await new Promise<void>((resolve) => {
      if (pc.iceGatheringState === "complete") return resolve();
      const done = () => pc.iceGatheringState === "complete" && (pc.removeEventListener("icegatheringstatechange", done), resolve());
      pc.addEventListener("icegatheringstatechange", done);
      setTimeout(resolve, 1500);
    });

    const response = await fetch(whepUrl, {
      method: "POST",
      headers: { "Content-Type": "application/sdp", Authorization: `Bearer ${token}` },
      body: pc.localDescription!.sdp,
    });
    if (!response.ok) throw new Error(`WHEP ${response.status}`);
    await pc.setRemoteDescription({ type: "answer", sdp: await response.text() });
    return pc;
  } catch (err) {
    pc.close();
    throw err;
  }
}

/**
 * WHIP (WebRTC-HTTP Ingestion Protocol) — энэ browser-ийн камерыг MediaMTX руу дамжуулна (BROWSER камер).
 * Нэвтрэлт: backend-ийн тухайн камерт л хүчинтэй publish токен.
 */
export async function startWhip(whipUrl: string, token: string, stream: MediaStream, onClosed: () => void): Promise<RTCPeerConnection> {
  const pc = new RTCPeerConnection({ iceServers: [{ urls: "stun:stun.l.google.com:19302" }] });
  // AI-д 30 fps хэрэггүй: 15 fps / ~1.2 Mbps-ээр хязгаарлавал tunnel/NAT-аар гацахгүй, латент багатай (хөдөлгөөн бага хугацаанд л хоцорно)
  stream.getVideoTracks().forEach((track) =>
    pc.addTransceiver(track, { direction: "sendonly", sendEncodings: [{ maxBitrate: 1_200_000, maxFramerate: 15 }] }),
  );
  pc.onconnectionstatechange = () => {
    // "disconnected" ихэвчлэн түр зуурын (ICE өөрөө сэргэнэ); сэргэхгүй бол "failed" болно
    if (["failed", "closed"].includes(pc.connectionState)) onClosed();
  };

  try {
    await pc.setLocalDescription(await pc.createOffer());
    await new Promise<void>((resolve) => {
      if (pc.iceGatheringState === "complete") return resolve();
      const done = () => pc.iceGatheringState === "complete" && (pc.removeEventListener("icegatheringstatechange", done), resolve());
      pc.addEventListener("icegatheringstatechange", done);
      setTimeout(resolve, 1500);
    });

    const response = await fetch(whipUrl, {
      method: "POST",
      headers: { "Content-Type": "application/sdp", Authorization: `Bearer ${token}` },
      body: pc.localDescription!.sdp,
    });
    if (!response.ok) throw new Error(`WHIP ${response.status}`);
    await pc.setRemoteDescription({ type: "answer", sdp: await response.text() });
    return pc;
  } catch (err) {
    pc.close();
    throw err;
  }
}
