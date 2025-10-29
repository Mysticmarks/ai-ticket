import React from "react";

type Shortcut = {
  combo: string;
  description: string;
};

type ShortcutSection = {
  title: string;
  shortcuts: Shortcut[];
};

type ShortcutOverlayProps = {
  sections: ShortcutSection[];
  onClose: () => void;
};

const ShortcutOverlay: React.FC<ShortcutOverlayProps> = ({ sections, onClose }) => {
  return (
    <div className="shortcut-overlay" role="dialog" aria-modal="true" aria-label="Keyboard shortcuts" data-testid="shortcut-overlay">
      <div className="shortcut-surface">
        <header className="shortcut-header">
          <h3>Keyboard Shortcuts</h3>
          <button type="button" onClick={onClose} className="ghost-button">
            Close
          </button>
        </header>
        <div className="shortcut-grid">
          {sections.map((section) => (
            <section key={section.title} aria-label={section.title} className="shortcut-section">
              <h4>{section.title}</h4>
              <dl>
                {section.shortcuts.map((shortcut) => (
                  <React.Fragment key={shortcut.combo}>
                    <dt>{shortcut.combo}</dt>
                    <dd>{shortcut.description}</dd>
                  </React.Fragment>
                ))}
              </dl>
            </section>
          ))}
        </div>
        <footer className="shortcut-footer">
          <p>
            Preferences are stored locally, so your shortcuts, theme, and viewing options persist the next time you visit the
            dashboard.
          </p>
        </footer>
      </div>
    </div>
  );
};

export default ShortcutOverlay;
