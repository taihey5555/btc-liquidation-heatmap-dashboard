import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "BTCUSDT Liquidation Heatmap",
  description: "Mock liquidation heatmap dashboard for BTCUSDT",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ja">
      <body>{children}</body>
    </html>
  );
}
