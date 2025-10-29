import { useEffect, useMemo } from "https://esm.sh/react@18.2.0";

const normalizeKey = (key) => key.toLowerCase();

const parseShortcut = (combo) => {
  const tokens = combo
    .split("+")
    .map((token) => token.trim().toLowerCase())
    .filter(Boolean);

  if (tokens.length === 0) {
    return null;
  }

  const descriptor = {
    key: normalizeKey(tokens[tokens.length - 1]),
    shift: false,
    alt: false,
    ctrl: false,
    meta: false,
  };

  for (let index = 0; index < tokens.length - 1; index += 1) {
    const token = tokens[index];
    if (token === "shift") {
      descriptor.shift = true;
    } else if (token === "alt" || token === "option") {
      descriptor.alt = true;
    } else if (token === "ctrl" || token === "control") {
      descriptor.ctrl = true;
    } else if (token === "meta" || token === "cmd" || token === "command") {
      descriptor.meta = true;
    }
  }

  return descriptor;
};

const targetIsEditable = (target) => {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  return target.isContentEditable || target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT";
};

export const useKeyboardShortcuts = (config) => {
  const shortcuts = useMemo(() => {
    return Object.entries(config)
      .map(([combo, handler]) => {
        const descriptor = parseShortcut(combo);
        if (!descriptor) {
          return null;
        }
        return { descriptor, handler };
      })
      .filter(Boolean);
  }, [config]);

  useEffect(() => {
    if (shortcuts.length === 0) {
      return;
    }

    const handler = (event) => {
      if (event.defaultPrevented || targetIsEditable(event.target)) {
        return;
      }

      const eventKey = normalizeKey(event.key);
      const match = shortcuts.find(({ descriptor }) => {
        if (descriptor.shift !== event.shiftKey) {
          return false;
        }
        if (descriptor.alt !== event.altKey) {
          return false;
        }
        if (descriptor.ctrl !== event.ctrlKey) {
          return false;
        }
        if (descriptor.meta !== event.metaKey) {
          return false;
        }
        return descriptor.key === eventKey;
      });

      if (match) {
        event.preventDefault();
        match.handler();
      }
    };

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [shortcuts]);
};
