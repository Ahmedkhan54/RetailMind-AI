import type { Metadata, Viewport } from "next";
import "./globals.css";
import { AppProviders } from "@/components/providers";

export const metadata: Metadata = {
  title: {
    default: "RetailMind AI | Business Analytics",
    template: "%s | RetailMind AI",
  },
  description: "A clear workspace for business analytics, forecasts, customer intelligence, and trusted exports.",
  applicationName: "RetailMind AI",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#f7f8fb",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className="h-full antialiased"
    >
      <body className="min-h-full flex flex-col font-sans"><AppProviders>{children}</AppProviders></body>
    </html>
  );
}
