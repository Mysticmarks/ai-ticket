import React from "https://esm.sh/react@18.2.0";

const ShortcutOverlay = ({ sections, onClose }) => {
  return React.createElement(
    "div",
    {
      className: "shortcut-overlay",
      role: "dialog",
      "aria-modal": "true",
      "aria-label": "Keyboard shortcuts",
      "data-testid": "shortcut-overlay",
    },
    React.createElement(
      "div",
      { className: "shortcut-surface" },
      React.createElement(
        "header",
        { className: "shortcut-header" },
        React.createElement("h3", null, "Keyboard Shortcuts"),
        React.createElement(
          "button",
          { type: "button", onClick: onClose, className: "ghost-button" },
          "Close"
        )
      ),
      React.createElement(
        "div",
        { className: "shortcut-grid" },
        sections.map((section) =>
          React.createElement(
            "section",
            { key: section.title, "aria-label": section.title, className: "shortcut-section" },
            React.createElement("h4", null, section.title),
            React.createElement(
              "dl",
              null,
              section.shortcuts.map((shortcut) =>
                React.createElement(
                  React.Fragment,
                  { key: shortcut.combo },
                  React.createElement("dt", null, shortcut.combo),
                  React.createElement("dd", null, shortcut.description)
                )
              )
            )
          )
        )
      ),
      React.createElement(
        "footer",
        { className: "shortcut-footer" },
        React.createElement(
          "p",
          null,
          "Preferences are stored locally, so your shortcuts, theme, and viewing options persist the next time you visit the dashboard."
        )
      )
    )
  );
};

export default ShortcutOverlay;
