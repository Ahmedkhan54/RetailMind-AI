"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { useReducedMotion } from "@/lib/use-reduced-motion";

const STORAGE_KEY = "retailmind_charts_animate";
const listeners = new Set<() => void>();

function readStoredPreference(): boolean {
  if (typeof window === "undefined") return true;
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "false") return false;
    if (stored === "true") return true;
  } catch {
    /* localStorage can be unavailable in private modes; keep the default. */
  }
  return true;
}

function subscribe(onChange: () => void) {
  listeners.add(onChange);
  const onStorage = (event: StorageEvent) => {
    if (event.key === STORAGE_KEY) onChange();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(onChange);
    window.removeEventListener("storage", onStorage);
  };
}

function getSnapshot() {
  return readStoredPreference();
}

function getServerSnapshot() {
  return true;
}

type AnimationPreferenceValue = {
  /** The user's explicit preference (defaults to on). */
  enabled: boolean;
  /** Whether the operating system asks for reduced motion. */
  systemReducedMotion: boolean;
  /** Effective flag for charts and counters: enabled AND not reduced. */
  animationsActive: boolean;
  setEnabled: (value: boolean) => void;
  toggle: () => void;
};

const AnimationPreferenceContext = createContext<AnimationPreferenceValue | null>(null);

const FALLBACK: AnimationPreferenceValue = {
  enabled: false,
  systemReducedMotion: true,
  animationsActive: false,
  setEnabled: () => {},
  toggle: () => {},
};

export function AnimationPreferenceProvider({ children }: { children: ReactNode }) {
  const systemReducedMotion = useReducedMotion();
  const enabled = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  const setEnabled = useCallback((value: boolean) => {
    try {
      window.localStorage.setItem(STORAGE_KEY, String(value));
    } catch {
      /* Ignore persistence failures; notify listeners so the UI still updates. */
    }
    listeners.forEach((listener) => listener());
  }, []);

  const value = useMemo<AnimationPreferenceValue>(() => ({
    enabled,
    systemReducedMotion,
    animationsActive: enabled && !systemReducedMotion,
    setEnabled,
    toggle: () => setEnabled(!enabled),
  }), [enabled, setEnabled, systemReducedMotion]);

  return <AnimationPreferenceContext.Provider value={value}>{children}</AnimationPreferenceContext.Provider>;
}

export function useAnimationPreference(): AnimationPreferenceValue {
  return useContext(AnimationPreferenceContext) ?? FALLBACK;
}

/**
 * Consistent native Recharts animation props for every chart in the app.
 * No extra animation dependency is added.
 */
export function useChartAnimation() {
  const { animationsActive } = useAnimationPreference();
  return {
    isAnimationActive: animationsActive,
    animationDuration: 720,
    animationEasing: "ease-out" as const,
  };
}
