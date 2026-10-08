"use client";

import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import {
  createCandidate,
  getCandidate,
  getCandidateFilterOptions,
  getCandidateTalentPoolConsentState,
  listCandidates,
  requestCandidateErasure,
  grantCandidateTalentPoolConsent,
  renewCandidateTalentPoolConsent,
  withdrawCandidateTalentPoolConsent,
  withdrawCandidateConsent,
  type CandidateSearchParams,
} from "../services/candidates";
import type {
  CandidateCreateRequest,
  CandidatePrivacyOperationResponse,
  CandidateTalentPoolConsentGrantRequest,
  CandidateTalentPoolConsentResponse,
  CandidateTalentPoolConsentWithdrawalRequest,
} from "@/types/api";

export const candidateQueryKeys = {
  all: ["candidates"] as const,
  lists: () => [...candidateQueryKeys.all, "list"] as const,
  list: (params: CandidateSearchParams = {}) =>
    [...candidateQueryKeys.lists(), params] as const,
  filterOptions: () => [...candidateQueryKeys.all, "filter-options"] as const,
  detail: (id: string) => [...candidateQueryKeys.all, "detail", id] as const,
  talentPoolConsent: (id: string) => [...candidateQueryKeys.all, "talent-pool-consent", id] as const,
};

export type TalentPoolConsentMutationVariables<TBody> = {
  id: string;
  body: TBody;
  idempotencyKey: string;
};

export function useCandidates(params: CandidateSearchParams = {}) {
  const { status } = useSession();

  return useInfiniteQuery({
    queryKey: candidateQueryKeys.list(params),
    queryFn: ({ pageParam, signal }) =>
      listCandidates(
        { ...params, cursor: pageParam },
        { signal },
      ),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: status === "authenticated",
  });
}

export function useCandidateFilterOptions() {
  const { status } = useSession();

  return useQuery({
    queryKey: candidateQueryKeys.filterOptions(),
    queryFn: ({ signal }) => getCandidateFilterOptions({ signal }),
    enabled: status === "authenticated",
  });
}

export function useCandidate(id: string) {
  const { status } = useSession();

  return useQuery({
    queryKey: candidateQueryKeys.detail(id),
    queryFn: ({ signal }) => getCandidate(id, { signal }),
    enabled: status === "authenticated" && Boolean(id),
  });
}

export function useCandidateTalentPoolConsentState(id: string) {
  const { status } = useSession();

  return useQuery({
    queryKey: candidateQueryKeys.talentPoolConsent(id),
    queryFn: ({ signal }) => getCandidateTalentPoolConsentState(id, { signal }),
    enabled: status === "authenticated" && Boolean(id),
  });
}

export function useCreateCandidate() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      candidate,
      idempotencyKey,
    }: {
      candidate: CandidateCreateRequest;
      idempotencyKey: string;
    }) => createCandidate(candidate, idempotencyKey),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: candidateQueryKeys.lists() }),
        queryClient.invalidateQueries({ queryKey: candidateQueryKeys.filterOptions() }),
      ]);
    },
  });
}

export function useRequestCandidateErasure() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      id,
      idempotencyKey,
    }: {
      id: string;
      idempotencyKey: string;
    }) => requestCandidateErasure(id, idempotencyKey),
    onSuccess: async (_result, { id }) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: candidateQueryKeys.lists() }),
        queryClient.invalidateQueries({ queryKey: candidateQueryKeys.filterOptions() }),
      ]);
      queryClient.removeQueries({ queryKey: candidateQueryKeys.detail(id), exact: true });
      queryClient.removeQueries({ queryKey: candidateQueryKeys.talentPoolConsent(id), exact: true });
    },
  });
}

function useTalentPoolConsentMutation<
  TBody extends CandidateTalentPoolConsentGrantRequest | CandidateTalentPoolConsentWithdrawalRequest,
>(
  mutationFn: (id: string, body: TBody, idempotencyKey: string) => Promise<CandidateTalentPoolConsentResponse>,
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, body, idempotencyKey }: TalentPoolConsentMutationVariables<TBody>) =>
      mutationFn(id, body, idempotencyKey),
    onSuccess: async (_result, { id }) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: candidateQueryKeys.lists() }),
        queryClient.invalidateQueries({ queryKey: candidateQueryKeys.detail(id) }),
        queryClient.invalidateQueries({ queryKey: candidateQueryKeys.talentPoolConsent(id) }),
      ]);
    },
  });
}

export function useGrantCandidateTalentPoolConsent() {
  return useTalentPoolConsentMutation(grantCandidateTalentPoolConsent);
}

export function useRenewCandidateTalentPoolConsent() {
  return useTalentPoolConsentMutation(renewCandidateTalentPoolConsent);
}

export function useWithdrawCandidateTalentPoolConsent() {
  return useTalentPoolConsentMutation(withdrawCandidateTalentPoolConsent);
}

export function useWithdrawCandidateConsent() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      id,
      idempotencyKey,
    }: {
      id: string;
      idempotencyKey: string;
    }) => withdrawCandidateConsent(id, idempotencyKey),
    onSuccess: async (_result: CandidatePrivacyOperationResponse, { id }) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: candidateQueryKeys.lists() }),
        queryClient.invalidateQueries({ queryKey: candidateQueryKeys.detail(id) }),
      ]);
    },
  });
}
