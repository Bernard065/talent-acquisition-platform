"use client";

import React, { useState } from "react";
import { Check, ChevronRight, Briefcase, FileText, Users, Send } from "lucide-react";
import { useRouter } from "next/navigation";

const STEPS = [
  { id: 1, title: "Job Details", icon: Briefcase },
  { id: 2, title: "Description", icon: FileText },
  { id: 3, title: "Hiring Team", icon: Users },
  { id: 4, title: "Review & Publish", icon: Send },
];

export const JobCreationWizard = () => {
  const router = useRouter();
  const [currentStep, setCurrentStep] = useState(1);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Form State
  const [formData, setFormData] = useState({
    title: "",
    department: "",
    location: "",
    type: "Full-time",
    experienceLevel: "",
    description: "",
    requirements: "",
    hiringManager: "",
    recruiter: "",
  });

  const handleNext = () => {
    if (currentStep < 4) setCurrentStep(currentStep + 1);
  };

  const handleBack = () => {
    if (currentStep > 1) setCurrentStep(currentStep - 1);
  };

  const handlePublish = () => {
    setIsSubmitting(true);
    // Simulate API call
    setTimeout(() => {
      setIsSubmitting(false);
      router.push("/dashboard/jobs");
    }, 1500);
  };

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm flex flex-col overflow-hidden">

      {/* Wizard Progress Bar */}
      <div className="bg-gray-50 border-b border-gray-200 px-6 py-4 flex items-center justify-between overflow-x-auto">
        <div className="flex items-center w-full min-w-150">
          {STEPS.map((step, index) => {
            const isCompleted = currentStep > step.id;
            const isActive = currentStep === step.id;

            return (
              <React.Fragment key={step.id}>
                {/* Step Item */}
                <div className="flex items-center gap-3">
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center font-bold text-xs shrink-0 transition-colors ${
                    isCompleted ? "bg-sr-green text-white" :
                    isActive ? "bg-sr-mint text-sr-text-blue border-2 border-sr-green" :
                    "bg-gray-200 text-gray-500"
                  }`}>
                    {isCompleted ? <Check className="w-4 h-4" /> : step.id}
                  </div>
                  <span className={`text-sm font-semibold whitespace-nowrap ${
                    isActive ? "text-sr-text-blue" :
                    isCompleted ? "text-gray-900" :
                    "text-gray-400"
                  }`}>
                    {step.title}
                  </span>
                </div>

                {/* Separator Line */}
                {index < STEPS.length - 1 && (
                  <div className="flex-1 mx-4 h-0.5 bg-gray-200">
                    <div
                      className={`h-full transition-all duration-300 ${isCompleted ? "bg-sr-green w-full" : "bg-gray-200 w-0"}`}
                    />
                  </div>
                )}
              </React.Fragment>
            );
          })}
        </div>
      </div>

      {/* Wizard Form Content */}
      <div className="p-6 sm:p-8 min-h-100">
        {currentStep === 1 && (
          <div className="space-y-6 animate-in fade-in slide-in-from-right-4 duration-300">
            <h2 className="text-xl font-bold text-sr-text-blue mb-4">Basic Job Details</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="md:col-span-2">
                <label className="text-sm font-medium text-gray-700 mb-1.5 block">Job Title *</label>
                <input
                  type="text"
                  placeholder="e.g. Senior Frontend Engineer"
                  className="h-11 px-4 rounded-lg border border-gray-200 w-full focus:border-sr-green focus:ring-1 focus:ring-sr-green outline-none transition-colors"
                  value={formData.title}
                  onChange={(e) => setFormData({...formData, title: e.target.value})}
                />
              </div>
              <div>
                <label className="text-sm font-medium text-gray-700 mb-1.5 block">Department *</label>
                <select
                  className="h-11 px-4 rounded-lg border border-gray-200 w-full focus:border-sr-green focus:ring-1 focus:ring-sr-green outline-none transition-colors appearance-none bg-white"
                  value={formData.department}
                  onChange={(e) => setFormData({...formData, department: e.target.value})}
                >
                  <option value="">Select Department</option>
                  <option value="Engineering">Engineering</option>
                  <option value="Product">Product</option>
                  <option value="Design">Design</option>
                  <option value="Marketing">Marketing</option>
                  <option value="Sales">Sales</option>
                </select>
              </div>
              <div>
                <label className="text-sm font-medium text-gray-700 mb-1.5 block">Location *</label>
                <input
                  type="text"
                  placeholder="e.g. San Francisco, CA or Remote"
                  className="h-11 px-4 rounded-lg border border-gray-200 w-full focus:border-sr-green focus:ring-1 focus:ring-sr-green outline-none transition-colors"
                  value={formData.location}
                  onChange={(e) => setFormData({...formData, location: e.target.value})}
                />
              </div>
              <div>
                <label className="text-sm font-medium text-gray-700 mb-1.5 block">Employment Type</label>
                <select
                  className="h-11 px-4 rounded-lg border border-gray-200 w-full focus:border-sr-green focus:ring-1 focus:ring-sr-green outline-none transition-colors appearance-none bg-white"
                  value={formData.type}
                  onChange={(e) => setFormData({...formData, type: e.target.value})}
                >
                  <option value="Full-time">Full-time</option>
                  <option value="Part-time">Part-time</option>
                  <option value="Contract">Contract</option>
                  <option value="Internship">Internship</option>
                </select>
              </div>
              <div>
                <label className="text-sm font-medium text-gray-700 mb-1.5 block">Experience Level</label>
                <select
                  className="h-11 px-4 rounded-lg border border-gray-200 w-full focus:border-sr-green focus:ring-1 focus:ring-sr-green outline-none transition-colors appearance-none bg-white"
                  value={formData.experienceLevel}
                  onChange={(e) => setFormData({...formData, experienceLevel: e.target.value})}
                >
                  <option value="">Select Level</option>
                  <option value="Entry Level">Entry Level</option>
                  <option value="Mid Level">Mid Level</option>
                  <option value="Senior">Senior</option>
                  <option value="Director">Director</option>
                  <option value="Executive">Executive</option>
                </select>
              </div>
            </div>
          </div>
        )}

        {currentStep === 2 && (
          <div className="space-y-6 animate-in fade-in slide-in-from-right-4 duration-300">
            <h2 className="text-xl font-bold text-sr-text-blue mb-4">Description & Requirements</h2>
            <div>
              <label className="text-sm font-medium text-gray-700 mb-1.5 block">Job Description</label>
              <textarea
                rows={5}
                placeholder="Describe the role, the team, and the impact..."
                className="p-4 rounded-lg border border-gray-200 w-full focus:border-sr-green focus:ring-1 focus:ring-sr-green outline-none transition-colors resize-none"
                value={formData.description}
                onChange={(e) => setFormData({...formData, description: e.target.value})}
              />
            </div>
            <div>
              <label className="text-sm font-medium text-gray-700 mb-1.5 block">Key Requirements (One per line)</label>
              <textarea
                rows={5}
                placeholder="- 5+ years of React experience&#10;- Strong communication skills..."
                className="p-4 rounded-lg border border-gray-200 w-full focus:border-sr-green focus:ring-1 focus:ring-sr-green outline-none transition-colors resize-none"
                value={formData.requirements}
                onChange={(e) => setFormData({...formData, requirements: e.target.value})}
              />
            </div>
          </div>
        )}

        {currentStep === 3 && (
          <div className="space-y-6 animate-in fade-in slide-in-from-right-4 duration-300">
            <h2 className="text-xl font-bold text-sr-text-blue mb-4">Hiring Team</h2>
            <p className="text-sm text-gray-500 mb-6">Assign the team members responsible for this role.</p>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <label className="text-sm font-medium text-gray-700 mb-1.5 block">Hiring Manager</label>
                <select
                  className="h-11 px-4 rounded-lg border border-gray-200 w-full focus:border-sr-green focus:ring-1 focus:ring-sr-green outline-none transition-colors appearance-none bg-white"
                  value={formData.hiringManager}
                  onChange={(e) => setFormData({...formData, hiringManager: e.target.value})}
                >
                  <option value="">Select Manager</option>
                  <option value="Alex Johnson">Alex Johnson (VP Eng)</option>
                  <option value="Sarah Chen">Sarah Chen (Design Lead)</option>
                  <option value="Michael Park">Michael Park (Product Lead)</option>
                </select>
              </div>
              <div>
                <label className="text-sm font-medium text-gray-700 mb-1.5 block">Lead Recruiter</label>
                <select
                  className="h-11 px-4 rounded-lg border border-gray-200 w-full focus:border-sr-green focus:ring-1 focus:ring-sr-green outline-none transition-colors appearance-none bg-white"
                  value={formData.recruiter}
                  onChange={(e) => setFormData({...formData, recruiter: e.target.value})}
                >
                  <option value="">Select Recruiter</option>
                  <option value="Bernard Bebeni">Bernard Bebeni (You)</option>
                  <option value="Emily Rodriguez">Emily Rodriguez</option>
                </select>
              </div>
            </div>
          </div>
        )}

        {currentStep === 4 && (
          <div className="space-y-6 animate-in fade-in slide-in-from-right-4 duration-300">
            <h2 className="text-xl font-bold text-sr-text-blue mb-4">Review & Publish</h2>

            <div className="bg-gray-50 border border-gray-200 rounded-xl p-6 space-y-6">
              <div className="border-b border-gray-200 pb-4">
                <h3 className="text-2xl font-bold text-gray-900">{formData.title || "Untitled Role"}</h3>
                <div className="flex flex-wrap items-center gap-4 mt-2 text-sm text-gray-600 font-medium">
                  <span className="flex items-center gap-1.5"><Briefcase className="w-4 h-4 text-gray-400" /> {formData.department || "No Department"}</span>
                  <span className="flex items-center gap-1.5">📍 {formData.location || "No Location"}</span>
                  <span className="flex items-center gap-1.5">⏱️ {formData.type}</span>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                <div>
                  <h4 className="text-sm font-bold text-gray-900 uppercase tracking-wider mb-2">Description</h4>
                  <p className="text-sm text-gray-600 whitespace-pre-line">
                    {formData.description || "No description provided."}
                  </p>
                </div>
                <div>
                  <h4 className="text-sm font-bold text-gray-900 uppercase tracking-wider mb-2">Team</h4>
                  <ul className="text-sm text-gray-600 space-y-2">
                    <li><strong>Manager:</strong> {formData.hiringManager || "Unassigned"}</li>
                    <li><strong>Recruiter:</strong> {formData.recruiter || "Unassigned"}</li>
                  </ul>
                </div>
              </div>
            </div>

            <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 flex items-start gap-3">
              <div className="mt-0.5 text-amber-500">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <p className="text-sm text-amber-800 font-medium">
                Publishing this job will immediately make it visible on your careers page and distribute it to connected job boards (LinkedIn, Indeed).
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Footer Controls */}
      <div className="bg-gray-50 border-t border-gray-200 p-4 sm:px-6 flex items-center justify-between">
        <button
          onClick={handleBack}
          disabled={currentStep === 1 || isSubmitting}
          className={`px-4 py-2 rounded-lg font-semibold text-sm transition-colors ${
            currentStep === 1 ? "text-gray-400 cursor-not-allowed" : "text-gray-700 hover:bg-gray-200 bg-gray-100"
          }`}
        >
          Back
        </button>

        {currentStep < 4 ? (
          <button
            onClick={handleNext}
            className="px-6 py-2 bg-sr-text-blue text-white hover:bg-sr-text-blue/90 rounded-lg font-semibold text-sm transition-colors flex items-center gap-2"
          >
            Continue <ChevronRight className="w-4 h-4" />
          </button>
        ) : (
          <button
            onClick={handlePublish}
            disabled={isSubmitting}
            className={`px-8 py-2 rounded-lg font-bold text-sm transition-all flex items-center gap-2 ${
              isSubmitting ? "bg-sr-green/70 text-white cursor-not-allowed" : "bg-sr-green text-white hover:bg-emerald-600 shadow-sm"
            }`}
          >
            {isSubmitting ? (
              <>
                <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                Publishing...
              </>
            ) : (
              <>
                <Send className="w-4 h-4" /> Publish Job
              </>
            )}
          </button>
        )}
      </div>
    </div>
  );
};
