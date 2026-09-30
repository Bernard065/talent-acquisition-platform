"use client";

import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";

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

export function Header() {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  const navItems = ["Platform", "Solutions", "Services", "Customers", "Partners", "Resources", "About"];

  return (
    <header className="sticky top-0 left-0 w-full z-50 bg-white border-b border-gray-100">
      <div className="max-w-[1220px] mx-auto px-4 lg:px-4 h-[70px] lg:h-[80px] flex items-center justify-between">
        {/* Left: Logo */}
        <div className="flex-shrink-0 z-50">
          <Link href="/" className="font-display font-bold text-xl lg:text-2xl tracking-tighter text-sr-text-blue flex items-center gap-2">
            <span className="w-7 h-7 lg:w-8 lg:h-8 rounded bg-sr-green text-white flex items-center justify-center text-base lg:text-lg">M</span>
            MindHire
          </Link>
        </div>

        {/* Center: Desktop Navigation */}
        <nav className="hidden xl:flex items-center space-x-1">
          {navItems.map((item) => (
            <div key={item} className="relative group px-3 py-6 cursor-pointer">
              <span className="text-[15px] font-semibold text-sr-text-blue group-hover:text-black transition-colors flex items-center gap-1">
                {item}
                <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="opacity-50 group-hover:opacity-100 group-hover:-rotate-180 transition-all duration-200">
                  <path d="m6 9 6 6 6-6"/>
                </svg>
              </span>
              {/* Active indicator line */}
              <div className="absolute bottom-4 left-0 w-full h-[2px] bg-sr-green scale-x-0 group-hover:scale-x-100 transition-transform origin-left rounded-full" />
            </div>
          ))}
        </nav>

        {/* Right: Actions */}
        <div className="hidden xl:flex items-center gap-6">
          <Link href="/login" className="text-[15px] font-semibold text-sr-text-blue hover:text-black">
            Login
          </Link>
          <Button className="h-10 px-6 text-sm">
            Get Started
          </Button>
        </div>

        {/* Mobile Menu Toggle Button */}
        <div className="xl:hidden flex items-center gap-4 z-50">
          <Button className="h-9 px-4 text-xs sm:text-sm">
            Get Started
          </Button>
          <button
            onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
            className="text-sr-text-blue p-2 -mr-2"
            aria-label="Toggle Menu"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              {isMobileMenuOpen ? (
                <>
                  <path d="M18 6 6 18"/><path d="m6 6 12 12"/>
                </>
              ) : (
                <>
                  <line x1="4" x2="20" y1="12" y2="12"/><line x1="4" x2="20" y1="6" y2="6"/><line x1="4" x2="20" y1="18" y2="18"/>
                </>
              )}
            </svg>
          </button>
        </div>
      </div>

      {/* Mobile Navigation Menu */}
      {isMobileMenuOpen && (
        <div className="xl:hidden absolute top-[70px] left-0 w-full bg-white h-[calc(100vh-70px)] overflow-y-auto border-t border-gray-100 p-4">
          <nav className="flex flex-col gap-2">
            {navItems.map((item) => (
              <div key={item} className="w-full flex items-center justify-between py-4 border-b border-gray-100 cursor-pointer">
                <span className="text-lg font-semibold text-sr-text-blue">{item}</span>
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-sr-green">
                  <path d="m9 18 6-6-6-6"/>
                </svg>
              </div>
            ))}
            <div className="py-6 flex flex-col gap-4">
              <Link href="/login" className="text-lg font-semibold text-sr-text-blue text-center">
                Login
              </Link>
            </div>
          </nav>
        </div>
      )}
    </header>
  );
}
