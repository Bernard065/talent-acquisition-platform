"use client";

import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";



import { NAV_DATA } from "@/constants/nav";

export function Header() {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  return (
    <header className="sticky top-0 left-0 w-full z-50 bg-white border-b border-gray-100">
      <div className="max-w-305 mx-auto px-4 lg:px-4 h-17.5 lg:h-20 flex items-center justify-between">
        {/* Left: Logo */}
        <div className="shrink-0 z-50">
          <Link href="/" className="font-display font-bold text-xl lg:text-2xl tracking-tighter text-sr-text-blue flex items-center gap-2">
            <span className="w-7 h-7 lg:w-8 lg:h-8 rounded bg-sr-green text-white flex items-center justify-center p-1.5">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="w-full h-full">
                <path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z"/>
                <path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z"/>
                <path d="M15 13a4.5 4.5 0 0 1-3-4 4.5 4.5 0 0 1-3 4"/>
              </svg>
            </span>
            MindHire
          </Link>
        </div>

        {/* Center: Desktop Navigation */}
        <nav className="hidden xl:flex items-center space-x-1">
          {NAV_DATA.map((navItem) => (
            <div key={navItem.title} className="relative group px-3 py-6 cursor-pointer">
              <span className="text-[15px] font-semibold text-sr-text-blue group-hover:text-black transition-colors flex items-center gap-1">
                {navItem.title}
                {navItem.megaMenu && (
                  <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="opacity-50 group-hover:opacity-100 group-hover:-rotate-180 transition-all duration-200">
                    <path d="m6 9 6 6 6-6"/>
                  </svg>
                )}
              </span>
              {/* Active indicator line */}
              <div className="absolute bottom-4 left-0 w-full h-0.5 bg-sr-green scale-x-0 group-hover:scale-x-100 transition-transform origin-left rounded-full" />

              {/* Mega Menu Full Width Overlay */}
              {navItem.megaMenu && (
                <div className="fixed left-0 top-20 w-full bg-white border-t border-gray-100 shadow-[0_10px_30px_rgba(0,0,0,0.05)] opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-200 -translate-y-2 group-hover:translate-y-0">
                  <div className="max-w-305 mx-auto px-4 py-10 flex gap-12">
                    {navItem.megaMenu.map((section, idx) => (
                      <div key={idx} className="flex-1 min-w-62.5">
                        <h4 className="text-sm font-bold tracking-widest text-sr-gray uppercase mb-6">{section.heading}</h4>
                        <div className="flex flex-col gap-6">
                          {section.items.map((item, itemIdx) => (
                            <Link href="/" key={itemIdx} className="group/item flex flex-col gap-1">
                              <span className="text-[15px] font-semibold text-sr-text-blue group-hover/item:text-sr-green transition-colors">
                                {item.title}
                              </span>
                              <span className="text-[14px] text-sr-gray leading-tight">
                                {item.desc}
                              </span>
                            </Link>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
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
        <div className="xl:hidden absolute top-17.5 left-0 w-full bg-white h-[calc(100vh-70px)] overflow-y-auto border-t border-gray-100 p-4">
          <nav className="flex flex-col gap-2">
            {NAV_DATA.map((navItem) => (
              <div key={navItem.title} className="w-full flex items-center justify-between py-4 border-b border-gray-100 cursor-pointer group">
                <span className="text-lg font-semibold text-sr-text-blue group-hover:text-sr-green transition-colors">{navItem.title}</span>
                {navItem.megaMenu && (
                  <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-sr-green">
                    <path d="m9 18 6-6-6-6"/>
                  </svg>
                )}
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
