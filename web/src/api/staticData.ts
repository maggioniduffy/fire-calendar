import { createStaticClient, type Manifest, type RegionInfo } from "./staticClient";

/** The one client of the build: data root from `VITE_DATA_URL` (unused when it is not set). */
export const staticClient = createStaticClient(import.meta.env.VITE_DATA_URL ?? "");

export interface Catalog {
  manifest: Manifest;
  areas: RegionInfo[];
}

let catalog: Catalog | null = null;

/** Loads manifest.json and areas.json once, before the app renders in static mode. */
export async function loadCatalog(): Promise<Catalog> {
  const [manifest, areas] = await Promise.all([staticClient.manifest(), staticClient.areas()]);
  catalog = { manifest, areas };
  return catalog;
}

/** Sync access to what `loadCatalog` fetched (null in API mode or before the load). */
export const getCatalog = (): Catalog | null => catalog;
export const setCatalog = (c: Catalog | null): void => {
  catalog = c;
};

export const regionInfo = (id: string): RegionInfo | null => catalog?.areas.find((a) => a.id === id) ?? null;
