import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        groww: {
          bg: "#F8F7FC",
          surface: "#FFFFFF",
          surfaceSoft: "#F5F3FB",
          panel: "#FFFFFF",
          border: "#E8E7F0",
          text: "#1F2430",
          muted: "#6B7280",
          faint: "#9CA3AF",
          accent: "#7C3AED",
          accentSoft: "#F3ECFF",
          accentBlue: "#60A5FA",
          accentPink: "#F9A8D4",
          success: "#22C55E",
          warning: "#F59E0B",
          danger: "#EF4444",
          info: "#3B82F6",
        },
      },
      boxShadow: {
        soft: "0 18px 50px rgba(31, 36, 48, 0.08)",
        card: "0 12px 30px rgba(31, 36, 48, 0.06)",
      },
    },
  },
  plugins: [],
};

export default config;
