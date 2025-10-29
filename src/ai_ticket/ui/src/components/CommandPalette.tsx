import React, { useEffect, useMemo, useRef, useState } from "react";

type CommandAction = {
  id: string;
  title: string;
  description?: string;
  shortcut?: string;
  onSelect: () => void;
};

type CommandPaletteProps = {
  open: boolean;
  onClose: () => void;
  actions: CommandAction[];
};

const CommandPalette: React.FC<CommandPaletteProps> = ({ open, onClose, actions }) => {
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (open && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
    if (!open) {
      setQuery("");
    }
  }, [open]);

  useEffect(() => {
    if (!open) {
      return;
    }
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  const filtered = useMemo(() => {
    const trimmed = query.trim().toLowerCase();
    if (!trimmed) {
      return actions;
    }
    return actions.filter((action) => {
      return (
        action.title.toLowerCase().includes(trimmed) ||
        (action.description && action.description.toLowerCase().includes(trimmed)) ||
        (action.shortcut && action.shortcut.toLowerCase().includes(trimmed))
      );
    });
  }, [actions, query]);

  const handleSelect = (action: CommandAction) => {
    action.onSelect();
    onClose();
    setQuery("");
  };

  if (!open) {
    return null;
  }

  return (
    <div className="command-palette-backdrop" role="dialog" aria-modal="true" aria-label="Command palette">
      <div className="command-palette">
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Type a command or search…"
          aria-label="Command search"
        />
        <ul className="command-list" role="listbox">
          {filtered.length === 0 ? (
            <li className="command-list-empty">No matching actions.</li>
          ) : (
            filtered.map((action) => (
              <li key={action.id}>
                <button type="button" onClick={() => handleSelect(action)}>
                  <div className="command-list-meta">
                    <div className="command-list-title">{action.title}</div>
                    {action.description && <div className="command-list-description">{action.description}</div>}
                  </div>
                  {action.shortcut && <span className="command-list-shortcut">{action.shortcut}</span>}
                </button>
              </li>
            ))
          )}
        </ul>
      </div>
    </div>
  );
};

export type { CommandAction };
export default CommandPalette;
