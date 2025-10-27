import { useEffect } from "react";

type ShortcutConfig = Record<string, () => void>;

export const useKeyboardShortcuts = (config: ShortcutConfig) => {
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) {
        return;
      }

      const key = event.key.toLowerCase();
      const normalizedEntries = Object.entries(config).map(([combo, callback]) => [combo.toLowerCase(), callback] as const);
      const match = normalizedEntries.find(([combo]) => combo === key);

      if (match) {
        event.preventDefault();
        match[1]();
      }
    };

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [config]);
};
