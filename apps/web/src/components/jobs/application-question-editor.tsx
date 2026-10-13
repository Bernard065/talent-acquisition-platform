"use client";

import { useState, type FormEvent } from "react";
import {
  useJobApplicationQuestions,
  useReplaceJobApplicationQuestions,
} from "@/lib/api/hooks/jobs";
import type {
  ApplicationQuestionDefinition,
  ApplicationQuestionType,
} from "@/types/api/jobs";

const questionTypes: { value: ApplicationQuestionType; label: string }[] = [
  { value: "short_text", label: "Short answer" },
  { value: "long_text", label: "Long answer" },
  { value: "yes_no", label: "Yes or no" },
  { value: "single_choice", label: "Choose one" },
];

const controlClassName = "mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20 disabled:bg-gray-50";

export function ApplicationQuestionEditor({ jobPostingId }: { jobPostingId: string }) {
  const query = useJobApplicationQuestions(jobPostingId);
  const saveMutation = useReplaceJobApplicationQuestions();
  const [draft, setDraft] = useState<{
    version: number;
    items: ApplicationQuestionDefinition[];
  } | null>(null);
  const configuration = query.data;
  const questions = draft?.items ?? configuration?.items ?? [];
  const isStale = Boolean(draft && configuration && draft.version !== configuration.version);
  const questionsAreValid = questions.every((question) => {
    if (!question.prompt.trim()) return false;
    if (question.question_type !== "single_choice") return true;
    const options = question.options.map((option) => option.trim());
    return options.length >= 2
      && options.every(Boolean)
      && new Set(options.map((option) => option.toLocaleLowerCase())).size === options.length;
  });

  function updateQuestions(next: ApplicationQuestionDefinition[]) {
    if (!configuration || isStale) return;
    setDraft({
      version: draft?.version ?? configuration.version,
      items: next,
    });
  }

  function addQuestion() {
    const next: ApplicationQuestionDefinition = {
      id: crypto.randomUUID(),
      prompt: "",
      question_type: "short_text",
      is_required: false,
      options: [],
    };
    updateQuestions([...questions, next]);
  }

  function moveQuestion(index: number, offset: -1 | 1) {
    const targetIndex = index + offset;
    if (targetIndex < 0 || targetIndex >= questions.length) return;
    const reordered = [...questions];
    [reordered[index], reordered[targetIndex]] = [reordered[targetIndex], reordered[index]];
    updateQuestions(reordered);
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!configuration || !draft || isStale || saveMutation.isPending) return;
    saveMutation.mutate({
      id: jobPostingId,
      request: {
        expected_version: draft.version,
        questions: draft.items.map((question) => ({
          ...question,
          prompt: question.prompt.trim(),
          options: question.question_type === "single_choice"
            ? question.options.map((option) => option.trim())
            : [],
        })),
      },
      idempotencyKey: crypto.randomUUID(),
    }, { onSuccess: () => setDraft(null) });
  }

  return (
    <section aria-labelledby="application-question-editor-title" className="rounded-xl border border-gray-200 bg-white p-5 sm:p-8">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 id="application-question-editor-title" className="text-lg font-semibold text-sr-text-blue">
            Application questions
          </h2>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-gray-600">
            Ask up to 10 role-specific questions. Applicants’ answers are saved with their applications, including a snapshot of each question.
          </p>
        </div>
        {configuration && questions.length < 10 && (
          <button
            type="button"
            onClick={addQuestion}
            disabled={saveMutation.isPending || isStale}
            className="inline-flex h-10 shrink-0 items-center justify-center rounded-lg border border-gray-300 px-4 text-sm font-semibold text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60"
          >
            Add question
          </button>
        )}
      </div>

      {query.isLoading ? (
        <p className="mt-5 text-sm text-gray-500" role="status">Loading application questions…</p>
      ) : query.isError ? (
        <div className="mt-5" role="alert">
          <p className="text-sm text-rose-800">We couldn’t load application questions.</p>
          <button type="button" onClick={() => void query.refetch()} className="mt-2 text-sm font-semibold text-sr-text-blue underline">
            Try again
          </button>
        </div>
      ) : configuration ? (
        <form onSubmit={submit} className="mt-5">
          {isStale && (
            <div role="alert" className="mb-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
              These questions changed elsewhere. Reload the latest version before saving your edits.
              <button type="button" className="ml-2 font-semibold underline" onClick={() => setDraft(null)}>Reload</button>
            </div>
          )}

          {questions.length ? (
            <ol className="space-y-4">
              {questions.map((question, index) => (
                <li key={question.id} className="rounded-lg border border-gray-200 p-4">
                  <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_12rem]">
                    <label className="block text-sm font-medium text-gray-700">
                      Question {index + 1}
                      <input
                        value={question.prompt}
                        maxLength={300}
                        required
                        disabled={saveMutation.isPending || isStale}
                        onChange={(event) => updateQuestions(questions.map((item) =>
                          item.id === question.id ? { ...item, prompt: event.target.value } : item,
                        ))}
                        placeholder="e.g. What interests you about this role?"
                        className={controlClassName}
                      />
                    </label>
                    <label className="block text-sm font-medium text-gray-700">
                      Answer type
                      <select
                        value={question.question_type}
                        disabled={saveMutation.isPending || isStale}
                        onChange={(event) => {
                          const questionType = event.target.value as ApplicationQuestionType;
                          updateQuestions(questions.map((item) => item.id === question.id
                            ? { ...item, question_type: questionType, options: questionType === "single_choice" ? ["Option 1", "Option 2"] : [] }
                            : item,
                          ));
                        }}
                        className={controlClassName}
                      >
                        {questionTypes.map((type) => <option key={type.value} value={type.value}>{type.label}</option>)}
                      </select>
                    </label>
                  </div>

                  {question.question_type === "single_choice" && (
                    <label className="mt-4 block text-sm font-medium text-gray-700">
                      Answer options <span className="font-normal text-gray-500">(one per line, 2–10 options)</span>
                      <textarea
                        rows={3}
                        value={question.options.join("\n")}
                        disabled={saveMutation.isPending || isStale}
                        onChange={(event) => updateQuestions(questions.map((item) => item.id === question.id
                          ? { ...item, options: event.target.value.split("\n").slice(0, 10) }
                          : item,
                        ))}
                        className={controlClassName}
                      />
                      {question.options.map((option) => option.trim()).filter(Boolean).length < 2 && (
                        <span className="mt-1 block text-xs font-normal text-rose-700">Add at least two options.</span>
                      )}
                    </label>
                  )}

                  <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
                    <div className="flex flex-wrap items-center gap-4">
                      <label className="inline-flex cursor-pointer items-center gap-2 text-sm text-gray-700">
                        <input
                          type="checkbox"
                          checked={question.is_required}
                          disabled={saveMutation.isPending || isStale}
                          onChange={(event) => updateQuestions(questions.map((item) => item.id === question.id
                            ? { ...item, is_required: event.target.checked }
                            : item,
                          ))}
                          className="h-4 w-4 rounded border-gray-300 text-sr-green focus:ring-sr-green"
                        />
                        Required
                      </label>
                      <button type="button" onClick={() => moveQuestion(index, -1)} disabled={index === 0 || saveMutation.isPending || isStale} className="text-sm font-medium text-gray-600 underline disabled:cursor-not-allowed disabled:opacity-40">Move up</button>
                      <button type="button" onClick={() => moveQuestion(index, 1)} disabled={index === questions.length - 1 || saveMutation.isPending || isStale} className="text-sm font-medium text-gray-600 underline disabled:cursor-not-allowed disabled:opacity-40">Move down</button>
                    </div>
                    <button type="button" onClick={() => updateQuestions(questions.filter((item) => item.id !== question.id))} disabled={saveMutation.isPending || isStale} className="text-sm font-medium text-rose-700 underline hover:text-rose-900 disabled:cursor-not-allowed disabled:opacity-60">Remove</button>
                  </div>
                </li>
              ))}
            </ol>
          ) : (
            <div className="rounded-lg border border-dashed border-gray-300 bg-gray-50 p-5 text-sm text-gray-600">
              No extra application questions. Applicants will only be asked for their contact details and résumé.
            </div>
          )}

          {saveMutation.isError && (
            <p role="alert" className="mt-4 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
              We couldn’t save these questions. The posting may have changed; reload and try again.
            </p>
          )}
          {saveMutation.isSuccess && (
            <p role="status" className="mt-4 text-sm text-emerald-700">Application questions saved.</p>
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
                disabled={saveMutation.isPending || questions.length > 10 || !questionsAreValid}
                className="h-10 rounded-lg bg-sr-text-blue px-5 text-sm font-semibold text-white hover:bg-sr-text-blue/90 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {saveMutation.isPending ? "Saving…" : "Save questions"}
              </button>
            </div>
          )}
        </form>
      ) : null}
    </section>
  );
}

