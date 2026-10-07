import { InlineSvgIcon005, InlineSvgIcon006 } from "@/components/icons";
import React, { useState } from "react";

export const ProfileTab = () => {
  const [isSavedFeedback, setIsSavedFeedback] = useState(false);

  const handleSave = () => {
    setIsSavedFeedback(true);
    setTimeout(() => setIsSavedFeedback(false), 2000);
  };

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      <div className="p-6 border-b border-gray-100 flex items-center gap-5">
        <div className="w-16 h-16 rounded-full bg-sr-mint text-sr-text-blue flex items-center justify-center font-bold text-2xl shrink-0">
          BB
        </div>
        <div>
          <h2 className="text-xl font-bold text-sr-text-blue">Bernard Bebeni</h2>
          <p className="text-sm text-gray-500 mt-1">Head of Talent Acquisition • Acme Corp</p>
        </div>
      </div>
      <div className="p-6 sm:p-8">
        <form className="grid grid-cols-1 md:grid-cols-2 gap-6" onSubmit={(e) => { e.preventDefault(); handleSave(); }}>
          <div>
            <label className="text-sm font-medium text-gray-700 mb-1.5 block">First Name</label>
            <input type="text" defaultValue="Bernard" className="h-11 px-4 rounded-lg border border-gray-200 bg-white text-gray-900 placeholder-gray-400 focus:border-sr-green focus:ring-1 focus:ring-sr-green outline-none transition-colors w-full" />
          </div>
          <div>
            <label className="text-sm font-medium text-gray-700 mb-1.5 block">Last Name</label>
            <input type="text" defaultValue="Bebeni" className="h-11 px-4 rounded-lg border border-gray-200 bg-white text-gray-900 placeholder-gray-400 focus:border-sr-green focus:ring-1 focus:ring-sr-green outline-none transition-colors w-full" />
          </div>
          <div className="md:col-span-2 relative">
            <label className="text-sm font-medium text-gray-700 mb-1.5 block">Email Address</label>
            <div className="relative">
              <input type="email" defaultValue="bernard@acmecorp.com" disabled className="h-11 pl-10 pr-4 rounded-lg border border-gray-200 bg-gray-50 text-gray-500 w-full cursor-not-allowed" />
              <InlineSvgIcon005 className="w-4 h-4 text-gray-400 absolute left-3.5 top-3.5" />
            </div>
            <p className="text-xs text-gray-400 mt-1.5">Email cannot be changed directly. Contact IT support.</p>
          </div>
          <div>
            <label className="text-sm font-medium text-gray-700 mb-1.5 block">Job Title</label>
            <input type="text" defaultValue="Head of Talent Acquisition" className="h-11 px-4 rounded-lg border border-gray-200 bg-white text-gray-900 placeholder-gray-400 focus:border-sr-green focus:ring-1 focus:ring-sr-green outline-none transition-colors w-full" />
          </div>
          <div>
            <label className="text-sm font-medium text-gray-700 mb-1.5 block">Company</label>
            <input type="text" defaultValue="Acme Corp" disabled className="h-11 px-4 rounded-lg border border-gray-200 bg-gray-50 text-gray-500 w-full cursor-not-allowed" />
          </div>
          <div className="md:col-span-2">
            <label className="text-sm font-medium text-gray-700 mb-1.5 block">Timezone</label>
            <select className="h-11 px-4 rounded-lg border border-gray-200 bg-white text-gray-900 focus:border-sr-green focus:ring-1 focus:ring-sr-green outline-none transition-colors w-full appearance-none">
              <option>Africa/Nairobi (UTC+3)</option>
              <option>Europe/London (UTC+0)</option>
              <option>America/New_York (UTC-5)</option>
              <option>America/Los_Angeles (UTC-8)</option>
            </select>
          </div>
          <div className="md:col-span-2 flex justify-end mt-4 pt-6 border-t border-gray-100">
            <button type="submit" className={`h-11 px-6 rounded-lg font-semibold transition-all flex items-center gap-2 ${isSavedFeedback ? "bg-green-500 text-white" : "bg-sr-mint text-sr-text-blue hover:bg-sr-green hover:text-white"}`}>
              {isSavedFeedback ? (
                <>
                  <InlineSvgIcon006 className="w-5 h-5" />
                  Saved!
                </>
              ) : (
                "Save Changes"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
