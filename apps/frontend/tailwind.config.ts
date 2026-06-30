import type { Config } from "tailwindcss";
import forms from "@tailwindcss/forms";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        border: "#d9dee7",
        canvas: "#f7f8fb",
        ink: "#172033",
        muted: "#5d687a",
        primary: "#0f766e",
        surface: "#ffffff",
      },
      boxShadow: {
        panel: "0 12px 30px rgba(23, 32, 51, 0.08)",
      },
    },
  },
  plugins: [forms],
};

export default config;
