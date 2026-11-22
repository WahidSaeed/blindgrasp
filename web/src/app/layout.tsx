import type { Metadata } from "next";
import { Fraunces, IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import "./globals.css";

const display = Fraunces({ variable: "--nf-display", subsets: ["latin"], axes: ["SOFT", "opsz"], style: ["normal", "italic"] });
const sans = IBM_Plex_Sans({ variable: "--nf-body", subsets: ["latin"], weight: ["400", "500", "600"] });
const mono = IBM_Plex_Mono({ variable: "--nf-data", subsets: ["latin"], weight: ["400", "500", "600"] });

export const metadata: Metadata = {
  title: "Blindgrasp — a blind robot that learns by touch",
  description: "A Franka arm in MuJoCo maps its table by touch and learns to push in a few tries with TabPFN in-context learning.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${display.variable} ${sans.variable} ${mono.variable} h-full antialiased`}>
      <body className="min-h-full">{children}</body>
    </html>
  );
}
