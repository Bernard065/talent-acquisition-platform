"use client";

import { useState, type FormEvent } from "react";
import {
  useJobScreeningRubric,
  useReplaceJobScreeningRubric,
} from "@/lib/api/hooks/jobs";
import type { ScreeningRubricCriterion } from "@/types/api/applications";

const fieldClassName = "mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20 disabled:bg-gray-50";

export function ScreeningRubricEditor({ jobPostingId }: { jobPostingId: string }) {
  const query = useJobScreeningRubric(jobPostingId);
  const saveMutation = useReplaceJobScreeningRubric();
  const [draft, setDraft] = useState<{
    version: number;
    items: ScreeningRubricCriterion[];
  } | null>(null);
  const rubric = draft?.items ?? query.data?.items ?? [];
  const isStale = Boolean(draft && query.data && draft.version !== query.data.version);
  const normalizedLabels = rubric.map((item) => item.criterion.trim().toLocaleLowerCase());
  const rubricIsValid = rubric.every((item) => item.criterion.trim())
    && new Set(normalizedLabels).size === normalizedLabels.length;

  function updateRubric(items: ScreeningRubricCriterion[]) {
    if (!query.data || isStale) return;
    setDraft({ version: draft?.version ?? query.data.version, items });
  }

  function addCriterion() {
    updateRubric([...rubric, {
      id: crypto.randomUUID(),
      criterion: "",
      guidance: null,
    }]);
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!query.data || !draft || isStale || saveMutation.isPending || !rubricIsValid) return;
    saveMutation.mutate({
      id: jobPostingId,
      request: {
        expected_version: draft.version,
        items: draft.items.map((item) => ({
          ...item,
          criterion: item.criterion.trim(),
          guidance: item.guidance?.trim() || null,
        })),
      },
      idempotencyKey: crypto.randomUUID(),
    }, { onSuccess: () => setDraft(null) });
  }

  return (
    <section aria-labelledby="screening-rubric-title" className="rounded-xl border border-gray-200 bg-white p-5 sm:p-8">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 id="screening-rubric-title" className="text-lg font-semibold text-sr-text-blue">
            Screening rubric
          </h2>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-gray-600">
            Set up to 10 shared criteria. Every reviewer will score candidates for this job against the same rubric.
          </p>
        </div>
        {query.data && rubric.length < 10 && (
          <button
            type="button"
            onClick={addCriterion}
            disabled={saveMutation.isPending || isStale}
            className="inline-flex h-10 shrink-0 items-center justify-center rounded-lg border border-gray-300 px-4 text-sm font-semibold text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60"
          >
            Add criterion
          </button>
        )}
      </div>

      {query.isLoading ? (
        <p className="mt-5 text-sm text-gray-500" role="status">Loading screening rubric…</p>
      ) : query.isError ? (
        <div className="mt-5" role="alert">
          <p className="text-sm text-rose-800">We couldn’t load the screening rubric.</p>
          <button type="button" onClick={() => void query.refetch()} className="mt-2 text-sm font-semibold text-sr-text-blue underline">
            Try again
          </button>
        </div>
      ) : query.data ? (
        <form onSubmit={submit} className="mt-5">
          {isStale && (
            <div role="alert" className="mb-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
              The rubric changed elsewhere. Reload the latest version before saving.
              <button type="button" className="ml-2 font-semibold underline" onClick={() => setDraft(null)}>Reload</button>
            </div>
          )}

          {rubric.length ? (
            <ol className="space-y-4">
              {rubric.map((item, index) => (
                <li key={item.id} className="rounded-lg border border-gray-200 p-4">
                  <label className="block text-sm font-medium text-gray-700">
                    Criterion {index + 1}
                    <input
                      value={item.criterion}
                      required
                      maxLength={200}
                      disabled={saveMutation.isPending || isStale}
                      onChange={(event) => updateRubric(rubric.map((current) => current.id === item.id
                        ? { ...current, criterion: event.target.value }
                        : current,
                      ))}
                      placeholder="e.g. Relevant product design experience"
                      className={fieldClassName}
                    />
                  </label>
                  <label className="mt-4 block text-sm font-medium text-gray-700">
                    Reviewer guidance <span className="font-normal text-gray-500">(optional)</span>
                    <textarea
                      value={item.guidance ?? ""}
                      maxLength={1000}
                      rows={2}
                      disabled={saveMutation.isPending || isStale}
                      onChange={(event) => updateRubric(rubric.map((current) => current.id === item.id
                        ? { ...current, guidance: event.target.value }
                        : current,
                      ))}
                      placeholder="What evidence should reviewers look for?"
                      className={fieldClassName}
                    />
                  </label>
                  <button
                    type="button"
                    onClick={() => updateRubric(rubric.filter((current) => current.id !== item.id))}
                    disabled={saveMutation.isPending || isStale}
                    className="mt-3 text-sm font-medium text-rose-700 underline hover:text-rose-900 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    Remove criterion
                  </button>
                </li>
              ))}
            </ol>
          ) : (
            <p className="rounded-lg border border-dashed border-gray-300 bg-gray-50 p-5 text-sm text-gray-600">
              No screening criteria are set. Add a rubric before reviewers submit screening assessments.
            </p>
          )}

          {saveMutation.isError && (
            <p role="alert" className="mt-4 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
              We couldn’t save the screening rubric. Reload the latest version and try again.
            </p>
          )}
          {saveMutation.isSuccess && (
            <p role="status" className="mt-4 text-sm text-emerald-700">Screening rubric saved.</p>
          )}

          {draft && !isStale && (
            <div className="mt-5 flex flex-wrap justify-end gap-3 border-t border-gray-100 pt-5">
              <button
                type="button"
                onClick={() => setDraft(null)}
                disabled={saveMutation.isPending}
                className="h-10 rounded-lg border border-gray-300 px-4 text-sm font-semibold text-gray-700 hover:bg-gray-50 disabled:opacity-60"
              >
                Discard changes
              </button>
              <button
                type="submit"
                disabled={saveMutation.isPending || !rubricIsValid}
                className="h-10 rounded-lg bg-sr-text-blue px-5 text-sm font-semibold text-white hover:bg-sr-text-blue/90 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {saveMutation.isPending ? "Saving…" : "Save rubric"}
              </button>
            </div>
          )}
        </form>
      ) : null}
    </section>
  );
}
