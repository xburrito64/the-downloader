export function duration(seconds) {
  if (!seconds) return "";
  const total = Math.round(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = String(total % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${s}` : `${m}:${s}`;
}

export function speed(bytesPerSecond) {
  if (!bytesPerSecond) return "";
  if (bytesPerSecond >= 1_000_000) return `${(bytesPerSecond / 1_000_000).toFixed(1)} MB/s`;
  return `${Math.max(1, Math.round(bytesPerSecond / 1000))} kB/s`;
}

export function plural(count, word) {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

/** A stand-in colour pair for an item without a cover, always the same for the same text. */
export function tint(text) {
  let hash = 0;
  for (let i = 0; i < text.length; i++) hash = (hash * 31 + text.charCodeAt(i)) | 0;
  const hue = Math.abs(hash) % 360;
  return `linear-gradient(135deg, hsl(${hue} 55% 42%), hsl(${(hue + 50) % 360} 60% 28%))`;
}
