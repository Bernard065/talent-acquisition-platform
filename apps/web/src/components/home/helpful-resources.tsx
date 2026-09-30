import React from "react";
import Image from "next/image";
import Link from "next/link";
import { Button } from "@/components/ui/button";

export const HelpfulResources = () => {
  return (
    <section className="w-full py-20 md:py-32 bg-[#F8FAFC]">
      <div className="max-w-[1220px] mx-auto px-4 lg:px-4">
        
        {/* Header */}
        <div className="text-center max-w-2xl mx-auto mb-16">
          <p className="text-sm font-semibold uppercase tracking-widest text-sr-gray mb-4">
            Whether you're a seasoned recruiter or hiring your first employee,
          </p>
          <h2 className="text-4xl md:text-5xl font-display font-light text-sr-text-blue tracking-tight">
            We have helpful resources <strong className="font-bold">just for you.</strong>
          </h2>
        </div>

        {/* Resources Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mb-16">
          
          {/* Resource 1 */}
          <Link href="#" className="group relative rounded-3xl overflow-hidden block aspect-[4/3] md:aspect-[16/10] shadow-md hover:shadow-xl transition-shadow duration-300">
            <Image 
              src="/images/resource-high-volume.jpg" 
              alt="High-Volume Recruiting" 
              fill
              className="object-cover group-hover:scale-105 transition-transform duration-700"
            />
            {/* Gradient Overlay */}
            <div className="absolute inset-0 bg-gradient-to-t from-sr-dark-gray/90 via-sr-dark-gray/40 to-transparent"></div>
            
            {/* Content Overlay */}
            <div className="absolute inset-0 p-8 md:p-12 flex flex-col justify-end text-white">
              <h3 className="text-3xl md:text-4xl font-display font-bold mb-3">
                High-Volume Recruiting
              </h3>
              <p className="text-lg text-gray-200 mb-6 max-w-md">
                Expand your high velocity hiring skills and strategies.
              </p>
              <div className="inline-flex items-center text-white font-semibold group-hover:text-sr-green transition-colors">
                View Resources
                <svg className="w-5 h-5 ml-2 transform group-hover:translate-x-1 transition-transform" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" fill="none">
                  <path d="M29.2938 16.8272C29.7956 16.3254 29.7956 15.5139 29.2938 15.0174L20.3248 6.04312C19.823 5.54129 19.0115 5.54129 18.515 6.04312C18.0185 6.54496 18.0132 7.35644 18.515 7.85293L25.2951 14.633H3.61478C2.90473 14.633 2.3335 15.2043 2.3335 15.9143C2.3335 16.6244 2.90473 17.1956 3.61478 17.1956H25.2951L18.515 23.9757C18.0132 24.4776 18.0132 25.289 18.515 25.7855C19.0168 26.282 19.8283 26.2874 20.3248 25.7855L29.2938 16.8272Z" fill="currentColor" />
                </svg>
              </div>
            </div>
          </Link>

          {/* Resource 2 */}
          <Link href="#" className="group relative rounded-3xl overflow-hidden block aspect-[4/3] md:aspect-[16/10] shadow-md hover:shadow-xl transition-shadow duration-300">
            <Image 
              src="/images/resource-enterprise.jpg" 
              alt="Enterprise Recruiting" 
              fill
              className="object-cover group-hover:scale-105 transition-transform duration-700"
            />
            {/* Gradient Overlay */}
            <div className="absolute inset-0 bg-gradient-to-t from-sr-dark-gray/90 via-sr-dark-gray/40 to-transparent"></div>
            
            {/* Content Overlay */}
            <div className="absolute inset-0 p-8 md:p-12 flex flex-col justify-end text-white">
              <h3 className="text-3xl md:text-4xl font-display font-bold mb-3">
                Enterprise Recruiting
              </h3>
              <p className="text-lg text-gray-200 mb-6 max-w-md">
                Elevate your enterprise hiring to the next level.
              </p>
              <div className="inline-flex items-center text-white font-semibold group-hover:text-sr-green transition-colors">
                View Resources
                <svg className="w-5 h-5 ml-2 transform group-hover:translate-x-1 transition-transform" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" fill="none">
                  <path d="M29.2938 16.8272C29.7956 16.3254 29.7956 15.5139 29.2938 15.0174L20.3248 6.04312C19.823 5.54129 19.0115 5.54129 18.515 6.04312C18.0185 6.54496 18.0132 7.35644 18.515 7.85293L25.2951 14.633H3.61478C2.90473 14.633 2.3335 15.2043 2.3335 15.9143C2.3335 16.6244 2.90473 17.1956 3.61478 17.1956H25.2951L18.515 23.9757C18.0132 24.4776 18.0132 25.289 18.515 25.7855C19.0168 26.282 19.8283 26.2874 20.3248 25.7855L29.2938 16.8272Z" fill="currentColor" />
                </svg>
              </div>
            </div>
          </Link>
        </div>

        {/* Explore All CTA */}
        <div className="text-center">
          <Link href="#" className="inline-block text-sr-text-blue font-semibold hover:text-sr-green transition-colors border-b-2 border-transparent hover:border-sr-green pb-1">
            Explore All Recruiting Resources
          </Link>
        </div>

      </div>
    </section>
  );
};
