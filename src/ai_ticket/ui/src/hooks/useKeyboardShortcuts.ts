import { useEffect, useMemo, useRef } from "react";

type ShortcutConfig = Record<string, () => void>;

type ShortcutPart = {
  key: string;
  modifiers: Set<string>;
};

type NormalizedShortcut = {
  sequence: ShortcutPart[];
  callback: () => void;
};

const SEQUENCE_TIMEOUT_MS = 1000;

const normaliseModifier = (modifier: string): string => {
  switch (modifier) {
    case "cmd":
    case "command":
      return "meta";
    case "control":
      return "ctrl";
    case "option":
      return "alt";
    default:
      return modifier;
  }
};

const parseShortcut = (combo: string, callback: () => void): NormalizedShortcut => {
  const parts = combo
    .split(/\s+/)
    .filter(Boolean)
    .map((segment) => {
      const tokens = segment
        .split("+")
        .map((token) => token.trim().toLowerCase())
        .filter(Boolean);
      const key = tokens.pop() ?? "";
      const modifiers = new Set<string>();
      tokens.forEach((token) => {
        modifiers.add(normaliseModifier(token));
      });
      return { key, modifiers };
    });
  return { sequence: parts, callback };
};

const matchesPart = (part: ShortcutPart, event: KeyboardEvent): boolean => {
  const eventKey = event.key.length === 1 ? event.key.toLowerCase() : event.key.toLowerCase();
  const targetKey = part.key;

  const requireMod = part.modifiers.has("mod");
  const modifiers = new Set([...part.modifiers].filter((modifier) => modifier !== "mod"));

  const active = {
    shift: event.shiftKey,
    ctrl: event.ctrlKey,
    alt: event.altKey,
    meta: event.metaKey,
  } as const;

  if (requireMod) {
    if (!event.metaKey && !event.ctrlKey) {
      return false;
    }
  }

  for (const [modifier, isActive] of Object.entries(active)) {
    const normalised = modifier as keyof typeof active;
    const required = modifiers.has(normalised);
    if (required && !isActive) {
      return false;
    }
    if (!required && isActive) {
      if (!(requireMod && (normalised === "ctrl" || normalised === "meta"))) {
        return false;
      }
    }
  }

  if (eventKey === targetKey) {
    return true;
  }
  if (targetKey === "/" && modifiers.has("shift") && eventKey === "?") {
    return true;
  }
  return false;
};

export const useKeyboardShortcuts = (config: ShortcutConfig) => {
  const shortcuts = useMemo<NormalizedShortcut[]>(
    () =>
      Object.entries(config).map(([combo, callback]) =>
        parseShortcut(combo.trim().toLowerCase(), callback)
      ),
    [config]
  );

  const progressRef = useRef<{ shortcut: NormalizedShortcut; index: number; timestamp: number }[]>([]);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) {
        return;
      }

      const now = Date.now();
      progressRef.current = progressRef.current.filter((state) => now - state.timestamp <= SEQUENCE_TIMEOUT_MS);

      const triggered: NormalizedShortcut[] = [];
      const nextProgress: typeof progressRef.current = [];

      for (const shortcut of shortcuts) {
        const firstPart = shortcut.sequence[0];
        if (!firstPart) {
          continue;
        }
        if (matchesPart(firstPart, event)) {
          if (shortcut.sequence.length === 1) {
            triggered.push(shortcut);
          } else {
            nextProgress.push({ shortcut, index: 1, timestamp: now });
          }
        }
      }

      for (const state of progressRef.current) {
        const part = state.shortcut.sequence[state.index];
        if (part && matchesPart(part, event)) {
          if (state.index + 1 === state.shortcut.sequence.length) {
            triggered.push(state.shortcut);
          } else {
            nextProgress.push({ shortcut: state.shortcut, index: state.index + 1, timestamp: now });
          }
        }
      }

      progressRef.current = nextProgress;

      if (triggered.length > 0) {
        event.preventDefault();
        triggered[0].callback();
        progressRef.current = [];
      }
    };

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [shortcuts]);
};
