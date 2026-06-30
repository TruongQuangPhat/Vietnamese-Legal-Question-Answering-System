import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "VnLaw-QA",
  description: "Vietnamese legal QA product interface.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="vi" suppressHydrationWarning>
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}
