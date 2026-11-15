"use client";

/**
 * Interactive city bubble map.
 *
 * Only cities present in the active dataset are drawn, and only when the
 * bundled gazetteer has real coordinates for them.  Unknown cities are listed
 * separately rather than placed at an invented location.  The state outline
 * underneath comes from the same bundled GeoJSON used by the India map, so a
 * bubble always sits inside the correct boundary.
 */

import { useMemo, useRef, useState, type PointerEvent as ReactPointerEvent, type WheelEvent as ReactWheelEvent } from "react";
import useSWR from "swr";
import { findCityCoordinate, normaliseCity } from "@/lib/city-coordinates";
import { formatCompactCurrency, formatCurrency, formatPercent } from "@/lib/format";
import {
  fetchIndiaGeography,
  INDIA_GEO_URL,
  INDIA_MAP_HEIGHT,
  INDIA_MAP_WIDTH,
  pathFor,
  projectIndia,
  type IndiaGeo,
  type Position,
} from "@/lib/india-geo";
import { Button } from "@/components/ui/button";

export type CityMapDatum = {
  city: string;
  sales: number;
  profit: number;
  margin?: number | null;
};

type Props = {
  cities: CityMapDatum[];
  selectedCity?: string;
  onSelectCity?: (city: string) => void;
  height?: number;
  showSearch?: boolean;
};

type Box = { x: number; y: number; width: number; height: number };

function intersects(left: Box, right: Box): boolean {
  return !(
    left.x + left.width < right.x ||
    right.x + right.width < left.x ||
    left.y + left.height < right.y ||
    right.y + right.height < left.y
  );
}

type LabelEntry = { key: string; text: string; point: Position; radius: number; priority: number };

/** Greedy, collision-aware label placement. A label is dropped rather than overlapped. */
function placeLabels(entries: LabelEntry[]): { key: string; text: string; x: number; y: number }[] {
  const font = 2.5;
  const occupied: Box[] = [];
  const accepted: { key: string; text: string; x: number; y: number }[] = [];

  for (const entry of entries) {
    const width = Math.min(entry.text.length * font * 0.56, 24);
    const circle: Box = {
      x: entry.point[0] - entry.radius,
      y: entry.point[1] - entry.radius,
      width: entry.radius * 2,
      height: entry.radius * 2,
    };
    // The marker itself is an obstacle for every other label.
    if (!occupied.some((other) => other.x === circle.x && other.y === circle.y && other.width === circle.width)) {
      occupied.push(circle);
    }
    const candidates: Position[] = [
      [entry.point[0] + entry.radius + 0.8, entry.point[1] - entry.radius - 0.6],
      [entry.point[0] + entry.radius + 0.8, entry.point[1] + entry.radius + 2.4],
      [entry.point[0] - width - entry.radius - 0.8, entry.point[1] - entry.radius - 0.6],
      [entry.point[0] - width / 2, entry.point[1] - entry.radius - 1.8],
      [entry.point[0] - width / 2, entry.point[1] + entry.radius + 3.1],
    ];
    for (const [x, y] of candidates) {
      const box: Box = { x, y: y - font, width, height: font + 0.6 };
      const inBounds = x > 0 && x + width < INDIA_MAP_WIDTH && y > font && y < INDIA_MAP_HEIGHT;
      if (!inBounds) continue;
      if (occupied.some((other) => intersects(box, other))) continue;
      occupied.push(box);
      accepted.push({ key: entry.key, text: entry.text, x, y });
      break;
    }
  }
  return accepted;
}

export function CityBubbleMap({ cities, selectedCity = "", onSelectCity, height = 560, showSearch = true }: Props) {
  const { data: geography } = useSWR<IndiaGeo>(INDIA_GEO_URL, fetchIndiaGeography);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [search, setSearch] = useState("");
  const [hovered, setHovered] = useState("");
  const drag = useRef<{ pointerId: number; startX: number; startY: number; originX: number; originY: number } | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);

  const outline = useMemo(() => {
    if (!geography?.features?.length) return [];
    return geography.features.map((feature) => ({ key: String(feature.properties.name ?? feature.properties["hc-key"]), path: pathFor(feature) }));
  }, [geography]);

  const mapped = useMemo(() => {
    return cities
      .map((row) => {
        const coordinate = findCityCoordinate(String(row.city ?? ""));
        if (!coordinate) return null;
        const point = projectIndia(coordinate.lon, coordinate.lat);
        return { ...row, city: String(row.city), point, state: coordinate.state ?? "" };
      })
      .filter((row): row is NonNullable<typeof row> => row !== null);
  }, [cities]);

  const unmapped = useMemo(
    () => cities.filter((row) => !findCityCoordinate(String(row.city ?? ""))),
    [cities],
  );

  const maxSales = Math.max(...mapped.map((row) => Number(row.sales) || 0), 0);
  const minSales = Math.min(...mapped.map((row) => Number(row.sales) || 0), maxSales);
  const query = normaliseCity(search);
  const selectedKey = normaliseCity(selectedCity);

  const radii = useMemo(() => {
    return new Map(mapped.map((row) => {
      const share = maxSales > 0 ? Math.max(Number(row.sales) || 0, 0) / maxSales : 0;
      return [normaliseCity(row.city), 1.2 + Math.sqrt(share) * 4.6] as const;
    }));
  }, [mapped, maxSales]);

  const labels = useMemo(() => {
    const matches = mapped.filter((row) => !query || normaliseCity(row.city).includes(query));
    const ranked = [...matches].sort((left, right) => {
      const leftSelected = selectedKey === normaliseCity(left.city);
      const rightSelected = selectedKey === normaliseCity(right.city);
      if (leftSelected !== rightSelected) return leftSelected ? -1 : 1;
      const leftHovered = normaliseCity(hovered) === normaliseCity(left.city);
      const rightHovered = normaliseCity(hovered) === normaliseCity(right.city);
      if (leftHovered !== rightHovered) return leftHovered ? -1 : 1;
      return Number(right.sales) - Number(left.sales);
    }).slice(0, 14);
    return placeLabels(ranked.map((row) => ({
      key: row.city,
      text: row.city,
      point: row.point,
      radius: radii.get(normaliseCity(row.city)) ?? 1.2,
      priority: Number(row.sales),
    })));
  }, [hovered, mapped, query, radii, selectedKey]);

  function handleWheel(event: ReactWheelEvent<SVGSVGElement>) {
    event.preventDefault();
    setZoom((current) => Math.min(5, Math.max(1, current - event.deltaY * 0.0015)));
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

  if (!cities.length) {
    return <p className="city-map-empty">No city values are available for the active filters.</p>;
  }

  return (
    <div className="city-map">
      <div className="city-map-toolbar">
        {showSearch ? (
          <label className="city-map-search">
            <span>Search city</span>
            <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="e.g. Surat" />
          </label>
        ) : <span />}
        <div className="city-map-zoom">
          <Button type="button" size="sm" variant="outline" onClick={() => setZoom((current) => Math.min(5, current + 0.25))} aria-label="Zoom in">+</Button>
          <Button type="button" size="sm" variant="outline" onClick={() => setZoom((current) => Math.max(1, current - 0.25))} aria-label="Zoom out">−</Button>
          <Button type="button" size="sm" variant="outline" onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }}>Reset</Button>
        </div>
      </div>

      <svg
        ref={svgRef}
        className="city-map-svg"
        viewBox={`0 0 ${INDIA_MAP_WIDTH} ${INDIA_MAP_HEIGHT}`}
        style={{ maxHeight: height }}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label="Interactive city sales bubble map of India"
        onWheel={handleWheel}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerLeave={handlePointerUp}
      >
        <g transform={`translate(${INDIA_MAP_WIDTH / 2 + pan.x} ${INDIA_MAP_HEIGHT / 2 + pan.y}) scale(${zoom}) translate(${-INDIA_MAP_WIDTH / 2} ${-INDIA_MAP_HEIGHT / 2})`}>
          <rect x="0" y="0" width={INDIA_MAP_WIDTH} height={INDIA_MAP_HEIGHT} fill="#f7fbf8" rx="2" />
          {outline.map((state) => (
            <path key={state.key} d={state.path} fill="#e9f2ec" stroke="#c3d8c9" strokeWidth="0.22" aria-hidden="true" />
          ))}

          {[...mapped].sort((left, right) => Number(left.sales) - Number(right.sales)).map((row) => {
            const radius = radii.get(normaliseCity(row.city)) ?? 1.2;
            const isSelected = selectedKey === normaliseCity(row.city);
            const isHovered = normaliseCity(hovered) === normaliseCity(row.city);
            const matches = !query || normaliseCity(row.city).includes(query);
            return (
              <g
                key={row.city}
                className="city-map-marker"
                opacity={matches ? 1 : 0.24}
                role="button"
                tabIndex={0}
                aria-label={`${row.city}: ${formatCurrency(row.sales)} sales`}
                onClick={() => onSelectCity?.(isSelected ? "" : row.city)}
                onMouseEnter={() => setHovered(row.city)}
                onMouseLeave={() => setHovered("")}
                onFocus={() => setHovered(row.city)}
                onBlur={() => setHovered("")}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelectCity?.(isSelected ? "" : row.city);
                  }
                }}
              >
                <circle
                  cx={row.point[0]}
                  cy={row.point[1]}
                  r={isSelected || isHovered ? radius + 0.35 : radius}
                  fill={isSelected ? "#d9a41a" : "#1e5233"}
                  fillOpacity={isSelected ? 0.85 : 0.6}
                  stroke={isSelected ? "#8a6508" : "#ffffff"}
                  strokeWidth={isSelected ? 0.5 : 0.3}
                />
                <title>{`${row.city}${row.state ? `, ${row.state}` : ""}\nSales ${formatCurrency(row.sales)}\nProfit ${formatCurrency(row.profit)}${typeof row.margin === "number" ? `\nMargin ${formatPercent(row.margin * 100)}` : ""}`}</title>
              </g>
            );
          })}

          {labels.map((label) => (
            <text
              key={label.key}
              x={label.x}
              y={label.y}
              className="city-map-label"
              fontSize="2.5"
              fill="#173b2a"
              paintOrder="stroke"
              stroke="#ffffff"
              strokeWidth="0.55"
            >
              {label.text}
            </text>
          ))}
        </g>
      </svg>

      <div className="city-map-legend">
        <span><i className="city-map-dot city-map-dot-large" aria-hidden="true" /> {maxSales ? formatCompactCurrency(maxSales) : "No sales"}</span>
        <span><i className="city-map-dot" aria-hidden="true" /> {mapped.length ? formatCompactCurrency(minSales) : "No sales"}</span>
        <span>{mapped.length} of {cities.length} cities mapped</span>
      </div>
      <p className="city-map-note">
        Bubble size is proportional to observed sales. Positions come only from the bundled city-coordinate gazetteer; cities without known coordinates are listed below and are never placed at a guessed location.
      </p>
      {unmapped.length ? (
        <div className="city-map-unmapped" aria-label="Cities without coordinates">
          <strong>No coordinates available</strong>
          <div>{unmapped.map((row) => <span key={row.city}>{row.city}<em>{formatCompactCurrency(row.sales)}</em></span>)}</div>
        </div>
      ) : null}
    </div>
  );
}
