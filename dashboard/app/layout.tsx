import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "RootPilot Operations",
  description:
    "Queue, inspect, and review evidence-grounded incident investigations.",
  metadataBase: new URL(
    process.env.SITE_URL ?? "http://localhost:3000",
  ),
  openGraph: {
    title: "RootPilot Operations",
    description: "From incident signal to grounded decision.",
    images: ["/og.png"],
  },
  twitter: {
    card: "summary_large_image",
    title: "RootPilot Operations",
    description: "From incident signal to grounded decision.",
    images: ["/og.png"],
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        {children}
      </body>
    </html>
  );
}
