// SA0.7 test layer: static fixture that follows the manifest contract.
// Only bundled in dev and e2e builds (see loadLayers.ts); the data is fake.
import manifest from "../../e2e/fixtures/fake-hotspots/manifest.json";
import points from "../../e2e/fixtures/fake-hotspots/points.json";
import { parseManifest, type Hotspot, type PointLayer } from "./manifest";

export const fakeLayer: PointLayer = {
  manifest: parseManifest(manifest),
  points: points as Hotspot[],
};
