"use client";

import React from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export const Topbar = () => {
  return (
    <header className="h-16 border-b border-gray-200 bg-white flex items-center justify-between px-4 lg:px-8 sticky top-0 z-30">
      
      {/* Mobile Menu Button (shown only on mobile) */}
      <div className="flex items-center md:hidden">
        <Button variant="ghost" size="icon" className="text-gray-500 hover:text-sr-text-blue">
          <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </Button>
      </div>

      {/* Global Search */}
      <div className="hidden sm:flex items-center max-w-md w-full ml-4 md:ml-0 relative">
        <svg className="w-5 h-5 text-gray-400 absolute left-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
        <Input 
          type="search" 
          placeholder="Search candidates, jobs, or keywords..." 
          className="pl-10 h-10 w-full bg-gray-50 border-transparent focus:bg-white focus:border-sr-mint focus:ring-1 focus:ring-sr-mint transition-all"
        />
        <div className="absolute right-3 hidden lg:flex items-center gap-1">
          <kbd className="inline-flex h-5 items-center gap-1 rounded border bg-gray-100 px-1.5 font-mono text-[10px] font-medium text-gray-500 opacity-100">
            <span className="text-xs">⌘</span>K
          </kbd>
        </div>
      </div>

      {/* Right Actions */}
      <div className="flex items-center gap-2 lg:gap-4 ml-auto">
        <Button variant="outline" className="hidden lg:flex h-9 border-gray-200 text-sr-text-blue hover:bg-gray-50 hover:text-sr-text-blue font-medium text-sm gap-2">
          <svg className="w-4 h-4 text-sr-green" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          New Job
        </Button>
        
        <div className="h-6 w-px bg-gray-200 hidden lg:block mx-1"></div>

        <Button variant="ghost" size="icon" className="text-gray-500 hover:text-sr-text-blue relative">
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
          </svg>
          <span className="absolute top-2 right-2.5 w-2 h-2 rounded-full bg-red-500 ring-2 ring-white"></span>
        </Button>

        {/* Mobile Profile Avatar */}
        <div className="md:hidden ml-2 w-8 h-8 rounded-full bg-sr-mint text-sr-text-blue flex items-center justify-center font-bold text-xs">
          SJ
        </div>
      </div>
    </header>
  );
};
