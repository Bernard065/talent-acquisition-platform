import React from "react";
import Image from "next/image";
import { Button } from "@/components/ui/button";

export const CaseStudyHighlights = () => {
  return (
    <section className="w-full bg-sr-text-blue py-20 md:py-32 relative overflow-hidden">
      <div className="max-w-[1000px] mx-auto px-4 lg:px-4 relative z-10 text-center">
        
        {/* Client Logo */}
        <div className="mb-12 flex justify-center">
          <div className="w-32 md:w-48 opacity-80 mix-blend-screen mix-blend-plus-lighter">
            <Image 
              src="/images/client-logo-vanguard.jpg" 
              alt="Vanguard Solutions Logo" 
              width={200} 
              height={133}
              className="w-full h-auto grayscale invert contrast-200" 
            />
          </div>
        </div>

        {/* Highlight Metric / Quote */}
        <h2 className="text-4xl md:text-6xl font-display font-light text-white leading-tight mb-12 tracking-tight">
          Time to hire reduced from <br className="hidden md:block" />
          <strong className="font-bold text-sr-green">23 days to 9 days</strong>
        </h2>

        {/* CTA */}
        <Button 
          variant="outline" 
          className="text-white bg-transparent border-white/20 hover:bg-white/10 hover:text-white hover:border-white/40 h-14 px-8 rounded-full text-lg"
        >
          Read the full Vanguard story
        </Button>

      </div>

      {/* Decorative Blur */}
      <div className="absolute bottom-0 right-0 w-[600px] h-[600px] bg-sr-green/10 blur-[100px] rounded-full translate-x-1/3 translate-y-1/3 pointer-events-none"></div>
      <div className="absolute top-0 left-0 w-[400px] h-[400px] bg-blue-500/10 blur-[100px] rounded-full -translate-x-1/2 -translate-y-1/2 pointer-events-none"></div>
    </section>
  );
};
