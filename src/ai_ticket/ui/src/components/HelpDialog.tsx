import React from "react";

type HelpDialogProps = {
  onClose: () => void;
};

const HelpDialog: React.FC<HelpDialogProps> = ({ onClose }) => {
  return (
    <div className="help-dialog-backdrop" role="dialog" aria-modal="true" aria-label="Keyboard shortcuts and help">
      <div className="help-dialog">
        <h3>Keyboard Shortcuts</h3>
        <dl>
          <dt>Shift + /</dt>
          <dd>Toggle this help overlay</dd>
          <dt>Cmd/Ctrl + K</dt>
          <dd>Open the command palette</dd>
          <dt>G then H</dt>
          <dd>Jump to the dashboard home panels</dd>
          <dt>G then P</dt>
          <dd>Preview the prompt history workspace</dd>
          <dt>G then C</dt>
          <dd>Open the configuration panel preview</dd>
          <dt>R</dt>
          <dd>Manually refresh the metrics snapshot</dd>
          <dt>H</dt>
          <dd>Shift the accent hue forward</dd>
          <dt>Esc</dt>
          <dd>Close help and command palette overlays</dd>
        </dl>
        <h3>About this dashboard</h3>
        <p>
          Metrics and status panels update in real-time using a streaming API. The command palette mirrors the roadmap for
          keyboard-first navigation, while the accent hue slider updates gradients across the interface and persists locally.
        </p>
        <button type="button" onClick={onClose}>
          Close
        </button>
      </div>
    </div>
  );
};

export default HelpDialog;
