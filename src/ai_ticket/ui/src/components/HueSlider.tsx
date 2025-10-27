import React from "react";

type HueSliderProps = {
  value: number;
  onChange: (value: number) => void;
};

const HueSlider: React.FC<HueSliderProps> = ({ value, onChange }) => {
  return (
    <label className="hue-slider">
      Accent hue
      <input
        type="range"
        min={0}
        max={359}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        aria-label="Adjust accent hue"
      />
      <span>{value}°</span>
    </label>
  );
};

export default HueSlider;
