import React, { useEffect, useMemo, useState } from "react";
import MetricsPanel from "./components/MetricsPanel";
import StatusGrid from "./components/StatusGrid";
import HueSlider from "./components/HueSlider";
import HistoryExplorer from "./components/HistoryExplorer";
import AdminPanel from "./components/AdminPanel";
import ShortcutOverlay from "./components/ShortcutOverlay";
import { useMetricsStream } from "./hooks/useMetricsStream";
import { useKeyboardShortcuts } from "./hooks/useKeyboardShortcuts";
import { useLocalStorageState } from "./hooks/useLocalStorageState";
import logoUrl from "./assets/logo.svg";
import type { MetricsSnapshot } from "./types";

type ThemeOption = "dark" | "light";

const HISTORY_LIMIT = 60;

const App: React.FC = () => {
  const [hue, setHue] = useLocalStorageState<number>("dashboard-hue", 210);
  const [theme, setTheme] = useLocalStorageState<ThemeOption>("dashboard-theme", "dark");
  const [adminOpen, setAdminOpen] = useLocalStorageState<boolean>("dashboard-admin-open", false);
  const [followLive, setFollowLive] = useLocalStorageState<boolean>("dashboard-follow-live", true);
  const [streamPaused, setStreamPaused] = useLocalStorageState<boolean>("dashboard-stream-paused", false);
  const [reducedMotion, setReducedMotion] = useLocalStorageState<boolean>("dashboard-reduced-motion", false);
  const [selectedTimestamp, setSelectedTimestamp] = useLocalStorageState<string | null>("dashboard-history-selection", null);
  const [shortcutOverlayOpen, setShortcutOverlayOpen] = useState(false);

  const { metrics, refresh } = useMetricsStream({ paused: streamPaused });
  const [history, setHistory] = useState<MetricsSnapshot[]>([]);

  useEffect(() => {
    setHistory((previous) => {
      if (previous.length > 0 && previous[previous.length - 1].timestamp === metrics.timestamp) {
        return previous;
      }
      const next = [...previous, metrics];
      if (next.length > HISTORY_LIMIT) {
        return next.slice(next.length - HISTORY_LIMIT);
      }
      return next;
    });
  }, [metrics]);

  useEffect(() => {
    document.documentElement.style.setProperty("--accent-hue", hue.toString());
  }, [hue]);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  useEffect(() => {
    document.documentElement.setAttribute("data-reduced-motion", reducedMotion ? "true" : "false");
  }, [reducedMotion]);

  useEffect(() => {
    if (followLive) {
      setSelectedTimestamp(null);
    }
  }, [followLive, metrics.timestamp, setSelectedTimestamp]);

  const activeSnapshot = useMemo(() => {
    if (!selectedTimestamp) {
      return metrics;
    }
    return history.find((snapshot) => snapshot.timestamp === selectedTimestamp) ?? metrics;
  }, [selectedTimestamp, history, metrics]);

  const isLive = !selectedTimestamp || selectedTimestamp === metrics.timestamp;

  const selectTimestamp = (timestamp: string | null) => {
    if (timestamp === null) {
      setSelectedTimestamp(null);
      return;
    }
    setFollowLive(false);
    setSelectedTimestamp(timestamp);
  };

  const stepHistory = (delta: number) => {
    if (history.length === 0) {
      return;
    }
    const currentIndex = isLive
      ? history.length - 1
      : history.findIndex((snapshot) => snapshot.timestamp === selectedTimestamp);
    const safeIndex = currentIndex === -1 ? history.length - 1 : currentIndex;
    const targetIndex = Math.min(history.length - 1, Math.max(0, safeIndex + delta));
    const target = history[targetIndex];
    if (!target) {
      return;
    }
    if (targetIndex === history.length - 1) {
      setSelectedTimestamp(null);
      setFollowLive(true);
    } else {
      setFollowLive(false);
      setSelectedTimestamp(target.timestamp);
    }
  };

  const jumpToLive = () => {
    setFollowLive(true);
    setSelectedTimestamp(null);
  };

  const shortcutSections = useMemo(
    () => [
      {
        title: "Navigation",
        shortcuts: [
          { combo: "Shift + /", description: "Toggle shortcut overlay" },
          { combo: "Ctrl + .", description: "Toggle admin panel" },
          { combo: "Escape", description: "Close overlays" },
        ],
      },
      {
        title: "Realtime",
        shortcuts: [
          { combo: "R", description: "Refresh metrics" },
          { combo: "H", description: "Shift accent hue forward" },
          { combo: "Shift + H", description: "Shift accent hue backward" },
        ],
      },
      {
        title: "History explorer",
        shortcuts: [
          { combo: "[", description: "Step backward in history" },
          { combo: "]", description: "Step forward in history" },
          { combo: "Arrow Keys", description: "Navigate snapshots" },
        ],
      },
    ],
    []
  );

  useKeyboardShortcuts({
    "?": () => setShortcutOverlayOpen((open) => !open),
    "shift+/": () => setShortcutOverlayOpen((open) => !open),
    escape: () => setShortcutOverlayOpen(false),
    r: () => refresh(),
    h: () => setHue((value) => (value + 10) % 360),
    "shift+h": () => setHue((value) => (value - 10 + 360) % 360),
    "[": () => stepHistory(-1),
    "]": () => stepHistory(1),
    arrowleft: () => stepHistory(-1),
    arrowright: () => stepHistory(1),
    "ctrl+.": () => setAdminOpen((value) => !value),
    "meta+.": () => setAdminOpen((value) => !value),
  });

  const metricsView = useMemo(() => activeSnapshot, [activeSnapshot]);

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="branding">
          <img src={logoUrl} alt="AI Ticket" />
          <h1>AI Ticket Operations</h1>
        </div>
        <div className="controls-bar">
          <HueSlider value={hue} onChange={setHue} />
          <span className="shortcuts-hint">Press ⇧ / for shortcuts</span>
        </div>
      </header>
      <main className="app-content">
        <section className="panel" aria-label="Key metrics">
          <h2>Realtime Metrics</h2>
          <MetricsPanel metrics={metricsView} />
        </section>
        <section className="panel" aria-label="System status">
          <h2>System Status</h2>
          <StatusGrid statuses={metricsView.statusPanels} lastUpdated={metricsView.timestamp} />
        </section>
        <section className="panel" aria-label="Error activity">
          <h2>Recent Errors</h2>
          {metricsView.recentErrors.length === 0 ? (
            <p>No errors reported in the last 15 minutes.</p>
          ) : (
            <ul>
              {metricsView.recentErrors.map((error) => (
                <li key={error.id}>
                  <strong>{error.code}</strong> &mdash; {error.message} ({new Date(error.timestamp).toLocaleTimeString()})
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className="panel" aria-label="History explorer">
          <h2>History Explorer</h2>
          <HistoryExplorer
            history={history}
            activeSnapshot={activeSnapshot}
            selectedTimestamp={selectedTimestamp}
            onSelectTimestamp={selectTimestamp}
            onStepBackward={() => stepHistory(-1)}
            onStepForward={() => stepHistory(1)}
            isLive={isLive}
            followLive={followLive}
            onFollowLiveChange={setFollowLive}
            onJumpToLive={jumpToLive}
          />
        </section>
        <section className="panel" aria-label="Admin panel" data-testid="admin-panel-section">
          <h2>Admin Panel</h2>
          <AdminPanel
            open={adminOpen}
            onToggle={setAdminOpen}
            theme={theme}
            onThemeChange={setTheme}
            streamPaused={streamPaused}
            onStreamPausedChange={setStreamPaused}
            followLive={followLive}
            onFollowLiveChange={setFollowLive}
            reducedMotion={reducedMotion}
            onReducedMotionChange={setReducedMotion}
            onRefresh={refresh}
          />
        </section>
      </main>
      {shortcutOverlayOpen && <ShortcutOverlay sections={shortcutSections} onClose={() => setShortcutOverlayOpen(false)} />}
    </div>
  );
};

export default App;
