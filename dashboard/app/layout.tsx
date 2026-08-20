import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { headers } from "next/headers";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const title = "RootPilot Operations";
const description =
  "Queue, inspect, and review evidence-grounded incident investigations.";

const requestOrigin = async () => {
  const requestHeaders = await headers();
  const host = (
    requestHeaders.get("x-forwarded-host") ?? requestHeaders.get("host")
  )
    ?.split(",")[0]
    .trim();
  const forwardedProtocol = requestHeaders
    .get("x-forwarded-proto")
    ?.split(",")[0]
    .trim();
  const protocol =
    forwardedProtocol ?? (host?.startsWith("localhost") ? "http" : "https");

  if (host) {
    try {
      return new URL(`${protocol}://${host}`).origin;
    } catch {
      // Fall through to the configured development-safe origin.
    }
  }

  return process.env.SITE_URL ?? "http://localhost:3000";
};

export const dynamic = "force-dynamic";

export async function generateMetadata(): Promise<Metadata> {
  const origin = await requestOrigin();
  const previewImage = new URL("/og.png", origin).toString();

  return {
    title,
    description,
    metadataBase: new URL(origin),
    openGraph: {
      title,
      description: "From incident signal to grounded decision.",
      images: [previewImage],
    },
    twitter: {
      card: "summary_large_image",
      title,
      description: "From incident signal to grounded decision.",
      images: [previewImage],
    },
  };
}

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
