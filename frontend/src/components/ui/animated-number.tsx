"use client";

import { useEffect, useRef, useState } from "react";
import { useAnimationPreference } from "@/lib/animation-preference";

function easeOutCubic(progress: number) {
  return 1 - Math.pow(1 - progress, 3);
}

/**
 * Animated KPI counter. Animates from the previously displayed value to the new
 * one using requestAnimationFrame. When motion is disabled (system preference or
 * the in-app toggle) the final value is rendered immediately.
 */
export function AnimatedNumber({
  value,
  format,
  duration = 900,
  className,
  ariaLabel,
}: {
  value: number | null | undefined;
  format: (value: number) => string;
  duration?: number;
  className?: string;
  ariaLabel?: string;
}) {
  const { animationsActive } = useAnimationPreference();
  const [display, setDisplay] = useState(0);
  const currentRef = useRef(0);
  const frameRef = useRef<number | null>(null);

  useEffect(() => {
    const numeric = typeof value === "number" && Number.isFinite(value) ? value : null;
    if (numeric === null) {
      currentRef.current = 0;
      const raf = requestAnimationFrame(() => setDisplay(0));
      return () => cancelAnimationFrame(raf);
    }
    if (!animationsActive) {
      // Show the value instantly while motion is off, but keep the animation
      // origin at zero so enabling animations later produces a counter roll-up.
      currentRef.current = 0;
      const raf = requestAnimationFrame(() => setDisplay(numeric));
      return () => cancelAnimationFrame(raf);
    }
    const from = currentRef.current;
    if (from === numeric) {
      const raf = requestAnimationFrame(() => setDisplay(numeric));
      return () => cancelAnimationFrame(raf);
    }
    const startedAt = performance.now();
    const step = (now: number) => {
      const progress = Math.min(1, (now - startedAt) / duration);
      const next = from + (numeric - from) * easeOutCubic(progress);
      currentRef.current = next;
      setDisplay(next);
      if (progress < 1) {
        frameRef.current = requestAnimationFrame(step);
      } else {
        currentRef.current = numeric;
        setDisplay(numeric);
      }
    };
    frameRef.current = requestAnimationFrame(step);
    return () => {
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    };
  }, [animationsActive, duration, value]);

  const numeric = typeof value === "number" && Number.isFinite(value) ? value : null;
  const finalLabel = numeric === null ? "—" : format(numeric);
  return (
    <span className={className} aria-label={ariaLabel ?? finalLabel}>
      <span aria-hidden="true">{numeric === null ? "—" : format(display)}</span>
    </span>
  );
}
