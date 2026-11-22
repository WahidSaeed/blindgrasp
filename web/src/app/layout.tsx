import type { Metadata } from "next";
import { IBM_Plex_Sans, JetBrains_Mono } from "next/font/google";
import "./globals.css";

const sans = IBM_Plex_Sans({ variable: "--nf-body", subsets: ["latin"], weight: ["400", "500", "600"] });
const mono = JetBrains_Mono({ variable: "--nf-data", subsets: ["latin"], weight: ["400", "500", "600"] });

export const metadata: Metadata = {
  title: "Blindgrasp — workstation",
  description: "A Franka arm in MuJoCo maps its table by touch and learns to push in a few tries with TabPFN in-context learning.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable} h-full antialiased`}>
      <body className="h-full">{children}</body>
    </html>
  );
}
