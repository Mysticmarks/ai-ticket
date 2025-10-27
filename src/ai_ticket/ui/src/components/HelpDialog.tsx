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
          <dt>?</dt>
          <dd>Toggle this help</dd>
          <dt>R</dt>
          <dd>Manually refresh metrics snapshot</dd>
          <dt>H</dt>
          <dd>Shift the accent hue forward</dd>
        </dl>
        <h3>About this dashboard</h3>
        <p>
          Metrics and status panels update in real-time using a streaming API. The accent hue slider updates all gradients in
          the interface and the setting is stored locally for quick recall.
        </p>
        <button type="button" onClick={onClose}>
          Close
        </button>
      </div>
    </div>
  );
};

export default HelpDialog;
