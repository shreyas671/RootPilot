import type { Metadata } from "next";
import "./globals.css";

const title = "RootPilot Operations";
const description =
  "Queue, inspect, and review evidence-grounded incident investigations.";

const vercelHost =
  process.env.VERCEL_PROJECT_PRODUCTION_URL ?? process.env.VERCEL_URL;
const siteUrl =
  process.env.NEXT_PUBLIC_SITE_URL ??
  (vercelHost ? `https://${vercelHost}` : "http://localhost:3000");

export const metadata: Metadata = {
  title,
  description,
  metadataBase: new URL(siteUrl),
  openGraph: {
    title,
    description: "From incident signal to grounded decision.",
    images: ["/og.png"],
  },
  twitter: {
    card: "summary_large_image",
    title,
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
      <body>{children}</body>
    </html>
  );
}
