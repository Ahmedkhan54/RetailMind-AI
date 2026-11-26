"use client";

/**
 * India state map rendered from the bundled Highcharts/OpenStreetMap GeoJSON.
 * No coordinates are fabricated: state positions come from the boundary file,
 * while bubble anchors are area centroids derived from those same polygons.
 *
 * The component only plots the values it is given. A state with no value is
 * drawn as an explicit "no data" shape instead of a near-invisible tint.
 */

import { useMemo, useRef, useState, type PointerEvent as ReactPointerEvent, type WheelEvent as ReactWheelEvent } from "react";
import useSWR from "swr";
import { formatCompactCurrency, formatCurrency, formatPercent } from "@/lib/format";
import {
  featureCentroid,
  fetchIndiaGeography,
  INDIA_GEO_URL,
  INDIA_MAP_HEIGHT,
  INDIA_MAP_WIDTH,
  INDIA_STATE_NAMES,
  normaliseRegion,
  pathFor,
  type IndiaGeo,
  type Position,
} from "@/lib/india-geo";

export { INDIA_STATE_NAMES, normaliseRegion };

export type RegionValue = { name: string; sales: number; profit: number; margin?: number | null };
export type MapMode = "choropleth" | "heatmap" | "bubble";

export function unmatchedRegions(regions: RegionValue[]): RegionValue[] {
  const known = new Set(INDIA_STATE_NAMES.map(normaliseRegion));
  return regions.filter((region) => !known.has(normaliseRegion(region.name)));
}

type Box = { x: number; y: number; width: number; height: number };

function intersects(left: Box, right: Box): boolean {
  return !(
    left.x + left.width < right.x ||
    right.x + right.width < left.x ||
    left.y + left.height < right.y ||
    right.y + right.height < left.y
  );
}

/** Greedy label placement in viewBox units; a label is skipped rather than overlapped. */
function placeLabels(
  entries: { key: string; point: Position; text: string }[],
  placedCircles: { point: Position; radius: number }[] = [],
): { key: string; text: string; x: number; y: number; width: number }[] {
  const accepted: { key: string; text: string; x: number; y: number; width: number }[] = [];
  const occupied: Box[] = placedCircles.map(({ point, radius }) => ({
    x: point[0] - radius,
    y: point[1] - radius,
    width: radius * 2,
    height: radius * 2,
  }));
  const font = 2.3;
  for (const entry of entries) {
    const width = Math.min(entry.text.length * font * 0.56, 26);
    const candidates: Position[] = [
      [entry.point[0] + 1.4, entry.point[1] - 1.4],
      [entry.point[0] + 1.4, entry.point[1] + 3.1],
      [entry.point[0] - width - 1.4, entry.point[1] - 1.4],
      [entry.point[0] - width / 2, entry.point[1] - 2.6],
      [entry.point[0] - width / 2, entry.point[1] + 3.6],
    ];
    for (const [x, y] of candidates) {
      const box: Box = { x, y: y - font, width, height: font + 0.6 };
      const inBounds = x > 0 && x + width < INDIA_MAP_WIDTH && y > font && y < INDIA_MAP_HEIGHT;
      if (!inBounds) continue;
      if (occupied.some((other) => intersects(box, other))) continue;
      occupied.push(box);
      accepted.push({ key: entry.key, text: entry.text, x, y, width });
      break;
    }
  }
  return accepted;
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
  const { data, error, isLoading } = useSWR<IndiaGeo>(INDIA_GEO_URL, fetchIndiaGeography);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [hovered, setHovered] = useState("");
  const drag = useRef<{ pointerId: number; startX: number; startY: number; originX: number; originY: number } | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);

  const projected = useMemo(() => {
    if (!data?.features?.length) return null;
    const values = new Map(regions.map((region) => [normaliseRegion(region.name), region]));
    const features = data.features.map((feature) => {
      const name = String(feature.properties.name ?? feature.properties["hc-key"] ?? "Unknown");
      const key = normaliseRegion(name);
      return {
        name,
        key,
        path: pathFor(feature),
        centroid: featureCentroid(feature),
        value: values.get(key) ?? null,
      };
    });
    const maxSales = Math.max(...features.map((feature) => feature.value?.sales ?? 0), 0);
    const minSales = Math.min(...features.filter((feature) => feature.value).map((feature) => feature.value!.sales), maxSales);
    const matched = features.filter((feature) => feature.value).length;
    return { features, maxSales, minSales: Number.isFinite(minSales) ? minSales : 0, matched };
  }, [data, regions]);

  const query = normaliseRegion(search);
  const selectedKey = normaliseRegion(selectedRegion);

  const labels = useMemo(() => {
    if (!projected) return [];
    const ranked = projected.features
      .filter((feature) => feature.value && (!query || feature.key.includes(query)))
      .sort((left, right) => (right.value?.sales ?? 0) - (left.value?.sales ?? 0))
      .slice(0, 7);
    const circles = mode === "bubble"
      ? ranked.map((feature) => {
          const ratio = projected.maxSales ? (feature.value?.sales ?? 0) / projected.maxSales : 0;
          return { point: feature.centroid, radius: 0.9 + Math.sqrt(Math.max(ratio, 0)) * 4.2 };
        })
      : [];
    return placeLabels(
      ranked.map((feature) => ({ key: feature.key, point: feature.centroid, text: feature.name })),
      circles,
    );
  }, [mode, projected, query]);

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
    if (!drag.current || !svgRef.current) return;
    const rect = svgRef.current.getBoundingClientRect();
    const scaleX = INDIA_MAP_WIDTH / Math.max(rect.width, 1);
    const scaleY = INDIA_MAP_HEIGHT / Math.max(rect.height, 1);
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

  if (error) {
    return <div className="india-map-empty" role="status">{error.message}</div>;
  }
  if (isLoading || !projected) return <div className="loading-panel india-map-loading" aria-live="polite" aria-label="Loading the India map" />;

  const hasValues = projected.matched > 0;

  return (
    <div className="india-map">
      <div className="india-map-toolbar">
        <span>{mode === "bubble" ? "State bubbles" : mode === "heatmap" ? "Geographic heatmap" : "Choropleth"}</span>
        <div>
          <button type="button" onClick={() => setZoom((current) => Math.min(4, current + 0.25))} aria-label="Zoom in">+</button>
          <button type="button" onClick={() => setZoom((current) => Math.max(1, current - 0.25))} aria-label="Zoom out">−</button>
          <button type="button" onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }}>Reset</button>
        </div>
      </div>

      {!hasValues ? (
        <p className="india-map-empty" role="status">
          No state-level values are available for this selection, so every boundary is shown as <strong>no data</strong>.
        </p>
      ) : null}

      <svg
        ref={svgRef}
        viewBox={`0 0 ${INDIA_MAP_WIDTH} ${INDIA_MAP_HEIGHT}`}
        className="india-map-svg"
        style={{ maxHeight: height }}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label="India state-wise sales map"
        onWheel={handleWheel}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerLeave={handlePointerUp}
      >
        <g transform={`translate(${INDIA_MAP_WIDTH / 2 + pan.x} ${INDIA_MAP_HEIGHT / 2 + pan.y}) scale(${zoom}) translate(${-INDIA_MAP_WIDTH / 2} ${-INDIA_MAP_HEIGHT / 2})`}>
          {projected.features.map((feature) => {
            const ratio = projected.maxSales ? (feature.value?.sales ?? 0) / projected.maxSales : 0;
            const isSelected = selectedKey === feature.key;
            const matches = !query || feature.key.includes(query);
            const hasValue = Boolean(feature.value);
            const fill = !hasValue
              ? "#edf5ef"
              : mode === "heatmap"
                ? `rgba(193, 84, 32, ${(0.22 + ratio * 0.74).toFixed(3)})`
                : `rgba(30, 82, 51, ${(0.24 + ratio * 0.72).toFixed(3)})`;
            return mode === "bubble" ? null : (
              <path
                key={feature.key}
                d={feature.path}
                fill={fill}
                stroke={isSelected ? "#b8860b" : hovered === feature.key ? "#1e5233" : hasValue ? "#ffffff" : "#d4e2d8"}
                strokeWidth={isSelected ? 1.2 : hovered === feature.key ? 0.9 : hasValue ? 0.4 : 0.3}
                opacity={matches ? 1 : 0.28}
                onClick={() => onSelectRegion(isSelected ? "" : feature.name)}
                onMouseEnter={() => setHovered(feature.key)}
                onMouseLeave={() => setHovered("")}
                className={hasValue ? "india-map-state has-value" : "india-map-state no-value"}
                tabIndex={0}
                role="button"
                aria-label={`${feature.name}: ${feature.value ? formatCurrency(feature.value.sales) : "no mapped state data"}`}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelectRegion(isSelected ? "" : feature.name);
                  }
                }}
              >
                <title>{feature.value
                  ? `${feature.name} · ${formatCurrency(feature.value.sales)} sales · ${formatCurrency(feature.value.profit)} profit${typeof feature.value.margin === "number" ? ` · ${formatPercent(feature.value.margin * 100)} margin` : ""}`
                  : `${feature.name} · no data for this selection`}</title>
              </path>
            );
          })}

          {mode === "bubble" ? projected.features.map((feature) => {
            if (!feature.value) return null;
            const ratio = projected.maxSales ? feature.value.sales / projected.maxSales : 0;
            const isSelected = selectedKey === feature.key;
            const matches = !query || feature.key.includes(query);
            return (
              <g
                key={feature.key}
                opacity={matches ? 1 : 0.28}
                onClick={() => onSelectRegion(isSelected ? "" : feature.name)}
                className="india-map-bubble"
                role="button"
                tabIndex={0}
                aria-label={`${feature.name}: ${formatCurrency(feature.value.sales)}`}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelectRegion(isSelected ? "" : feature.name);
                  }
                }}
              >
                <circle
                  cx={feature.centroid[0]}
                  cy={feature.centroid[1]}
                  r={0.9 + Math.sqrt(Math.max(ratio, 0)) * 4.2}
                  fill={isSelected ? "#d9a41a" : "#1e5233"}
                  fillOpacity={0.62}
                  stroke="#ffffff"
                  strokeWidth={0.35}
                >
                  <title>{`${feature.name} · ${formatCurrency(feature.value.sales)} sales`}</title>
                </circle>
              </g>
            );
          }) : null}

          {labels.map((label) => (
            <text
              key={label.key}
              x={label.x}
              y={label.y}
              className="india-map-label"
              fontSize="2.3"
              fill="#173b2a"
              paintOrder="stroke"
              stroke="#ffffff"
              strokeWidth="0.5"
            >
              {label.text}
            </text>
          ))}
        </g>
      </svg>

      <div className="india-map-legend">
        <span className="india-map-legend-swatch" aria-hidden="true" />
        <span>{hasValues ? formatCompactCurrency(projected.minSales) : "No data"}</span>
        <i aria-hidden="true" />
        <span>{hasValues ? formatCompactCurrency(projected.maxSales) : "No data"}</span>
        <span className="india-map-legend-gap" />
        <span className="india-map-legend-nodata" aria-hidden="true" />
        <span>No data for this selection</span>
      </div>

      {mode === "bubble" ? <p className="india-map-note">Bubble anchors are area centroids calculated from the bundled state boundaries — they are not city coordinates.</p> : null}
      <p className="india-map-note">Zoom with +/− or the mouse wheel; drag to pan when zoomed. Select a state to cross-filter every chart on the page.</p>
    </div>
  );
}
