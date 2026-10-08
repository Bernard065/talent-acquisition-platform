"use client";

import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { useUpdateRequisition } from "@/lib/api/hooks/requisitions";
import type { RequisitionResponse } from "@/types/api/requisitions";

interface RequisitionEditDialogProps {
  requisition: RequisitionResponse;
  onClose: () => void;
}

export function RequisitionEditDialog({ requisition, onClose }: RequisitionEditDialogProps) {
  const updateMutation = useUpdateRequisition();
  const [title, setTitle] = useState(requisition.title);
  const [department, setDepartment] = useState(requisition.department ?? "");
  const [location, setLocation] = useState(requisition.location ?? "");
  const [headcount, setHeadcount] = useState(requisition.headcount);
  const [description, setDescription] = useState(requisition.description ?? "");
  const [error, setError] = useState<string | null>(null);

  async function saveChanges(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    try {
      await updateMutation.mutateAsync({
        id: requisition.id,
        requisition: {
          title: title.trim(),
          department: department.trim() || null,
          location: location.trim() || null,
          headcount,
          description: description.trim() || null,
        },
        idempotencyKey: crypto.randomUUID(),
      });
      onClose();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "We couldn’t save the requisition changes.");
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" role="presentation">
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="edit-requisition-title"
        className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-xl bg-white shadow-xl"
      >
        <form onSubmit={(event) => void saveChanges(event)}>
          <div className="space-y-5 p-6 sm:p-8">
            <div>
              <h2 id="edit-requisition-title" className="text-lg font-semibold text-sr-text-blue">
                Edit requisition
              </h2>
              <p className="mt-1 text-sm text-gray-600">
                Update the request using the reviewer’s feedback, then submit it for approval again.
              </p>
            </div>

            <label className="grid gap-1.5 text-sm font-medium text-gray-700">
              Job title <span className="text-red-600">*</span>
              <input
                required
                maxLength={200}
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                disabled={updateMutation.isPending}
                className="h-11 rounded-lg border border-gray-200 px-3 font-normal text-gray-900 outline-none focus:border-sr-green focus:ring-1 focus:ring-sr-green"
              />
            </label>

            <div className="grid gap-5 sm:grid-cols-2">
              <label className="grid gap-1.5 text-sm font-medium text-gray-700">
                Department
                <input
                  maxLength={200}
                  value={department}
                  onChange={(event) => setDepartment(event.target.value)}
                  disabled={updateMutation.isPending}
                  className="h-11 rounded-lg border border-gray-200 px-3 font-normal text-gray-900 outline-none focus:border-sr-green focus:ring-1 focus:ring-sr-green"
                />
              </label>
              <label className="grid gap-1.5 text-sm font-medium text-gray-700">
                Location
                <input
                  maxLength={200}
                  value={location}
                  onChange={(event) => setLocation(event.target.value)}
                  disabled={updateMutation.isPending}
                  className="h-11 rounded-lg border border-gray-200 px-3 font-normal text-gray-900 outline-none focus:border-sr-green focus:ring-1 focus:ring-sr-green"
                />
              </label>
            </div>

            <label className="grid max-w-48 gap-1.5 text-sm font-medium text-gray-700">
              Number of openings
              <input
                type="number"
                min={1}
                max={10_000}
                value={headcount}
                onChange={(event) => setHeadcount(Number(event.target.value))}
                disabled={updateMutation.isPending}
                className="h-11 rounded-lg border border-gray-200 px-3 font-normal text-gray-900 outline-none focus:border-sr-green focus:ring-1 focus:ring-sr-green"
              />
            </label>

            <label className="grid gap-1.5 text-sm font-medium text-gray-700">
              Role description and requirements
              <textarea
                rows={7}
                maxLength={20_000}
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                disabled={updateMutation.isPending}
                className="resize-y rounded-lg border border-gray-200 p-3 font-normal text-gray-900 outline-none focus:border-sr-green focus:ring-1 focus:ring-sr-green"
              />
            </label>

            {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
          </div>

          <div className="flex flex-col-reverse gap-3 border-t border-gray-100 bg-gray-50 p-4 sm:flex-row sm:justify-end sm:px-8">
            <Button type="button" variant="outline" disabled={updateMutation.isPending} onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={updateMutation.isPending}>
              {updateMutation.isPending ? "Saving…" : "Save changes"}
            </Button>
          </div>
        </form>
      </section>
    </div>
  );
}
