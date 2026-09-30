import React from "react";
import Image from "next/image";
import { Button } from "@/components/ui/button";

export const AIAssistant = () => {
  return (
    <section className="w-full py-20 md:py-32 bg-white relative overflow-hidden">
      <div className="max-w-305 mx-auto px-4 lg:px-4">

        <div className="flex flex-col md:flex-row items-center gap-12 lg:gap-20">

          {/* Left: Image */}
          <div className="flex-1 w-full relative group">
            {/* Background Glow */}
            <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[120%] h-[120%] bg-sr-mint/40 rounded-full blur-[80px] pointer-events-none transition-transform duration-700 group-hover:scale-110"></div>

            <div className="relative z-10 w-full rounded-3xl overflow-hidden shadow-2xl transition-transform duration-500 group-hover:-translate-y-2">
              <Image
                src="/images/ai-assistant.jpg"
                alt="Neural AI Assistant"
                width={800}
                height={800}
                className="w-full h-auto object-cover"
              />
            </div>
          </div>

          {/* Right: Copy */}
          <div className="flex-1 flex flex-col items-center md:items-start text-center md:text-left z-10">
            <h2 className="text-4xl md:text-[56px] leading-[1.1] font-display font-light text-sr-text-blue mb-6 tracking-tight">
              Hiring <strong className="font-bold text-sr-green">without</strong> the headaches
            </h2>
            <p className="text-lg md:text-xl text-sr-gray leading-relaxed mb-10 max-w-lg">
              Powered by AI, our all-new Neural Intelligence layer doesn’t just help you manage — it anticipates your needs, reduces admin work, and empowers you to focus on building the dream team.
            </p>
            <Button
              variant="secondary"
              className="font-semibold rounded-full h-14 px-10 text-lg bg-sr-mint text-sr-text-blue hover:bg-sr-green hover:text-white transition-colors group/btn flex items-center gap-2"
            >
              Meet Neural AI
              <svg className="w-5 h-5 ml-1 transform group-hover/btn:translate-x-1 transition-transform" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" fill="none">
                <path d="M29.2938 16.8272C29.7956 16.3254 29.7956 15.5139 29.2938 15.0174L20.3248 6.04312C19.823 5.54129 19.0115 5.54129 18.515 6.04312C18.0185 6.54496 18.0132 7.35644 18.515 7.85293L25.2951 14.633H3.61478C2.90473 14.633 2.3335 15.2043 2.3335 15.9143C2.3335 16.6244 2.90473 17.1956 3.61478 17.1956H25.2951L18.515 23.9757C18.0132 24.4776 18.0132 25.289 18.515 25.7855C19.0168 26.282 19.8283 26.2874 20.3248 25.7855L29.2938 16.8272Z" fill="currentColor" />
              </svg>
            </Button>
          </div>

        </div>
      </div>
    </section>
  );
};
