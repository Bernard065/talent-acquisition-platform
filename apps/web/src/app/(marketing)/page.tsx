import { ExtractedSvgIcon11, ExtractedSvgIcon12, ExtractedSvgIcon13, ExtractedSvgIcon14, ExtractedSvgIcon15, ExtractedSvgIcon16, ExtractedSvgIcon17 } from "@/components/icons";
import React from "react";
import Image from "next/image";
import { Button } from "@/components/ui/button";
import { ProductBenefits } from "@/components/home/product-benefits";
import { PlatformEcosystem } from "@/components/home/platform-ecosystem";
import { AIAssistant } from "@/components/home/ai-assistant";
import { HelpfulResources } from "@/components/home/helpful-resources";
import { CaseStudyHighlights } from "@/components/home/case-study-highlights";

const HomePage = () => {
  return (
    <div className="w-full flex flex-col">
      {/* Hero Section */}
      <section className="relative w-full bg-sr-dark-gray overflow-hidden">
        <div className="max-w-305 mx-auto px-4 lg:px-4 py-20 md:py-32 flex flex-col md:flex-row items-center gap-12">

          {/* Left Content */}
          <div className="flex-1 text-center md:text-left z-10 flex flex-col gap-6 md:gap-8">
            <h1 className="text-5xl md:text-[64px] leading-[1.1] font-display font-bold text-white tracking-tight">
              <span className="text-sr-green">AI-Driven</span><br />
              Talent Platform Built for Growth
            </h1>

            <p className="text-lg md:text-xl text-gray-300 max-w-xl mx-auto md:mx-0 leading-relaxed">
              Smart recruitment software designed for modern teams. Streamline your hiring pipeline, attract top talent, and make data-backed decisions at any scale.
            </p>

            <div className="flex flex-col sm:flex-row items-center gap-4 mt-2 justify-center md:justify-start">
              <Button className="w-full sm:w-auto text-lg h-14 px-8">
                Explore the benefits
              </Button>
              <Button
                variant="ghost"
                className="w-full sm:w-auto text-lg h-14 px-8 text-white hover:text-white hover:bg-white/10 flex items-center gap-3 border border-transparent hover:border-white/20 transition-all rounded-full"
              >
                See how it works
                <div className="w-8 h-8 rounded-full bg-white/10 flex items-center justify-center">
                  <ExtractedSvgIcon11 className="w-4 h-4 ml-1" />
                </div>
              </Button>
            </div>
          </div>

          {/* Right Content / Hero Image */}
          <div className="flex-1 w-full relative z-10">
            <div className="relative w-full rounded-2xl shadow-2xl overflow-hidden">
              <Image
                src="/images/hero-dashboard.jpg"
                alt="MindHire dashboard showing candidate profiles, hiring pipeline, analytics charts, and welcome message"
                width={1200}
                height={900}
                className="w-full h-auto object-cover rounded-2xl"
                priority
              />
              {/* Decorative Glow */}
              <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full h-full bg-sr-green/15 blur-[80px] rounded-full pointer-events-none -z-10"></div>
            </div>
          </div>
        </div>

        {/* Background Decorative Graphic */}
        <div className="absolute top-0 right-0 w-1/2 h-full bg-sr-green/5 skew-x-12 translate-x-32 transform origin-top-right"></div>
      </section>

      {/* Trusted Logos Section */}
      <section className="w-full py-16 bg-white overflow-hidden border-b border-gray-100">
        <div className="max-w-305 mx-auto px-4 text-center mb-10">
          <h2 className="text-2xl text-sr-text-blue">
            Trusted by these <strong className="font-bold">industry leaders</strong> around the globe
          </h2>
        </div>

        {/* Infinite Scroll Logos */}
        <div className="relative w-full flex overflow-x-hidden group">
          <div className="flex gap-16 md:gap-24 items-center animate-scroll whitespace-nowrap pl-16 md:pl-24">
            {[1, 2].map((set) => (
              <React.Fragment key={set}>
                <div className="flex items-center gap-3 text-gray-400 grayscale opacity-70 hover:opacity-100 transition-opacity">
                  <ExtractedSvgIcon12 />
                  <span className="text-2xl font-bold font-display">Acme Corp</span>
                </div>
                <div className="flex items-center gap-3 text-gray-400 grayscale opacity-70 hover:opacity-100 transition-opacity">
                  <ExtractedSvgIcon13 />
                  <span className="text-2xl font-bold font-display">GlobalNet</span>
                </div>
                <div className="flex items-center gap-3 text-gray-400 grayscale opacity-70 hover:opacity-100 transition-opacity">
                  <ExtractedSvgIcon14 />
                  <span className="text-2xl font-bold font-display">ShopFront</span>
                </div>
                <div className="flex items-center gap-3 text-gray-400 grayscale opacity-70 hover:opacity-100 transition-opacity">
                  <ExtractedSvgIcon15 />
                  <span className="text-2xl font-bold font-display">CloudSync</span>
                </div>
                <div className="flex items-center gap-3 text-gray-400 grayscale opacity-70 hover:opacity-100 transition-opacity">
                  <ExtractedSvgIcon16 />
                  <span className="text-2xl font-bold font-display">BlockChain</span>
                </div>
                <div className="flex items-center gap-3 text-gray-400 grayscale opacity-70 hover:opacity-100 transition-opacity">
                  <ExtractedSvgIcon17 />
                  <span className="text-2xl font-bold font-display">DocuSign</span>
                </div>
              </React.Fragment>
            ))}
          </div>
        </div>
      </section>

      {/* Product Benefits Section */}
      <ProductBenefits />

      {/* Platform Ecosystem Section */}
      <PlatformEcosystem />

      {/* AI Assistant Section */}
      <AIAssistant />

      {/* Helpful Resources Section */}
      <HelpfulResources />

      {/* Case Study Highlights Section */}
      <CaseStudyHighlights />
    </div>
  );
};

export default HomePage;
