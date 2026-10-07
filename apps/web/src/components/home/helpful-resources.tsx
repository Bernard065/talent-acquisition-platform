import { ExtractedSvgIcon22 } from "@/components/icons";
import React from "react";
import Image from "next/image";
import Link from "next/link";

export const HelpfulResources = () => {
  return (
    <section className="w-full py-20 md:py-32 bg-[#F8FAFC]">
      <div className="max-w-305 mx-auto px-4 lg:px-4">

        {/* Header */}
        <div className="text-center max-w-2xl mx-auto mb-16">
          <p className="text-sm font-semibold uppercase tracking-widest text-sr-gray mb-4">
            Whether you&apos;re a seasoned recruiter or hiring your first employee,
          </p>
          <h2 className="text-4xl md:text-5xl font-display font-light text-sr-text-blue tracking-tight">
            We have helpful resources <strong className="font-bold">just for you.</strong>
          </h2>
        </div>

        {/* Resources Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mb-16">

          {/* Resource 1 */}
          <Link href="#" className="group relative rounded-3xl overflow-hidden block aspect-4/3 md:aspect-16/10 shadow-md hover:shadow-xl transition-shadow duration-300">
            <Image
              src="/images/resource-high-volume.jpg"
              alt="High-Volume Recruiting"
              fill
              sizes="(max-width: 768px) 100vw, 50vw"
              className="object-cover group-hover:scale-105 transition-transform duration-700"
            />
            {/* Gradient Overlay */}
            <div className="absolute inset-0 bg-linear-to-t from-sr-dark-gray/90 via-sr-dark-gray/40 to-transparent"></div>

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
                <ExtractedSvgIcon22 className="w-5 h-5 ml-2 transform group-hover:translate-x-1 transition-transform" />
              </div>
            </div>
          </Link>

          {/* Resource 2 */}
          <Link href="#" className="group relative rounded-3xl overflow-hidden block aspect-4/3 md:aspect-16/10 shadow-md hover:shadow-xl transition-shadow duration-300">
            <Image
              src="/images/resource-enterprise.jpg"
              alt="Enterprise Recruiting"
              fill
              sizes="(max-width: 768px) 100vw, 50vw"
              className="object-cover group-hover:scale-105 transition-transform duration-700"
            />
            {/* Gradient Overlay */}
            <div className="absolute inset-0 bg-linear-to-t from-sr-dark-gray/90 via-sr-dark-gray/40 to-transparent"></div>

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
                <ExtractedSvgIcon22 className="w-5 h-5 ml-2 transform group-hover:translate-x-1 transition-transform" />
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
