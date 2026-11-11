"use client";

/**
 * Interactive city bubble map.
 *
 * Only cities present in the active dataset are drawn, and only when the
 * bundled gazetteer has real coordinates for them.  Unknown cities are listed
 * separately rather than placed at an invented location.
 */

import { useMemo, useRef, useState, type PointerEvent as ReactPointerEvent, type WheelEvent as ReactWheelEvent } from "react";
import { findCityCoordinate, normaliseCity } from "@/lib/city-coordinates";
import { formatCompactCurrency, formatCurrency, formatPercent } from "@/lib/format";
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

const BOUNDS = { minLon: 68, maxLon: 97.5, minLat: 6.5, maxLat: 35.8 };
const VIEW_WIDTH = 100;
const VIEW_HEIGHT = 112;

function project(lon: number, lat: number): [number, number] {
  return [
    ((lon - BOUNDS.minLon) / (BOUNDS.maxLon - BOUNDS.minLon)) * VIEW_WIDTH,
    ((BOUNDS.maxLat - lat) / (BOUNDS.maxLat - BOUNDS.minLat)) * VIEW_HEIGHT,
  ];
}

export function CityBubbleMap({ cities, selectedCity = "", onSelectCity, height = 460, showSearch = true }: Props) {
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [search, setSearch] = useState("");
  const [hovered, setHovered] = useState("");
  const drag = useRef<{ pointerId: number; startX: number; startY: number; originX: number; originY: number } | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);

  const mapped = useMemo(() => {
    return cities
      .map((row) => {
        const coordinate = findCityCoordinate(String(row.city ?? ""));
        if (!coordinate) return null;
        const [x, y] = project(coordinate.lon, coordinate.lat);
        return { ...row, city: String(row.city), x, y, state: coordinate.state ?? "" };
      })
      .filter((row): row is NonNullable<typeof row> => row !== null);
  }, [cities]);

  const unmapped = useMemo(
    () => cities.filter((row) => !findCityCoordinate(String(row.city ?? ""))),
    [cities],
  );

  const maxSales = Math.max(...mapped.map((row) => Number(row.sales) || 0), 0);
  const query = normaliseCity(search);
  const selectedKey = normaliseCity(selectedCity);
  const topLabels = useMemo(
    () => new Set([...mapped].sort((left, right) => right.sales - left.sales).slice(0, 9).map((row) => normaliseCity(row.city))),
    [mapped],
  );

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
    const scaleX = VIEW_WIDTH / Math.max(rect.width, 1);
    const scaleY = VIEW_HEIGHT / Math.max(rect.height, 1);
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
        viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`}
        style={{ height }}
        role="img"
        aria-label="Interactive city sales bubble map of India"
        onWheel={handleWheel}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerLeave={handlePointerUp}
      >
        <g transform={`translate(${VIEW_WIDTH / 2 + pan.x} ${VIEW_HEIGHT / 2 + pan.y}) scale(${zoom}) translate(${-VIEW_WIDTH / 2} ${-VIEW_HEIGHT / 2})`}>
          <rect x="0" y="0" width={VIEW_WIDTH} height={VIEW_HEIGHT} fill="#f7fafd" rx="2" />
          {Array.from({ length: 7 }, (_, index) => BOUNDS.minLat + index * 5).map((lat) => {
            const [, y] = project(BOUNDS.minLon, lat);
            return <line key={`lat-${lat}`} x1="0" x2={VIEW_WIDTH} y1={y} y2={y} stroke="#e6edf6" strokeWidth="0.18" />;
          })}
          {Array.from({ length: 7 }, (_, index) => BOUNDS.minLon + index * 5).map((lon) => {
            const [x] = project(lon, BOUNDS.minLat);
            return <line key={`lon-${lon}`} x1={x} x2={x} y1="0" y2={VIEW_HEIGHT} stroke="#e6edf6" strokeWidth="0.18" />;
          })}
          <text x="74" y="14" fontSize="3.2" fill="#98a6ba" textAnchor="middle" aria-hidden="true">INDIA · CITY SALES</text>

          {[...mapped].sort((left, right) => left.sales - right.sales).map((row) => {
            const share = maxSales > 0 ? Number(row.sales) / maxSales : 0;
            const radius = 1.1 + Math.sqrt(Math.max(share, 0)) * 5.4;
            const isSelected = selectedKey === normaliseCity(row.city);
            const isHovered = normaliseCity(hovered) === normaliseCity(row.city);
            const matches = !query || normaliseCity(row.city).includes(query);
            const showLabel = isSelected || isHovered || topLabels.has(normaliseCity(row.city));
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
                  cx={row.x}
                  cy={row.y}
                  r={radius}
                  fill={isSelected ? "#d9a41a" : "#2f65a7"}
                  fillOpacity={isSelected ? 0.85 : 0.58}
                  stroke={isSelected ? "#8a6508" : "#ffffff"}
                  strokeWidth={isSelected ? 0.5 : 0.3}
                />
                <title>{`${row.city}${row.state ? `, ${row.state}` : ""}\nSales ${formatCurrency(row.sales)}\nProfit ${formatCurrency(row.profit)}${typeof row.margin === "number" ? `\nMargin ${formatPercent(row.margin * 100)}` : ""}`}</title>
                {showLabel ? (
                  <text x={row.x + radius * 0.7} y={row.y - radius * 0.7} fontSize="2.4" fill="#243b5a" paintOrder="stroke" stroke="#ffffff" strokeWidth="0.6">
                    {row.city}
                  </text>
                ) : null}
              </g>
            );
          })}
        </g>
      </svg>

      <div className="city-map-legend">
        <span><i className="city-map-dot city-map-dot-large" aria-hidden="true" /> Higher sales</span>
        <span><i className="city-map-dot" aria-hidden="true" /> Lower sales</span>
        <span>{mapped.length} of {cities.length} cities mapped</span>
      </div>
      <p className="city-map-note">
        Markers use the bundled city-coordinate gazetteer. Cities without known coordinates are listed below and are never placed at a guessed location.
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
