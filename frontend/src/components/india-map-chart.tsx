"use client";

/**
 * India state map rendered from the bundled Highcharts/OpenStreetMap GeoJSON.
 * No coordinates are fabricated: state positions come from the boundary file,
 * while bubble anchors are area centroids derived from those same polygons.
 */

import { useMemo, useRef, useState, type PointerEvent as ReactPointerEvent, type WheelEvent as ReactWheelEvent } from "react";
import useSWR from "swr";
import { formatCurrency } from "@/lib/format";import { ChartEmpty } from "@/components/visual-charts";

type Position = [number, number];
type PolygonGeometry = { type: "Polygon"; coordinates: Position[][] };
type MultiPolygonGeometry = { type: "MultiPolygon"; coordinates: Position[][][] };
type Feature = {
  type: "Feature";
  properties: { name?: string; "hc-key"?: string; [key: string]: unknown };
  geometry: PolygonGeometry | MultiPolygonGeometry;
};
type GeoCollection = { type: "FeatureCollection"; features: Feature[] };

export type RegionValue = { name: string; sales: number; profit: number; margin?: number | null };

export type MapMode = "choropleth" | "heatmap" | "bubble";

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
  "ncr": "delhi",
  "new delhi": "delhi",
  "delhi ncr": "delhi",
  "andaman and nicobar": "andaman and nicobar islands",
  "dnh and dd": "dadra and nagar haveli and daman and diu",
  "dadra and nagar haveli": "dadra and nagar haveli and daman and diu",
  "daman and diu": "dadra and nagar haveli and daman and diu",
  "dadra nagar haveli and daman diu": "dadra and nagar haveli and daman and diu",
  "telengana": "telangana",
  "chattisgarh": "chhattisgarh",
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

export function unmatchedRegions(regions: RegionValue[]): RegionValue[] {
  const known = new Set(INDIA_STATE_NAMES.map(normaliseRegion));
  return regions.filter((region) => !known.has(normaliseRegion(region.name)));
}

async function fetchGeography(url: string): Promise<GeoCollection> {
  const response = await fetch(url, { cache: "force-cache" });
  if (!response.ok) throw new Error("The bundled India boundary file could not be loaded.");
  return (await response.json()) as GeoCollection;
}

function ringsFor(feature: Feature): Position[][] {
  if (feature.geometry.type === "Polygon") return feature.geometry.coordinates;
  return feature.geometry.coordinates.flatMap((polygon) => polygon);
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

function featureCentroid(feature: Feature): Position {
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
  if (!totalArea) return [0, 0];
  return [x / totalArea, y / totalArea];
}

function pathFor(feature: Feature, project: (position: Position) => Position): string {
  return ringsFor(feature)
    .map((ring) => ring.map((point, index) => {
      const [x, y] = project(point);
      return `${index === 0 ? "M" : "L"}${x.toFixed(2)} ${y.toFixed(2)}`;
    }).join(" ") + " Z")
    .join(" ");
}

type Props = {
  regions: RegionValue[];
  mode: MapMode;
  selectedRegion: string;
  search: string;
  onSelectRegion: (name: string) => void;
  height?: number;
};

export function IndiaMapChart({ regions, mode, selectedRegion, search, onSelectRegion, height = 560 }: Props) {
  const { data, error, isLoading } = useSWR<GeoCollection>("/india-states.geo.json", fetchGeography);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [hovered, setHovered] = useState("");
  const drag = useRef<{ pointerId: number; startX: number; startY: number; originX: number; originY: number } | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);

  const projected = useMemo(() => {
    if (!data?.features?.length) return null;
    const coordinates = data.features.flatMap((feature) => ringsFor(feature).flat());
    const lons = coordinates.map(([lon]) => lon);
    const lats = coordinates.map(([, lat]) => lat);
    const minLon = Math.min(...lons);
    const maxLon = Math.max(...lons);
    const minLat = Math.min(...lats);
    const maxLat = Math.max(...lats);
    const width = 100;
    const heightUnits = Math.max(40, (width * (maxLat - minLat)) / Math.max(maxLon - minLon, 0.001));
    const project = ([lon, lat]: Position): Position => [
      ((lon - minLon) / Math.max(maxLon - minLon, 0.001)) * width,
      ((maxLat - lat) / Math.max(maxLat - minLat, 0.001)) * heightUnits,
    ];
    const values = new Map(regions.map((region) => [normaliseRegion(region.name), region]));
    const features = data.features.map((feature) => {
      const name = String(feature.properties.name ?? feature.properties["hc-key"] ?? "Unknown");
      const [lon, lat] = featureCentroid(feature);
      const [x, y] = project([lon, lat]);
      return {
        name,
        key: normaliseRegion(name),
        path: pathFor(feature, project),
        centroid: [x, y] as Position,
        value: values.get(normaliseRegion(name)) ?? null,
      };
    });
    const maxSales = Math.max(...features.map((feature) => feature.value?.sales ?? 0), 0);
    return { width, height: heightUnits, features, maxSales };
  }, [data, regions]);

  const query = normaliseRegion(search);
  const selectedKey = normaliseRegion(selectedRegion);

  function handleWheel(event: ReactWheelEvent<SVGSVGElement>) {
    event.preventDefault();
    setZoom((current) => Math.min(4, Math.max(1, current - event.deltaY * 0.0015)));
  }

  function handlePointerDown(event: ReactPointerEvent<SVGSVGElement>) {
    if (zoom <= 1) return;
    drag.current = { pointerId: event.pointerId, startX: event.clientX, startY: event.clientY, originX: pan.x, originY: pan.y };
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function handlePointerMove(event: ReactPointerEvent<SVGSVGElement>) {
    if (!drag.current || !projected || !svgRef.current) return;
    const rect = svgRef.current.getBoundingClientRect();
    const scaleX = projected.width / Math.max(rect.width, 1);
    const scaleY = projected.height / Math.max(rect.height, 1);
    setPan({
      x: drag.current.originX + (event.clientX - drag.current.startX) * scaleX,
      y: drag.current.originY + (event.clientY - drag.current.startY) * scaleY,
    });
  }

  function handlePointerUp(event: ReactPointerEvent<SVGSVGElement>) {
    if (drag.current && event.currentTarget.hasPointerCapture(drag.current.pointerId)) {
      event.currentTarget.releasePointerCapture(drag.current.pointerId);
    }
    drag.current = null;
  }

  if (error) return <ChartEmpty message={error.message} />;
  if (isLoading || !projected) return <div className="loading-panel india-map-loading" aria-live="polite" />;

  return (
    <div className="india-map" style={{ minHeight: height }}>
      <div className="india-map-toolbar">
        <span>{mode === "bubble" ? "State bubbles" : mode === "heatmap" ? "Geographic heatmap" : "Choropleth"}</span>
        <div>
          <button type="button" onClick={() => setZoom((current) => Math.min(4, current + 0.25))} aria-label="Zoom in">+</button>
          <button type="button" onClick={() => setZoom((current) => Math.max(1, current - 0.25))} aria-label="Zoom out">−</button>
          <button type="button" onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }}>Reset</button>
        </div>
      </div>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${projected.width} ${projected.height}`}
        className="india-map-svg"
        style={{ height }}
        role="img"
        aria-label="India state-wise sales map"
        onWheel={handleWheel}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerLeave={handlePointerUp}
      >
        <g transform={`translate(${projected.width / 2 + pan.x} ${projected.height / 2 + pan.y}) scale(${zoom}) translate(${-projected.width / 2} ${-projected.height / 2})`}>
          {projected.features.map((feature) => {
            const ratio = projected.maxSales ? (feature.value?.sales ?? 0) / projected.maxSales : 0;
            const isSelected = selectedKey === feature.key;
            const matches = !query || feature.key.includes(query);
            const fill = mode === "heatmap"
              ? `rgba(205, 92, 36, ${(feature.value ? 0.16 + ratio * 0.84 : 0.05).toFixed(3)})`
              : `rgba(47, 101, 167, ${(feature.value ? 0.14 + ratio * 0.86 : 0.06).toFixed(3)})`;
            return mode === "bubble" ? null : (
              <path
                key={feature.key}
                d={feature.path}
                fill={fill}
                stroke={isSelected ? "#b8860b" : hovered === feature.key ? "#173b73" : "#ffffff"}
                strokeWidth={isSelected ? 1.6 : hovered === feature.key ? 1.1 : 0.35}
                opacity={matches ? 1 : 0.25}
                onClick={() => onSelectRegion(isSelected ? "" : feature.name)}
                onMouseEnter={() => setHovered(feature.key)}
                onMouseLeave={() => setHovered("")}
                className={feature.value ? "india-map-state has-value" : "india-map-state"}
                tabIndex={0}
                role="button"
                aria-label={`${feature.name}: ${feature.value ? formatCurrency(feature.value.sales) : "no mapped sales"}`}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelectRegion(isSelected ? "" : feature.name);
                  }
                }}
              >
                <title>{feature.value ? `${feature.name} · ${formatCurrency(feature.value.sales)} sales · ${formatCurrency(feature.value.profit)} profit` : `${feature.name} · no matching region value`}</title>
              </path>
            );
          })}
          {mode === "bubble" ? projected.features.map((feature) => {
            const ratio = projected.maxSales ? (feature.value?.sales ?? 0) / projected.maxSales : 0;
            const isSelected = selectedKey === feature.key;
            const matches = !query || feature.key.includes(query);
            if (!feature.value) return null;
            return (
              <g key={feature.key} opacity={matches ? 1 : 0.25} onClick={() => onSelectRegion(isSelected ? "" : feature.name)} className="india-map-bubble" role="button" tabIndex={0} aria-label={`${feature.name}: ${formatCurrency(feature.value.sales)}`} onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onSelectRegion(isSelected ? "" : feature.name);
                }
              }}>
                <circle cx={feature.centroid[0]} cy={feature.centroid[1]} r={0.7 + Math.sqrt(ratio) * 4.6} fill={isSelected ? "#d9a41a" : "#2f65a7"} fillOpacity={0.62} stroke="#ffffff" strokeWidth={0.35}>
                  <title>{`${feature.name} · ${formatCurrency(feature.value.sales)} sales`}</title>
                </circle>
              </g>
            );
          }) : null}
        </g>
      </svg>
      <div className="india-map-legend">
        <span className="india-map-legend-swatch" aria-hidden="true" />
        <span>Lower sales</span>
        <i aria-hidden="true" />
        <span>Higher sales</span>
      </div>
      {mode === "bubble" ? <p className="india-map-note">Bubble anchors are area centroids calculated from the bundled state boundaries — not from city coordinates.</p> : null}
      <p className="india-map-note">Zoom with +/− or the mouse wheel; drag to pan when zoomed. Click a state to cross-filter the dashboard.</p>
    </div>
  );
}
