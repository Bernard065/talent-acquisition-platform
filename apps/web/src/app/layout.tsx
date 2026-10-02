import type { Metadata } from "next";
import type { ReactNode } from "react";
import { AuthProvider } from "@/providers/auth-provider";
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

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body className="flex flex-col min-h-screen">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
