import React from "react";
import Image from "next/image";
import Link from "next/link";
import { ArrowRight } from "lucide-react"; // Wait, lucide-react isn't installed. I'll use an SVG.

export const ProductBenefits = () => {
  return (
    <section className="w-full py-20 md:py-28 bg-[#F8FAFC]">
      <div className="max-w-[1220px] mx-auto px-4 lg:px-4">
        
        {/* Section Header */}
        <div className="text-center max-w-3xl mx-auto mb-16 md:mb-20">
          <h2 className="text-4xl md:text-5xl font-display font-light text-sr-text-blue mb-6 tracking-tight">
            Achieve more <strong className="font-bold">with less effort</strong>
          </h2>
          <p className="text-lg md:text-xl text-sr-gray leading-relaxed">
            With our simple, easy-to-use interface and powerful workflows, expect effortless efficiency and productivity gains.
          </p>
        </div>

        {/* Benefits Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 lg:gap-12">
          
          {/* Benefit 1 */}
          <div className="flex flex-col group">
            <div className="rounded-2xl overflow-hidden mb-8 shadow-sm group-hover:shadow-xl transition-shadow duration-300 border border-gray-100">
              <Image 
                src="/images/benefit-automation.jpg" 
                alt="Automated pipeline visualization" 
                width={400} 
                height={400}
                className="w-full h-auto object-cover group-hover:scale-105 transition-transform duration-500"
              />
            </div>
            <div className="flex flex-col flex-1 px-2">
              <h3 className="text-6xl md:text-7xl font-display font-bold text-sr-text-blue tracking-tighter mb-2">
                <span className="text-sr-green">70</span>%
              </h3>
              <p className="text-sm uppercase tracking-widest font-semibold text-sr-gray mb-4">
                Reduction
              </p>
              <p className="text-lg text-sr-text-blue leading-relaxed mb-8 flex-1">
                in time-to-hire by <strong className="font-semibold">streamlining the candidate experience</strong>.
              </p>
              <Link 
                href="#" 
                className="inline-flex items-center text-sr-text-blue font-semibold hover:text-sr-green transition-colors group/link"
              >
                Improve your time-to-hire
                <svg className="w-5 h-5 ml-2 transform group-hover/link:translate-x-1 transition-transform" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" fill="none">
                  <path d="M29.2938 16.8272C29.7956 16.3254 29.7956 15.5139 29.2938 15.0174L20.3248 6.04312C19.823 5.54129 19.0115 5.54129 18.515 6.04312C18.0185 6.54496 18.0132 7.35644 18.515 7.85293L25.2951 14.633H3.61478C2.90473 14.633 2.3335 15.2043 2.3335 15.9143C2.3335 16.6244 2.90473 17.1956 3.61478 17.1956H25.2951L18.515 23.9757C18.0132 24.4776 18.0132 25.289 18.515 25.7855C19.0168 26.282 19.8283 26.2874 20.3248 25.7855L29.2938 16.8272Z" fill="currentColor" />
                </svg>
              </Link>
            </div>
          </div>

          {/* Benefit 2 */}
          <div className="flex flex-col group">
            <div className="rounded-2xl overflow-hidden mb-8 shadow-sm group-hover:shadow-xl transition-shadow duration-300 border border-gray-100">
              <Image 
                src="/images/benefit-scheduling.jpg" 
                alt="Automated interview scheduling calendar" 
                width={400} 
                height={400}
                className="w-full h-auto object-cover group-hover:scale-105 transition-transform duration-500"
              />
            </div>
            <div className="flex flex-col flex-1 px-2">
              <h3 className="text-6xl md:text-7xl font-display font-bold text-sr-text-blue tracking-tighter mb-2">
                <span className="text-sr-green">97</span>%
              </h3>
              <p className="text-sm uppercase tracking-widest font-semibold text-sr-gray mb-4">
                Reduction
              </p>
              <p className="text-lg text-sr-text-blue leading-relaxed mb-8 flex-1">
                in scheduling administration work, <strong className="font-semibold">freeing resources</strong>.
              </p>
              <Link 
                href="#" 
                className="inline-flex items-center text-sr-text-blue font-semibold hover:text-sr-green transition-colors group/link"
              >
                Reduce your admin work
                <svg className="w-5 h-5 ml-2 transform group-hover/link:translate-x-1 transition-transform" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" fill="none">
                  <path d="M29.2938 16.8272C29.7956 16.3254 29.7956 15.5139 29.2938 15.0174L20.3248 6.04312C19.823 5.54129 19.0115 5.54129 18.515 6.04312C18.0185 6.54496 18.0132 7.35644 18.515 7.85293L25.2951 14.633H3.61478C2.90473 14.633 2.3335 15.2043 2.3335 15.9143C2.3335 16.6244 2.90473 17.1956 3.61478 17.1956H25.2951L18.515 23.9757C18.0132 24.4776 18.0132 25.289 18.515 25.7855C19.0168 26.282 19.8283 26.2874 20.3248 25.7855L29.2938 16.8272Z" fill="currentColor" />
                </svg>
              </Link>
            </div>
          </div>

          {/* Benefit 3 */}
          <div className="flex flex-col group">
            <div className="rounded-2xl overflow-hidden mb-8 shadow-sm group-hover:shadow-xl transition-shadow duration-300 border border-gray-100">
              <Image 
                src="/images/benefit-velocity.jpg" 
                alt="Hiring velocity charts" 
                width={400} 
                height={400}
                className="w-full h-auto object-cover group-hover:scale-105 transition-transform duration-500"
              />
            </div>
            <div className="flex flex-col flex-1 px-2">
              <h3 className="text-6xl md:text-7xl font-display font-bold text-sr-text-blue tracking-tighter mb-2">
                <span className="text-sr-green">50</span>%
              </h3>
              <p className="text-sm uppercase tracking-widest font-semibold text-sr-gray mb-4">
                Increase
              </p>
              <p className="text-lg text-sr-text-blue leading-relaxed mb-8 flex-1">
                in hiring velocity in <strong className="font-semibold">high-volume, high-turnover roles</strong>.
              </p>
              <Link 
                href="#" 
                className="inline-flex items-center text-sr-text-blue font-semibold hover:text-sr-green transition-colors group/link"
              >
                Speed up your hiring
                <svg className="w-5 h-5 ml-2 transform group-hover/link:translate-x-1 transition-transform" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" fill="none">
                  <path d="M29.2938 16.8272C29.7956 16.3254 29.7956 15.5139 29.2938 15.0174L20.3248 6.04312C19.823 5.54129 19.0115 5.54129 18.515 6.04312C18.0185 6.54496 18.0132 7.35644 18.515 7.85293L25.2951 14.633H3.61478C2.90473 14.633 2.3335 15.2043 2.3335 15.9143C2.3335 16.6244 2.90473 17.1956 3.61478 17.1956H25.2951L18.515 23.9757C18.0132 24.4776 18.0132 25.289 18.515 25.7855C19.0168 26.282 19.8283 26.2874 20.3248 25.7855L29.2938 16.8272Z" fill="currentColor" />
                </svg>
              </Link>
            </div>
          </div>

        </div>
      </div>
    </section>
  );
};
