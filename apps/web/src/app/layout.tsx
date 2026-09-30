import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "MindHire",
    template: "%s · MindHire",
  },
  description: "A secure workspace for the end-to-end hiring lifecycle.",
  robots: {
    index: false,
    follow: false,
  },
};

import { Header, TopNotificationBar } from "@/components/layout/header";

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body className="flex flex-col min-h-screen">
        <TopNotificationBar />
        <Header />
        <main className="flex-1 flex flex-col">
          {children}
        </main>
      </body>
    </html>
  );
}
