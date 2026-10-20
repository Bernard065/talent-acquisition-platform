import type { OnboardingTaskDocumentResponse } from "@/types/api/onboarding";

export interface OnboardingDocumentVersionGroup {
  current: OnboardingTaskDocumentResponse;
  previous: OnboardingTaskDocumentResponse[];
}

/** Group a task's uploaded documents into replacement chains, newest version first. */
export function groupOnboardingDocumentVersions(
  documents: readonly OnboardingTaskDocumentResponse[],
): OnboardingDocumentVersionGroup[] {
  const documentsById = new Map(documents.map((document) => [document.id, document]));
  const successorById = new Map<string, OnboardingTaskDocumentResponse>();
  for (const document of documents) {
    if (document.replaces_document_id && documentsById.has(document.replaces_document_id)) {
      successorById.set(document.replaces_document_id, document);
    }
  }

  const visited = new Set<string>();
  const groups: OnboardingDocumentVersionGroup[] = [];
  const roots = documents.filter(
    (document) =>
      !document.replaces_document_id ||
      !documentsById.has(document.replaces_document_id),
  );

  function addChain(root: OnboardingTaskDocumentResponse) {
    const versions: OnboardingTaskDocumentResponse[] = [];
    let current: OnboardingTaskDocumentResponse | undefined = root;
    while (current && !visited.has(current.id)) {
      versions.push(current);
      visited.add(current.id);
      current = successorById.get(current.id);
    }
    const latest = versions.at(-1);
    if (latest) {
      groups.push({ current: latest, previous: versions.slice(0, -1).reverse() });
    }
  }

  for (const root of roots) addChain(root);
  for (const document of documents) {
    if (!visited.has(document.id)) addChain(document);
  }

  return groups.sort((left, right) =>
    right.current.created_at.localeCompare(left.current.created_at),
  );
}
