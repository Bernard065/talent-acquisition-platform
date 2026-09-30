import React from "react";
import Link from "next/link";

export const GlobalFooter = () => {
  return (
    <footer className="w-full bg-[#0A1C2B] text-gray-300 pt-20 pb-8">
      <div className="max-w-305 mx-auto px-4 lg:px-4">

        {/* Main Footer Content */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-12 lg:gap-8 mb-16">

          {/* Brand Column */}
          <div className="lg:col-span-1">
            <Link href="/" className="flex items-center gap-2 mb-6 text-white group">
              <svg className="h-8 w-8 text-sr-mint group-hover:text-sr-green transition-colors" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z"/><path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z"/><path d="M15 13a4.5 4.5 0 0 1-3-4 4.5 4.5 0 0 1-3 4"/><path d="M17.599 6.5a3 3 0 0 0 .399-1.375"/></svg>
              <span className="font-display font-bold text-2xl tracking-tight">MindHire</span>
            </Link>
            <p className="text-sm text-gray-400 mb-8 leading-relaxed">
              The AI-driven talent operating system designed to help modern teams attract, select, and hire the best candidates at scale.
            </p>
            {/* Social Icons */}
            <div className="flex items-center gap-4">
              <Link href="#" className="text-gray-400 hover:text-sr-mint transition-colors">
                <svg className="h-5 w-5" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/></svg>
              </Link>
              <Link href="#" className="text-gray-400 hover:text-sr-mint transition-colors">
                <svg className="h-5 w-5" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M24 4.557c-.883.392-1.832.656-2.828.775 1.017-.609 1.798-1.574 2.165-2.724-.951.564-2.005.974-3.127 1.195-.897-.957-2.178-1.555-3.594-1.555-3.179 0-5.515 2.966-4.797 6.045-4.091-.205-7.719-2.165-10.148-5.144-1.29 2.213-.669 5.108 1.523 6.574-.806-.026-1.566-.247-2.229-.616-.054 2.281 1.581 4.415 3.949 4.89-.693.188-1.452.232-2.224.084.626 1.956 2.444 3.379 4.6 3.419-2.07 1.623-4.678 2.348-7.29 2.04 2.179 1.397 4.768 2.212 7.548 2.212 9.142 0 14.307-7.721 13.995-14.646.962-.695 1.797-1.562 2.457-2.549z"/></svg>
              </Link>
              <Link href="#" className="text-gray-400 hover:text-sr-mint transition-colors">
                <svg className="h-5 w-5" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.5 12 3.5 12 3.5s-7.505 0-9.377.55a3.016 3.016 0 0 0-2.122 2.136C0 8.07 0 12 0 12s0 3.93.501 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.55 9.377.55 9.377.55s7.505 0 9.377-.55a3.016 3.016 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/></svg>
              </Link>
            </div>
          </div>

          {/* Platform Column */}
          <div className="lg:col-span-1 lg:ml-8">
            <h4 className="text-white font-semibold mb-6">Platform</h4>
            <ul className="space-y-4 text-sm">
              <li><Link href="#" className="hover:text-sr-mint transition-colors">Applicant Tracking</Link></li>
              <li><Link href="#" className="hover:text-sr-mint transition-colors">Candidate CRM</Link></li>
              <li><Link href="#" className="hover:text-sr-mint transition-colors">Onboarding</Link></li>
              <li><Link href="#" className="hover:text-sr-mint transition-colors">Neural AI</Link></li>
              <li><Link href="#" className="hover:text-sr-mint transition-colors">Analytics</Link></li>
              <li><Link href="#" className="hover:text-sr-mint transition-colors">Pricing</Link></li>
            </ul>
          </div>

          {/* Solutions Column */}
          <div className="lg:col-span-1">
            <h4 className="text-white font-semibold mb-6">Solutions</h4>
            <ul className="space-y-4 text-sm">
              <li><Link href="#" className="hover:text-sr-mint transition-colors">Enterprise</Link></li>
              <li><Link href="#" className="hover:text-sr-mint transition-colors">High-Volume</Link></li>
              <li><Link href="#" className="hover:text-sr-mint transition-colors">Diversity & Inclusion</Link></li>
              <li><Link href="#" className="hover:text-sr-mint transition-colors">Healthcare</Link></li>
              <li><Link href="#" className="hover:text-sr-mint transition-colors">Retail</Link></li>
            </ul>
          </div>

          {/* Resources Column */}
          <div className="lg:col-span-1">
            <h4 className="text-white font-semibold mb-6">Resources</h4>
            <ul className="space-y-4 text-sm">
              <li><Link href="#" className="hover:text-sr-mint transition-colors">Blog</Link></li>
              <li><Link href="#" className="hover:text-sr-mint transition-colors">Case Studies</Link></li>
              <li><Link href="#" className="hover:text-sr-mint transition-colors">Hiring Guides</Link></li>
              <li><Link href="#" className="hover:text-sr-mint transition-colors">Help Center</Link></li>
              <li><Link href="#" className="hover:text-sr-mint transition-colors">API Documentation</Link></li>
            </ul>
          </div>

          {/* Company Column */}
          <div className="lg:col-span-1">
            <h4 className="text-white font-semibold mb-6">Company</h4>
            <ul className="space-y-4 text-sm">
              <li><Link href="#" className="hover:text-sr-mint transition-colors">About Us</Link></li>
              <li><Link href="#" className="hover:text-sr-mint transition-colors">Careers</Link></li>
              <li><Link href="#" className="hover:text-sr-mint transition-colors">Partner Program</Link></li>
              <li><Link href="#" className="hover:text-sr-mint transition-colors">Contact Us</Link></li>
              <li><Link href="#" className="hover:text-sr-mint transition-colors">Press</Link></li>
            </ul>
          </div>

        </div>

        {/* Bottom Bar */}
        <div className="border-t border-white/10 pt-8 flex flex-col md:flex-row justify-between items-center gap-4">
          <p className="text-xs text-gray-500">
            &copy; {new Date().getFullYear()} MindHire. All rights reserved.
          </p>
          <div className="flex flex-wrap items-center gap-6 text-xs text-gray-500">
            <Link href="#" className="hover:text-white transition-colors">Privacy Policy</Link>
            <Link href="#" className="hover:text-white transition-colors">Terms of Service</Link>
            <Link href="#" className="hover:text-white transition-colors">Cookie Policy</Link>
            <Link href="#" className="hover:text-white transition-colors">Security</Link>
            <Link href="#" className="hover:text-white transition-colors">Accessibility</Link>
          </div>
        </div>

      </div>
    </footer>
  );
};
