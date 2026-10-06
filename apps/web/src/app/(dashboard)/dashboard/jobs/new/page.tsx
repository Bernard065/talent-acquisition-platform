"use client";

import React from "react";
import { JobCreationWizard } from "@/components/jobs/job-creation-wizard";

export default function NewJobPage() {
  return (
    <div className="flex flex-col gap-6 max-w-250 mx-auto w-full pb-10">
      <div>
        <h1 className="text-2xl font-bold text-sr-text-blue tracking-tight">Create requisition</h1>
        <p className="text-sm text-gray-500 mt-1">Request approval to hire for a new role.</p>
      </div>

      <JobCreationWizard />
    </div>
  );
}
