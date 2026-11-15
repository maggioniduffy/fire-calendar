// Browser-only export helpers for the Dashboard charts (SA4.8): CSV text and SVG -> canvas -> PNG.

/** Starts a browser download of `blob` as `filename`. */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

export function downloadCsv(csv: string, filename: string): void {
  // BOM so spreadsheet apps read UTF-8 (accents in Spanish headers).
  downloadBlob(new Blob(["﻿", csv], { type: "text/csv;charset=utf-8" }), filename);
}

const STYLE_PROPS = [
  "fill",
  "fill-opacity",
  "stroke",
  "stroke-width",
  "stroke-opacity",
  "stroke-dasharray",
  "stroke-linecap",
  "stroke-linejoin",
  "opacity",
  "font-family",
  "font-size",
  "font-weight",
  "text-anchor",
  "dominant-baseline",
] as const;

/** Clone of `svg` with every computed paint/text property written inline, so it renders alone (CSS vars resolved). */
export function inlineStyles(svg: SVGSVGElement): SVGSVGElement {
  const clone = svg.cloneNode(true) as SVGSVGElement;
  const src = [svg, ...svg.querySelectorAll("*")];
  const dst = [clone, ...clone.querySelectorAll("*")];
  src.forEach((el, i) => {
    const cs = getComputedStyle(el);
    const target = dst[i] as SVGElement;
    for (const p of STYLE_PROPS) target.style.setProperty(p, cs.getPropertyValue(p));
  });
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  return clone;
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("svg render failed"));
    img.src = src;
  });
}

/** Renders `svg` below a title and a source line on a surface-colored canvas and downloads it as PNG. */
export async function downloadPng(svg: SVGSVGElement, title: string, source: string, filename: string): Promise<void> {
  const root = getComputedStyle(document.documentElement);
  const token = (name: string, fallback: string) => root.getPropertyValue(name).trim() || fallback;
  const w = Math.round(svg.getBoundingClientRect().width);
  const h = Math.round(svg.getBoundingClientRect().height);
  const pad = 16;
  const head = 52;
  const scale = 2;
  const xml = new XMLSerializer().serializeToString(inlineStyles(svg));
  const img = await loadImage(`data:image/svg+xml;charset=utf-8,${encodeURIComponent(xml)}`);

  const canvas = document.createElement("canvas");
  canvas.width = (w + pad * 2) * scale;
  canvas.height = (h + head + pad * 2) * scale;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("canvas unavailable");
  ctx.scale(scale, scale);
  ctx.fillStyle = token("--surface", "#F9F7F2");
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  const sans = token("--font-sans", "sans-serif");
  ctx.textBaseline = "top";
  ctx.fillStyle = token("--text", "#2A343B");
  ctx.font = `600 16px ${sans}`;
  ctx.fillText(title, pad, pad);
  ctx.fillStyle = token("--muted", "#5F6468");
  ctx.font = `400 12px ${sans}`;
  ctx.fillText(source, pad, pad + 24, w);
  ctx.drawImage(img, pad, pad + head, w, h);

  const blob = await new Promise<Blob | null>((r) => canvas.toBlob(r, "image/png"));
  if (!blob) throw new Error("png encoding failed");
  downloadBlob(blob, filename);
}
