"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { createRequisition } from "@/lib/api/services/requisitions";

export const JobCreationWizard = () => {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [department, setDepartment] = useState("");
  const [location, setLocation] = useState("");
  const [headcount, setHeadcount] = useState(1);
  const [description, setDescription] = useState("");
  const [requirements, setRequirements] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);

    const fullDescription = [
      description.trim(),
      requirements.trim() ? `Requirements\n${requirements.trim()}` : "",
    ].filter(Boolean).join("\n\n");

    try {
      await createRequisition({
        title: title.trim(),
        department: department.trim() || null,
        location: location.trim() || null,
        headcount,
        description: fullDescription || null,
      }, crypto.randomUUID());
      router.push("/dashboard/requisitions");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "We couldn’t create this requisition.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="rounded-xl border border-gray-200 bg-white shadow-sm">
      <div className="space-y-6 p-6 sm:p-8">
        <div>
          <h2 className="text-lg font-semibold text-sr-text-blue">Role details</h2>
          <p className="mt-1 text-sm text-gray-500">
            Create a requisition for review. An approved requisition can be turned into a job posting.
          </p>
        </div>

        <div className="grid gap-5 sm:grid-cols-2">
          <label className="grid gap-1.5 text-sm font-medium text-gray-700 sm:col-span-2">
            Job title <span className="text-red-600">*</span>
            <input
              required
              maxLength={200}
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              className="h-11 rounded-lg border border-gray-200 px-3 font-normal text-gray-900 outline-none focus:border-sr-green focus:ring-1 focus:ring-sr-green"
              placeholder="e.g. Senior software engineer"
            />
          </label>
          <label className="grid gap-1.5 text-sm font-medium text-gray-700">
            Department
            <input
              maxLength={200}
              value={department}
              onChange={(event) => setDepartment(event.target.value)}
              className="h-11 rounded-lg border border-gray-200 px-3 font-normal text-gray-900 outline-none focus:border-sr-green focus:ring-1 focus:ring-sr-green"
            />
          </label>
          <label className="grid gap-1.5 text-sm font-medium text-gray-700">
            Location
            <input
              maxLength={200}
              value={location}
              onChange={(event) => setLocation(event.target.value)}
              className="h-11 rounded-lg border border-gray-200 px-3 font-normal text-gray-900 outline-none focus:border-sr-green focus:ring-1 focus:ring-sr-green"
              placeholder="City, country or remote"
            />
          </label>
          <label className="grid max-w-48 gap-1.5 text-sm font-medium text-gray-700">
            Number of hires
            <input
              type="number"
              min={1}
              max={1000}
              value={headcount}
              onChange={(event) => setHeadcount(Number(event.target.value))}
              className="h-11 rounded-lg border border-gray-200 px-3 font-normal text-gray-900 outline-none focus:border-sr-green focus:ring-1 focus:ring-sr-green"
            />
          </label>
          <div className="hidden sm:block" />
          <label className="grid gap-1.5 text-sm font-medium text-gray-700 sm:col-span-2">
            Role description
            <textarea
              rows={6}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              className="resize-y rounded-lg border border-gray-200 p-3 font-normal text-gray-900 outline-none focus:border-sr-green focus:ring-1 focus:ring-sr-green"
              placeholder="Describe the role, responsibilities, and team."
            />
          </label>
          <label className="grid gap-1.5 text-sm font-medium text-gray-700 sm:col-span-2">
            Requirements
            <textarea
              rows={4}
              value={requirements}
              onChange={(event) => setRequirements(event.target.value)}
              className="resize-y rounded-lg border border-gray-200 p-3 font-normal text-gray-900 outline-none focus:border-sr-green focus:ring-1 focus:ring-sr-green"
              placeholder="Add one requirement per line."
            />
          </label>
        </div>

        {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
      </div>

      <div className="flex flex-col-reverse gap-3 border-t border-gray-100 bg-gray-50 p-4 sm:flex-row sm:justify-end sm:px-8">
        <Button type="button" variant="outline" disabled={isSubmitting} onClick={() => router.push("/dashboard/requisitions")}>
          Cancel
        </Button>
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Creating…" : "Create requisition"}
        </Button>
      </div>
    </form>
  );
};
