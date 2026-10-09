import React from "react";
import Link from "next/link";
import { MindHireMark, LinkedinIcon, TwitterIcon, YoutubeIcon } from "@/components/icons";

export const GlobalFooter = () => {
  return (
    <footer className="w-full bg-[#0A1C2B] text-gray-300 pt-20 pb-8">
      <div className="max-w-305 mx-auto px-4 lg:px-4">

        {/* Main Footer Content */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-12 lg:gap-8 mb-16">

          {/* Brand Column */}
          <div className="lg:col-span-1">
            <Link href="/" className="flex items-center gap-2 mb-6 text-white group">
              <MindHireMark className="h-8 w-8 text-sr-mint group-hover:text-sr-green transition-colors" />
              <span className="font-display font-bold text-2xl tracking-tight">MindHire</span>
            </Link>
            <p className="text-sm text-gray-400 mb-8 leading-relaxed">
              The AI-driven talent operating system designed to help modern teams attract, select, and hire the best candidates at scale.
            </p>
            {/* Social Icons */}
            <div className="flex items-center gap-4">
              <Link href="#" className="text-gray-400 hover:text-sr-mint transition-colors">
                <LinkedinIcon className="h-5 w-5" />
              </Link>
              <Link href="#" className="text-gray-400 hover:text-sr-mint transition-colors">
                <TwitterIcon className="h-5 w-5" />
              </Link>
              <Link href="#" className="text-gray-400 hover:text-sr-mint transition-colors">
                <YoutubeIcon className="h-5 w-5" />
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
              <li><Link href="/careers" className="hover:text-sr-mint transition-colors">Careers</Link></li>
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
