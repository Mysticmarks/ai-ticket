import React from "https://esm.sh/react@18.2.0";

const AdminPanel = ({
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
  return React.createElement(
    "div",
    { className: "admin-panel", "data-open": open, "data-testid": "admin-panel" },
    React.createElement(
      "header",
      null,
      React.createElement(
        "div",
        null,
        React.createElement("span", { className: "admin-pill" }, "Admin"),
        React.createElement("h3", null, "Operations Control Center"),
        React.createElement(
          "p",
          null,
          "Quickly adjust real-time behaviour, theme preferences, and diagnostic helpers. Settings persist locally so you can pick up exactly where you left off."
        )
      ),
      React.createElement(
        "button",
        {
          type: "button",
          className: "ghost-button",
          onClick: () => onToggle(!open),
          "data-testid": "admin-panel-toggle",
        },
        open ? "Collapse" : "Expand"
      )
    ),
    open
      ? React.createElement(
          "div",
          { className: "admin-grid" },
          React.createElement(
            "section",
            { "aria-label": "Realtime controls" },
            React.createElement("h4", null, "Realtime controls"),
            React.createElement(
              "label",
              { className: "toggle", "data-testid": "pause-stream-toggle" },
              React.createElement("input", {
                type: "checkbox",
                checked: streamPaused,
                onChange: (event) => onStreamPausedChange(event.target.checked),
              }),
              React.createElement("span", null, "Pause incoming stream updates")
            ),
            React.createElement(
              "label",
              { className: "toggle" },
              React.createElement("input", {
                type: "checkbox",
                checked: followLive,
                onChange: (event) => onFollowLiveChange(event.target.checked),
              }),
              React.createElement("span", null, "Auto-follow live snapshots")
            ),
            React.createElement(
              "button",
              { type: "button", className: "ghost-button", onClick: onRefresh },
              "Trigger refresh"
            )
          ),
          React.createElement(
            "section",
            { "aria-label": "Theme preferences" },
            React.createElement("h4", null, "Theme"),
            React.createElement(
              "div",
              { className: "theme-switcher" },
              React.createElement(
                "button",
                {
                  type: "button",
                  className: `ghost-button ${theme === "dark" ? "active" : ""}`,
                  onClick: () => onThemeChange("dark"),
                  "data-testid": "theme-dark",
                },
                "Dark"
              ),
              React.createElement(
                "button",
                {
                  type: "button",
                  className: `ghost-button ${theme === "light" ? "active" : ""}`,
                  onClick: () => onThemeChange("light"),
                  "data-testid": "theme-light",
                },
                "Light"
              )
            ),
            React.createElement(
              "label",
              { className: "toggle", "data-testid": "reduced-motion-toggle" },
              React.createElement("input", {
                type: "checkbox",
                checked: reducedMotion,
                onChange: (event) => onReducedMotionChange(event.target.checked),
              }),
              React.createElement("span", null, "Reduce animations")
            )
          ),
          React.createElement(
            "section",
            { "aria-label": "Shortcuts quick reference", className: "admin-shortcuts" },
            React.createElement("h4", null, "Quick shortcuts"),
            React.createElement(
              "ul",
              null,
              React.createElement(
                "li",
                null,
                React.createElement("strong", null, "Shift + /"),
                " — Toggle shortcut overlay"
              ),
              React.createElement(
                "li",
                null,
                React.createElement("strong", null, "R"),
                " — Refresh metrics"
              ),
              React.createElement(
                "li",
                null,
                React.createElement("strong", null, "["),
                " / ",
                React.createElement("strong", null, "]"),
                " — Step through history"
              ),
              React.createElement(
                "li",
                null,
                React.createElement("strong", null, "Ctrl + ."),
                " — Toggle this panel"
              )
            )
          )
        )
      : null
  );
};

export default AdminPanel;
