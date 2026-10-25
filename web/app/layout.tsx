import type { ReactNode } from "react";
import { Archivo, Big_Shoulders, Doto } from "next/font/google";
import "./globals.css";

// Big Shoulders for stadium-signage headings, Archivo for reading, Doto for the
// LED clock and the fourth official's board on the decision card.
const display = Big_Shoulders({ subsets: ["latin"], variable: "--font-display" });
const body = Archivo({ subsets: ["latin"], variable: "--font-body", axes: ["wdth"] });
const led = Doto({ subsets: ["latin"], variable: "--font-led", weight: ["700", "900"] });

const description = "Live decision guide: who is tiring, the bench's options and what each is worth, on a replayed synthetic match. Written by Microsoft Foundry agents and checked in code, running on Azure.";

// The share card (app/opengraph-image.png, a frame of the TV picture at the 60' card) needs an absolute URL.
export const metadata = {
  metadataBase: new URL("https://ashy-ocean-03bdf100f.2.azurestaticapps.net"),
  title: "The Dugout",
  description,
  openGraph: { title: "The Dugout", description, type: "website", siteName: "The Dugout" },
  twitter: { card: "summary_large_image", title: "The Dugout", description },
};

export const viewport = { width: "device-width", initialScale: 1, themeColor: "#e6ebe8" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${display.variable} ${body.variable} ${led.variable}`}>
      <body>{children}</body>
    </html>
  );
}
