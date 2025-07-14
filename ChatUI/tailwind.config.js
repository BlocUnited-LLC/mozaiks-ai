/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,jsx,ts,tsx}"],
  theme: {
    extend: {
      container: {
        center: true,
      },
      screens: {
        sm: "480px",
        md: "768px",
        lg: "976px",
        xl: "1440px",
      },
      colors: {
        purple: "#7e5bef",
        pink: "#ff49db",
        orange: "#ff7849",
        green: "#13ce66",
        yellow: "#ffc82c",
        white: "#ffff",
        "gray-dark": "#273444",
        "gray-light": "#d3dce6",
        gradient1: "#060B26",
        gradient2: "#1A1F37",
        gradient3: "#0F123B",
        navyblue: "#1A1F37",
        transpar: "rgba(255, 255, 255, 0.08)",
      },
      height: {
        "600x": "600px",
        "509x": "509px",
      },
      fontSize: {
        "8x": "8px",
      },
    },
  },
  plugins: [require("@tailwindcss/forms")],
};
