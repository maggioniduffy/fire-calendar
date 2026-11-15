/** File name from a `Content-Disposition` header (`attachment; filename="x.csv"`), or null. */
export function filenameFromDisposition(header: string | null): string | null {
  const m = header?.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
  if (!m) return null;
  let name = m[1].trim();
  try {
    name = decodeURIComponent(name);
  } catch {
    // Keep the raw value when it is not percent-encoded.
  }
  name = name.replace(/[\\/]/g, "_");
  return name === "" ? null : name;
}

/** Hands a response body to the browser as a file download. */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}
