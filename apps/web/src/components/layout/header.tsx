import Link from "next/link";
import { Button } from "@/components/ui/button";

export function TopNotificationBar() {
  return (
    <div className="bg-sr-mint w-full">
      <div className="max-w-[1220px] mx-auto relative px-4 py-3 text-center">
        <p className="text-sm font-semibold text-sr-text-blue m-0 flex items-center justify-center gap-2">
          We&apos;ve been ranked a Core Leader in the 2026 Grid for Talent Acquisition.
          <Link href="/" className="relative text-sr-text-blue hover:text-sr-green hover:underline decoration-2 underline-offset-4 transition-colors">
            Read the report &gt;
          </Link>
        </p>
        <button
          className="absolute right-4 top-1/2 -translate-y-1/2 text-sr-text-blue opacity-50 hover:opacity-100"
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
  return (
    <header className="sticky top-0 left-0 w-full z-50 bg-white border-b border-gray-100">
      <div className="max-w-[1220px] mx-auto px-4 h-[80px] flex items-center justify-between">
        {/* Left: Logo */}
        <div className="flex-shrink-0">
          <Link href="/" className="font-display font-bold text-2xl tracking-tighter text-sr-text-blue flex items-center gap-2">
            <span className="w-8 h-8 rounded bg-sr-green text-white flex items-center justify-center text-lg">T</span>
            Talent Acquisition Platform
          </Link>
        </div>

        {/* Center: Navigation */}
        <nav className="hidden lg:flex items-center space-x-1">
          {["Platform", "Solutions", "Services", "Customers", "Partners", "Resources", "About"].map((item) => (
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
        <div className="hidden lg:flex items-center gap-6">
          <Link href="/login" className="text-[15px] font-semibold text-sr-text-blue hover:text-black">
            Login
          </Link>
          <Button className="h-10 px-6 text-sm">
            Get Started
          </Button>
        </div>
      </div>
    </header>
  );
}
