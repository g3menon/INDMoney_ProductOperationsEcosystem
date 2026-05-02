import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Groww Ops AI",
  description: "Product operations dashboard for customer questions, weekly insights, and advisor workflows.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">{children}</body>
    </html>
  );
}
