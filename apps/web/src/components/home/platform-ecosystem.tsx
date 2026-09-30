import React from "react";
import Image from "next/image";
import { Button } from "@/components/ui/button";

export const PlatformEcosystem = () => {
  return (
    <section className="w-full py-20 md:py-32 bg-sr-dark-gray relative overflow-hidden">
      <div className="max-w-305 mx-auto px-4 lg:px-4 relative z-10">

        {/* Content */}
        <div className="flex flex-col items-center text-center max-w-4xl mx-auto mb-16">
          <h2 className="text-5xl md:text-7xl font-display font-bold text-white mb-6 tracking-tight">
            Mind<span className="text-sr-green">OS</span>
          </h2>
          <h3 className="text-2xl md:text-3xl text-gray-300 font-light mb-10 tracking-tight">
            The End-to-End Talent Operating System
          </h3>
          <Button className="h-14 px-10 text-lg rounded-full">
            Explore the platform
          </Button>
        </div>

        {/* Image */}
        <div className="w-full max-w-5xl mx-auto relative rounded-3xl overflow-hidden shadow-2xl">
          <Image
            src="/images/platform-ecosystem.jpg"
            alt="MindOS Platform Ecosystem Diagram"
            width={1200}
            height={675}
            className="w-full h-auto object-cover"
          />
          {/* Decorative Glow */}
          <div className="absolute inset-0 bg-linear-to-t from-sr-dark-gray via-transparent to-transparent opacity-80 pointer-events-none"></div>
        </div>

      </div>

      {/* Decorative Background Elements */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-200 h-200 bg-sr-green/10 rounded-full blur-[120px] pointer-events-none z-0"></div>
    </section>
  );
};
