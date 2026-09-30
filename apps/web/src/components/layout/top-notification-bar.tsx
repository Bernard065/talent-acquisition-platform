"use client";

import Link from "next/link";
import { useState } from "react";

export function TopNotificationBar() {
  const [isVisible, setIsVisible] = useState(true);

  if (!isVisible) return null;

  return (
    <div className="bg-sr-mint w-full">
      <div className="max-w-[1220px] mx-auto relative px-8 md:px-12 py-3 text-center">
        <p className="text-sm font-semibold text-sr-text-blue m-0 flex flex-col sm:flex-row items-center justify-center gap-1 sm:gap-2">
          <span>We&apos;ve been ranked a Core Leader in the 2026 Grid for Talent Acquisition.</span>
          <Link href="/" className="relative text-sr-text-blue hover:text-sr-green hover:underline decoration-2 underline-offset-4 transition-colors whitespace-nowrap">
            Read the report &gt;
          </Link>
        </p>
        <button
          onClick={() => setIsVisible(false)}
          className="absolute right-2 sm:right-4 top-1/2 -translate-y-1/2 text-sr-text-blue opacity-50 hover:opacity-100 p-1"
          aria-label="Close notification"
        >
          {/* Simple X icon */}
          <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M18 6 6 18"/><path d="m6 6 12 12"/>
          </svg>
        </button>
      </div>
    </div>
  );
}
