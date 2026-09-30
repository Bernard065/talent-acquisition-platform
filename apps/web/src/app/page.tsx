import React from "react";
import Image from "next/image";
import { Button } from "@/components/ui/button";
import { ProductBenefits } from "@/components/home/product-benefits";

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
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4 ml-1">
                    <path d="M8 5v14l11-7z" />
                  </svg>
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
                  <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M16 20V4a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/><rect width="20" height="14" x="2" y="6" rx="2"/></svg>
                  <span className="text-2xl font-bold font-display">Acme Corp</span>
                </div>
                <div className="flex items-center gap-3 text-gray-400 grayscale opacity-70 hover:opacity-100 transition-opacity">
                  <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/></svg>
                  <span className="text-2xl font-bold font-display">GlobalNet</span>
                </div>
                <div className="flex items-center gap-3 text-gray-400 grayscale opacity-70 hover:opacity-100 transition-opacity">
                  <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m2 7 4.41-4.41A2 2 0 0 1 7.83 2h8.34a2 2 0 0 1 1.42.59L22 7"/><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/><path d="M15 22v-4a2 2 0 0 0-2-2h-2a2 2 0 0 0-2 2v4"/><path d="M2 7h20"/><path d="M22 7v3a2 2 0 0 1-2 2v0a2.7 2.7 0 0 1-1.59-.63.7.7 0 0 0-.82 0A2.7 2.7 0 0 1 16 12a2.7 2.7 0 0 1-1.59-.63.7.7 0 0 0-.82 0A2.7 2.7 0 0 1 12 12a2.7 2.7 0 0 1-1.59-.63.7.7 0 0 0-.82 0A2.7 2.7 0 0 1 8 12a2.7 2.7 0 0 1-1.59-.63.7.7 0 0 0-.82 0A2.7 2.7 0 0 1 4 12a2 2 0 0 1-2-2V7"/></svg>
                  <span className="text-2xl font-bold font-display">ShopFront</span>
                </div>
                <div className="flex items-center gap-3 text-gray-400 grayscale opacity-70 hover:opacity-100 transition-opacity">
                  <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17.5 19c-1.5 0-2.5-2-2.5-2a3 3 0 0 1-2 0c0 0-1 2-2.5 2C9 19 8 18 8 17s1-2 2.5-2c0 0 1-2 2.5-2a3 3 0 0 1 2 0c1.5 0 2.5 2 2.5 2s-1 1-2.5 1Z"/><path d="M22 17c0-3-2-5-4-5-1-4-4-6-7-6S5 8 4 12c-2 0-4 2-4 5s2 4 4 4h16c2 0 2-2 2-4Z"/></svg>
                  <span className="text-2xl font-bold font-display">CloudSync</span>
                </div>
                <div className="flex items-center gap-3 text-gray-400 grayscale opacity-70 hover:opacity-100 transition-opacity">
                  <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="12 2 22 8.5 22 15.5 12 22 2 15.5 2 8.5 12 2"/><line x1="12" x2="12" y1="22" y2="12"/><line x1="22" x2="12" y1="8.5" y2="12"/><line x1="2" x2="12" y1="8.5" y2="12"/></svg>
                  <span className="text-2xl font-bold font-display">BlockChain</span>
                </div>
                <div className="flex items-center gap-3 text-gray-400 grayscale opacity-70 hover:opacity-100 transition-opacity">
                  <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 22h14a2 2 0 0 0 2-2V7l-5-5H6a2 2 0 0 0-2 2v4"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="m3 15 2 2 4-4"/></svg>
                  <span className="text-2xl font-bold font-display">DocuSign</span>
                </div>
              </React.Fragment>
            ))}
          </div>
        </div>
      </section>

      {/* Product Benefits Section */}
      <ProductBenefits />
    </div>
  );
};

export default HomePage;
