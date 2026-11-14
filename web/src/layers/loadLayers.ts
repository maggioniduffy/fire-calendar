import type { PointLayer } from "./manifest";

/** True in dev and e2e builds; production bundles never include the fake layer. */
export const fakeLayerEnabled = import.meta.env.DEV || import.meta.env.MODE === "e2e";

/** Layers to draw. Until the API lands (SA0.6) only the fake test layer exists. */
export async function loadLayers(): Promise<PointLayer[]> {
  if (fakeLayerEnabled) {
    const { fakeLayer } = await import("./fakeLayer");
    return [fakeLayer];
  }
  return [];
}
