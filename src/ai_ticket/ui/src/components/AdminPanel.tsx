import React from "react";

type ThemeOption = "dark" | "light";

type AdminPanelProps = {
  open: boolean;
  onToggle: (open: boolean) => void;
  theme: ThemeOption;
  onThemeChange: (theme: ThemeOption) => void;
  streamPaused: boolean;
  onStreamPausedChange: (paused: boolean) => void;
  followLive: boolean;
  onFollowLiveChange: (follow: boolean) => void;
  reducedMotion: boolean;
  onReducedMotionChange: (value: boolean) => void;
  onRefresh: () => void;
};

const AdminPanel: React.FC<AdminPanelProps> = ({
  open,
  onToggle,
  theme,
  onThemeChange,
  streamPaused,
  onStreamPausedChange,
  followLive,
  onFollowLiveChange,
  reducedMotion,
  onReducedMotionChange,
  onRefresh,
}) => {
  return (
    <div className="admin-panel" data-open={open} data-testid="admin-panel">
      <header>
        <div>
          <span className="admin-pill">Admin</span>
          <h3>Operations Control Center</h3>
          <p>
            Quickly adjust real-time behaviour, theme preferences, and diagnostic helpers. Settings persist locally so you can
            pick up exactly where you left off.
          </p>
        </div>
        <button type="button" className="ghost-button" onClick={() => onToggle(!open)} data-testid="admin-panel-toggle">
          {open ? "Collapse" : "Expand"}
        </button>
      </header>
      {open && (
        <div className="admin-grid">
          <section aria-label="Realtime controls">
            <h4>Realtime controls</h4>
            <label className="toggle" data-testid="pause-stream-toggle">
              <input
                type="checkbox"
                checked={streamPaused}
                onChange={(event) => onStreamPausedChange(event.target.checked)}
              />
              <span>Pause incoming stream updates</span>
            </label>
            <label className="toggle">
              <input
                type="checkbox"
                checked={followLive}
                onChange={(event) => onFollowLiveChange(event.target.checked)}
              />
              <span>Auto-follow live snapshots</span>
            </label>
            <button type="button" className="ghost-button" onClick={onRefresh}>
              Trigger refresh
            </button>
          </section>
          <section aria-label="Theme preferences">
            <h4>Theme</h4>
            <div className="theme-switcher">
              <button
                type="button"
                className={`ghost-button ${theme === "dark" ? "active" : ""}`}
                onClick={() => onThemeChange("dark")}
                data-testid="theme-dark"
              >
                Dark
              </button>
              <button
                type="button"
                className={`ghost-button ${theme === "light" ? "active" : ""}`}
                onClick={() => onThemeChange("light")}
                data-testid="theme-light"
              >
                Light
              </button>
            </div>
            <label className="toggle" data-testid="reduced-motion-toggle">
              <input
                type="checkbox"
                checked={reducedMotion}
                onChange={(event) => onReducedMotionChange(event.target.checked)}
              />
              <span>Reduce animations</span>
            </label>
          </section>
          <section aria-label="Shortcuts quick reference" className="admin-shortcuts">
            <h4>Quick shortcuts</h4>
            <ul>
              <li><strong>Shift + /</strong> — Toggle shortcut overlay</li>
              <li><strong>R</strong> — Refresh metrics</li>
              <li><strong>[</strong> / <strong>]</strong> — Step through history</li>
              <li><strong>Ctrl + .</strong> — Toggle this panel</li>
            </ul>
          </section>
        </div>
      )}
    </div>
  );
};

export default AdminPanel;
