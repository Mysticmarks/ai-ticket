import React, { useEffect, useMemo, useState } from "react";
import MetricsPanel from "./components/MetricsPanel";
import StatusGrid from "./components/StatusGrid";
import HueSlider from "./components/HueSlider";
import HelpDialog from "./components/HelpDialog";
import CommandPalette, { CommandAction } from "./components/CommandPalette";
import { useMetricsStream } from "./hooks/useMetricsStream";
import { useKeyboardShortcuts } from "./hooks/useKeyboardShortcuts";
import logoUrl from "./assets/logo.svg";

const App: React.FC = () => {
  const { metrics, refresh } = useMetricsStream();
  const [hue, setHue] = useState<number>(() => Number(localStorage.getItem("dashboard-hue")) || 210);
  const [helpOpen, setHelpOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [activeView, setActiveView] = useState<"home" | "prompts" | "config">("home");

  useEffect(() => {
    document.documentElement.style.setProperty("--accent-hue", hue.toString());
    localStorage.setItem("dashboard-hue", hue.toString());
  }, [hue]);

  const shortcuts = useMemo(
    () => ({
      "shift+/": () => setHelpOpen((value) => !value),
      "mod+k": () => setPaletteOpen(true),
      escape: () => {
        setHelpOpen(false);
        setPaletteOpen(false);
      },
      r: () => refresh(),
      h: () => setHue((value) => (value + 10) % 360),
      "g h": () => setActiveView("home"),
      "g p": () => setActiveView("prompts"),
      "g c": () => setActiveView("config"),
    }),
    [refresh, setActiveView, setHelpOpen, setHue, setPaletteOpen]
  );

  useKeyboardShortcuts(shortcuts);

  const metricsView = useMemo(() => metrics, [metrics]);

  const commandActions = useMemo<CommandAction[]>(
    () => [
      {
        id: "dashboard-home",
        title: "Go to dashboard home",
        description: "Return to the realtime metrics overview.",
        shortcut: "G then H",
        onSelect: () => setActiveView("home"),
      },
      {
        id: "prompt-history",
        title: "Open prompt history",
        description: "Preview upcoming prompt auditing tools.",
        shortcut: "G then P",
        onSelect: () => setActiveView("prompts"),
      },
      {
        id: "configuration-panel",
        title: "Open configuration panel",
        description: "Manage backend routing and feature flags (coming soon).",
        shortcut: "G then C",
        onSelect: () => setActiveView("config"),
      },
      {
        id: "refresh-metrics",
        title: "Refresh metrics",
        description: "Pull a fresh snapshot from the metrics API.",
        shortcut: "R",
        onSelect: () => refresh(),
      },
      {
        id: "toggle-help",
        title: "Show keyboard shortcuts",
        description: "Open the overlay with all accelerators.",
        shortcut: "Shift + /",
        onSelect: () => setHelpOpen(true),
      },
      {
        id: "shift-hue",
        title: "Shift accent hue",
        description: "Cycle the accent hue forward by 10 degrees.",
        shortcut: "H",
        onSelect: () => setHue((value) => (value + 10) % 360),
      },
    ],
    [refresh, setActiveView, setHelpOpen, setHue]
  );

  let mainContent: React.ReactNode;
  if (activeView === "home") {
    mainContent = (
      <>
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
      </>
    );
  } else if (activeView === "prompts") {
    mainContent = (
      <section className="panel" aria-label="Prompt history roadmap">
        <h2>Prompt History Preview</h2>
        <p>
          Audit trails and searchable prompt history will live here. The roadmap pairs this view with keyboard navigation,
          retention controls, and export tooling so operations teams can triage conversations quickly.
        </p>
        <p className="panel-placeholder">Use the command palette (Cmd/Ctrl + K) to jump back to the dashboard at any time.</p>
      </section>
    );
  } else {
    mainContent = (
      <section className="panel" aria-label="Configuration panel roadmap">
        <h2>Configuration Panel</h2>
        <p>
          Centralised backend configuration is on the way. Expect editable retry budgets, backend routing, and feature flag
          toggles surfaced directly in this view with full keyboard support.
        </p>
        <p className="panel-placeholder">Until then, manage settings through environment variables or the CLI wizard.</p>
      </section>
    );
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="branding">
          <img src={logoUrl} alt="AI Ticket" />
          <h1>AI Ticket Operations</h1>
        </div>
        <div className="controls-bar">
          <HueSlider value={hue} onChange={setHue} />
          <span className="shortcuts-hint">Shift + / for shortcuts · Cmd/Ctrl + K for commands</span>
        </div>
      </header>
      <main className="app-content">{mainContent}</main>
      {helpOpen && <HelpDialog onClose={() => setHelpOpen(false)} />}
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} actions={commandActions} />
    </div>
  );
};

export default App;
