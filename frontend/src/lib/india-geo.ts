/**
 * Shared helpers for the bundled India state boundaries.
 *
 * Both maps use the same projection so a city bubble always lands inside the
 * correct state outline.  Nothing here invents coordinates: every polygon and
 * centroid comes from `public/india-states.geo.json`.
 */

export type Position = [number, number];
export type PolygonGeometry = { type: "Polygon"; coordinates: Position[][] };
export type MultiPolygonGeometry = { type: "MultiPolygon"; coordinates: Position[][][] };
export type IndiaFeature = {
  type: "Feature";
  properties: { name?: string; "hc-key"?: string; [key: string]: unknown };
  geometry: PolygonGeometry | MultiPolygonGeometry;
};
export type IndiaGeo = { type: "FeatureCollection"; features: IndiaFeature[] };

export const INDIA_GEO_URL = "/india-states.geo.json";

// Geographic bounds of the bundled file, padded by ~0.2° so coastal strokes do
// not clip.  Longitude is scaled by cos(mean latitude) so the country is not
// stretched horizontally.
export const INDIA_BOUNDS = { minLon: 67.9, maxLon: 97.6, minLat: 6.4, maxLat: 35.9 };
const MEAN_LATITUDE = 22;
const LON_SCALE = Math.cos((MEAN_LATITUDE * Math.PI) / 180);

export const INDIA_MAP_WIDTH = 100;
export const INDIA_MAP_HEIGHT =
  (INDIA_MAP_WIDTH * (INDIA_BOUNDS.maxLat - INDIA_BOUNDS.minLat)) /
  ((INDIA_BOUNDS.maxLon - INDIA_BOUNDS.minLon) * LON_SCALE);

export function projectIndia(lon: number, lat: number, width = INDIA_MAP_WIDTH, height = INDIA_MAP_HEIGHT): Position {
  const x = ((lon - INDIA_BOUNDS.minLon) / (INDIA_BOUNDS.maxLon - INDIA_BOUNDS.minLon)) * width;
  const y = ((INDIA_BOUNDS.maxLat - lat) / (INDIA_BOUNDS.maxLat - INDIA_BOUNDS.minLat)) * height;
  return [x, y];
}

export function ringsFor(feature: IndiaFeature): Position[][] {
  if (feature.geometry.type === "Polygon") return feature.geometry.coordinates;
  return feature.geometry.coordinates.flatMap((polygon) => polygon);
}

export function pathFor(feature: IndiaFeature, width = INDIA_MAP_WIDTH, height = INDIA_MAP_HEIGHT): string {
  return ringsFor(feature)
    .map((ring) =>
      `${ring
        .map(([lon, lat], index) => {
          const [x, y] = projectIndia(lon, lat, width, height);
          return `${index === 0 ? "M" : "L"}${x.toFixed(2)} ${y.toFixed(2)}`;
        })
        .join(" ")} Z`,
    )
    .join(" ");
}

function ringCentroid(ring: Position[]): { area: number; x: number; y: number } {
  let area = 0;
  let x = 0;
  let y = 0;
  for (let index = 0; index < ring.length; index += 1) {
    const [x1, y1] = ring[index];
    const [x2, y2] = ring[(index + 1) % ring.length];
    const cross = x1 * y2 - x2 * y1;
    area += cross;
    x += (x1 + x2) * cross;
    y += (y1 + y2) * cross;
  }
  area /= 2;
  if (Math.abs(area) < 1e-9) {
    const average = ring.reduce((sum, [lon, lat]) => ({ lon: sum.lon + lon, lat: sum.lat + lat }), { lon: 0, lat: 0 });
    return { area: 1, x: average.lon / Math.max(ring.length, 1), y: average.lat / Math.max(ring.length, 1) };
  }
  return { area, x: x / (6 * area), y: y / (6 * area) };
}

/** Area-weighted centroid of a (multi)polygon, projected to viewBox units. */
export function featureCentroid(feature: IndiaFeature, width = INDIA_MAP_WIDTH, height = INDIA_MAP_HEIGHT): Position {
  const rings = ringsFor(feature);
  let totalArea = 0;
  let x = 0;
  let y = 0;
  for (const ring of rings) {
    const centroid = ringCentroid(ring);
    const weight = Math.abs(centroid.area);
    totalArea += weight;
    x += centroid.x * weight;
    y += centroid.y * weight;
  }
  if (!totalArea) return projectIndia(INDIA_BOUNDS.minLon, INDIA_BOUNDS.maxLat, width, height);
  return projectIndia(x / totalArea, y / totalArea, width, height);
}

export async function fetchIndiaGeography(): Promise<IndiaGeo> {
  const response = await fetch(INDIA_GEO_URL, { cache: "force-cache" });
  if (!response.ok) throw new Error("The bundled India boundary file could not be loaded.");
  return (await response.json()) as IndiaGeo;
}

export const INDIA_STATE_NAMES = [
  "Andaman and Nicobar Islands", "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chandigarh",
  "Chhattisgarh", "Dadra and Nagar Haveli and Daman and Diu", "Delhi", "Goa", "Gujarat", "Haryana",
  "Himachal Pradesh", "Jammu and Kashmir", "Jharkhand", "Karnataka", "Kerala", "Ladakh", "Lakshadweep",
  "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Puducherry",
  "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand",
  "West Bengal",
];

const STATE_ALIASES: Record<string, string> = {
  orissa: "odisha",
  uttaranchal: "uttarakhand",
  pondicherry: "puducherry",
  "j and k": "jammu and kashmir",
  "jammu and kashmir state": "jammu and kashmir",
  ncr: "delhi",
  "new delhi": "delhi",
  "delhi ncr": "delhi",
  "andaman and nicobar": "andaman and nicobar islands",
  "dnh and dd": "dadra and nagar haveli and daman and diu",
  "dadra and nagar haveli": "dadra and nagar haveli and daman and diu",
  "daman and diu": "dadra and nagar haveli and daman and diu",
  "dadra nagar haveli and daman diu": "dadra and nagar haveli and daman and diu",
  telengana: "telangana",
  chattisgarh: "chhattisgarh",
  "west bengal state": "west bengal",
};

export function normaliseRegion(value: string): string {
  const cleaned = value
    .toLowerCase()
    .replaceAll("&", " and ")
    .replace(/[^a-z0-9]+/g, " ")
    .trim()
    .replace(/\s+/g, " ");
  return STATE_ALIASES[cleaned] ?? cleaned;
}
