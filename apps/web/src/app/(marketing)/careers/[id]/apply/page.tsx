"use client";

import React, { useState, use } from "react";
import Link from "next/link";
import { mockJobs } from "@/lib/mock-jobs";
import { notFound } from "next/navigation";
import { ArrowLeft, UploadCloud, CheckCircle, Briefcase } from "lucide-react";

export default function ApplyPage({ params }: { params: Promise<{ id: string }> }) {
  const resolvedParams = use(params);
  const job = mockJobs.find((j) => j.id === resolvedParams.id);

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);
  
  const [formData, setFormData] = useState({
    firstName: "",
    lastName: "",
    email: "",
    phone: "",
    linkedin: "",
    portfolio: "",
    coverLetter: ""
  });

  if (!job) {
    notFound();
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    
    // Simulate API submission
    setTimeout(() => {
      setIsSubmitting(false);
      setIsSuccess(true);
    }, 1500);
  };

  if (isSuccess) {
    return (
      <div className="bg-gray-50 min-h-screen py-24 px-6 flex items-center justify-center">
        <div className="bg-white rounded-2xl border border-gray-200 shadow-lg p-10 max-w-md w-full text-center">
          <div className="w-20 h-20 bg-emerald-100 rounded-full flex items-center justify-center mx-auto mb-6">
            <CheckCircle className="w-10 h-10 text-emerald-600" />
          </div>
          <h2 className="text-2xl font-bold text-gray-900 mb-2">Application Submitted!</h2>
          <p className="text-gray-600 mb-8">
            Thank you for applying to the <strong>{job.title}</strong> role. Our team will review your application and get back to you soon.
          </p>
          <Link 
            href="/careers"
            className="inline-flex items-center justify-center w-full h-11 rounded-lg bg-sr-text-blue text-white font-bold hover:bg-sr-text-blue/90 transition-colors"
          >
            Back to Careers
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-gray-50 min-h-screen pb-24">
      <div className="max-w-3xl mx-auto px-6 pt-12">
        <Link href={`/careers/${job.id}`} className="inline-flex items-center gap-2 text-sm font-semibold text-gray-500 hover:text-sr-text-blue transition-colors mb-8">
          <ArrowLeft className="w-4 h-4" /> Back to Job Description
        </Link>
        
        <div className="mb-10">
          <h1 className="text-3xl font-bold text-gray-900 tracking-tight">Apply for {job.title}</h1>
          <p className="text-gray-500 mt-2 flex items-center gap-2">
            <Briefcase className="w-4 h-4" /> {job.department} • {job.location}
          </p>
        </div>

        <form onSubmit={handleSubmit} className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6 sm:p-10">
          
          {/* Resume Upload */}
          <div className="mb-10">
            <h3 className="text-lg font-bold text-gray-900 mb-4">Resume/CV *</h3>
            <div className="border-2 border-dashed border-gray-300 rounded-xl p-10 text-center hover:bg-gray-50 hover:border-sr-mint transition-colors cursor-pointer group">
              <UploadCloud className="w-10 h-10 text-gray-400 mx-auto mb-3 group-hover:text-sr-mint transition-colors" />
              <p className="text-sm font-semibold text-gray-900">Click to upload or drag and drop</p>
              <p className="text-xs text-gray-500 mt-1">PDF, DOCX, or TXT up to 5MB</p>
            </div>
          </div>

          <div className="h-px bg-gray-100 w-full mb-10" />

          {/* Personal Information */}
          <div className="mb-10">
            <h3 className="text-lg font-bold text-gray-900 mb-4">Personal Information</h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
              <div>
                <label className="text-sm font-medium text-gray-700 mb-1.5 block">First Name *</label>
                <input required type="text" className="h-11 px-4 rounded-lg border border-gray-200 w-full focus:border-sr-green outline-none" value={formData.firstName} onChange={(e) => setFormData({...formData, firstName: e.target.value})} />
              </div>
              <div>
                <label className="text-sm font-medium text-gray-700 mb-1.5 block">Last Name *</label>
                <input required type="text" className="h-11 px-4 rounded-lg border border-gray-200 w-full focus:border-sr-green outline-none" value={formData.lastName} onChange={(e) => setFormData({...formData, lastName: e.target.value})} />
              </div>
              <div>
                <label className="text-sm font-medium text-gray-700 mb-1.5 block">Email *</label>
                <input required type="email" className="h-11 px-4 rounded-lg border border-gray-200 w-full focus:border-sr-green outline-none" value={formData.email} onChange={(e) => setFormData({...formData, email: e.target.value})} />
              </div>
              <div>
                <label className="text-sm font-medium text-gray-700 mb-1.5 block">Phone Number *</label>
                <input required type="tel" className="h-11 px-4 rounded-lg border border-gray-200 w-full focus:border-sr-green outline-none" value={formData.phone} onChange={(e) => setFormData({...formData, phone: e.target.value})} />
              </div>
            </div>
          </div>

          <div className="h-px bg-gray-100 w-full mb-10" />

          {/* Links */}
          <div className="mb-10">
            <h3 className="text-lg font-bold text-gray-900 mb-4">Links</h3>
            <div className="space-y-6">
              <div>
                <label className="text-sm font-medium text-gray-700 mb-1.5 block">LinkedIn Profile</label>
                <input type="url" placeholder="https://linkedin.com/in/..." className="h-11 px-4 rounded-lg border border-gray-200 w-full focus:border-sr-green outline-none" value={formData.linkedin} onChange={(e) => setFormData({...formData, linkedin: e.target.value})} />
              </div>
              <div>
                <label className="text-sm font-medium text-gray-700 mb-1.5 block">Portfolio / Personal Website</label>
                <input type="url" placeholder="https://..." className="h-11 px-4 rounded-lg border border-gray-200 w-full focus:border-sr-green outline-none" value={formData.portfolio} onChange={(e) => setFormData({...formData, portfolio: e.target.value})} />
              </div>
            </div>
          </div>

          <div className="h-px bg-gray-100 w-full mb-10" />

          {/* Cover Letter */}
          <div className="mb-10">
            <h3 className="text-lg font-bold text-gray-900 mb-4">Cover Letter</h3>
            <div>
              <label className="text-sm font-medium text-gray-700 mb-1.5 block">Message</label>
              <textarea rows={6} placeholder="Tell us why you are a great fit for this role..." className="p-4 rounded-lg border border-gray-200 w-full focus:border-sr-green outline-none resize-none" value={formData.coverLetter} onChange={(e) => setFormData({...formData, coverLetter: e.target.value})} />
            </div>
          </div>

          <div className="pt-6 border-t border-gray-200">
            <button 
              type="submit" 
              disabled={isSubmitting}
              className={`w-full sm:w-auto px-10 h-12 rounded-lg font-bold text-lg transition-all flex items-center justify-center gap-2 ${
                isSubmitting ? "bg-sr-mint/70 text-sr-text-blue/70 cursor-not-allowed" : "bg-sr-mint text-sr-text-blue hover:bg-sr-green hover:text-white"
              }`}
            >
              {isSubmitting ? "Submitting..." : "Submit Application"}
            </button>
          </div>

        </form>
      </div>
    </div>
  );
}
