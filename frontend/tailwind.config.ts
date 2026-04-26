import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        groww: {
          ink: "#0B1220",
          panel: "#0F172A",
          accent: "#00B386",
          muted: "#94A3B8",
          border: "#1E293B",
        },
      },
    },
  },
  plugins: [],
};

export default config;
