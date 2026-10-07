import type { ReactNode } from "react";
import Link from "next/link";
import { MindHireMark } from "@/components/icons";

export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <main className="flex-1 flex w-full min-h-screen lg:h-screen lg:overflow-hidden bg-white">
      {/* Left Pane - Branding/Visual */}
      <div className="hidden lg:flex flex-1 relative bg-[#0A1C2B]">
        <div className="absolute inset-0 bg-linear-to-t from-[#0A1C2B] via-transparent to-transparent z-10" />

        {/* Subtle background pattern/gradient */}
        <div className="absolute inset-0 opacity-20 bg-[radial-gradient(ellipse_at_top_right,var(--tw-gradient-stops))] from-sr-mint via-sr-green to-transparent" />

        <div className="absolute inset-0 flex flex-col justify-end p-16 z-20 text-white">
          <Link href="/" className="flex items-center gap-2 mb-12 hover:opacity-80 transition-opacity">
            <MindHireMark className="h-8 w-8 text-sr-mint" />
            <span className="font-display font-bold text-2xl tracking-tight">MindHire</span>
          </Link>
          <blockquote className="space-y-6">
            <p className="text-3xl font-display font-light leading-tight">
              &quot;MindHire revolutionized how we attract and hire top talent. It&apos;s the most intuitive operating system we&apos;ve ever used.&quot;
            </p>
            <footer className="text-gray-400 text-lg flex items-center gap-4">
              <div className="w-10 h-10 rounded-full bg-sr-mint flex items-center justify-center text-sr-text-blue font-bold">
                BB
              </div>
              <span>Bernard Bebeni, VP of Talent Acquisition</span>
            </footer>
          </blockquote>
        </div>
      </div>

      {/* Right Pane - Form Content */}
      <div className="flex-1 flex flex-col justify-center px-4 sm:px-6 lg:px-20 xl:px-24 h-full lg:overflow-y-auto">
        <div className="mx-auto w-full max-w-sm lg:w-96 py-12 lg:py-16">
          {children}
        </div>
      </div>
    </main>
  );
}
