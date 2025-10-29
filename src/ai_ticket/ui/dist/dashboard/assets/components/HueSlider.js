import React from "https://esm.sh/react@18.2.0";

const HueSlider = ({ value, onChange }) => {
  return React.createElement(
    "label",
    { className: "hue-slider" },
    "Accent hue",
    React.createElement("input", {
      type: "range",
      min: 0,
      max: 359,
      value,
      onChange: (event) => onChange(Number(event.target.value)),
      "aria-label": "Adjust accent hue",
    }),
    React.createElement("span", null, `${value}°`)
  );
};

export default HueSlider;
