"use client";
import { ExtractedSvgIcon02, ExtractedSvgIcon03, ExtractedSvgIcon04, ExtractedSvgIcon05 } from "@/components/icons";


import { useEffect, useState } from "react";
import Link from "next/link";
import { useSession } from "next-auth/react";
import { Button } from "@/components/ui/button";
import {
  useCandidates,
  useCandidateFilterOptions,
} from "@/lib/api/hooks/candidates";
import { CandidateFilters } from "@/components/candidates/candidate-filters";
import { useRouter } from "next/navigation";

const PAGE_SIZE = 50;

function getInitials(name: string): string {
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toLocaleUpperCase() ?? "")
    .join("");
}

function formatSource(source: string): string {
  return source.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export default function CandidatesPage() {
  const router = useRouter();
  const { status: sessionStatus } = useSession();
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedSearchQuery, setDebouncedSearchQuery] = useState("");
  const [source, setSource] = useState("");
  const [location, setLocation] = useState("");
  useEffect(() => {
    const timeout = window.setTimeout(
      () => setDebouncedSearchQuery(searchQuery),
      250,
    );
    return () => window.clearTimeout(timeout);
  }, [searchQuery]);

  const candidatesQuery = useCandidates({
    limit: PAGE_SIZE,
    query: debouncedSearchQuery.trim() || undefined,
    source: source || undefined,
    location: location || undefined,
  });
  const filterOptionsQuery = useCandidateFilterOptions();
  const candidates = candidatesQuery.data?.pages.flatMap((page) => page.items) ?? [];
  const sourceOptions = filterOptionsQuery.data?.sources ?? [];
  const locationOptions = filterOptionsQuery.data?.locations ?? [];
  const isLoading = sessionStatus !== "authenticated" || candidatesQuery.isLoading;
  const error = candidatesQuery.isError
    ? candidatesQuery.error instanceof Error
      ? candidatesQuery.error.message
      : "Could not load candidates."
    : null;
  const hasActiveFilters = Boolean(
    searchQuery.trim() || source.trim() || location.trim(),
  );

  const updateSearch = (value: string) => {
    setSearchQuery(value);
  };
  const updateSource = (value: string) => {
    setSource(value);
  };
  const updateLocation = (value: string) => {
    setLocation(value);
  };

  return (
    <div className="flex flex-col gap-6 max-w-[1600px] mx-auto w-full">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-sr-text-blue tracking-tight">Candidates</h1>
          <p className="text-sm text-gray-500 mt-1">
            Search and manage candidate profiles in this workspace
          </p>
        </div>
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 w-full sm:w-auto">
          <Button
            variant="outline"
            className="h-10 border-gray-200 text-gray-700 hover:bg-gray-50 hover:text-gray-900 w-full sm:w-auto"
          >
            Export CSV
          </Button>
          <Button
            variant="secondary"
            className="h-10 bg-sr-mint hover:bg-sr-green text-sr-text-blue hover:text-white transition-colors font-semibold gap-2 w-full sm:w-auto"
          >
            <ExtractedSvgIcon02 className="w-4 h-4" />
            Add Candidate
          </Button>
        </div>
      </div>

      {/* Filters */}
      <CandidateFilters
        onSearchChange={updateSearch}
        onSourceChange={updateSource}
        onLocationChange={updateLocation}
        searchQuery={searchQuery}
        source={source}
        location={location}
        sourceOptions={sourceOptions}
        locationOptions={locationOptions}
      />

      {/* Candidates List (Cards on Mobile, Table on Desktop) */}
      <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden flex flex-col">
        
        {/* Mobile View (Cards) */}
        <div className="block lg:hidden divide-y divide-gray-200">
          {isLoading ? (
            <p className="p-8 text-center text-sm text-gray-500" role="status">Loading candidates…</p>
          ) : error ? (
            <p className="p-8 text-center text-sm text-red-700" role="alert">{error}</p>
          ) : candidates.length > 0 ? (
            candidates.map((cand) => {
              const addedDate = new Date(cand.created_at).toLocaleDateString("en-US", {
                month: "short",
                day: "numeric",
              });
              const initials = getInitials(cand.full_name);

              return (
                <Link href={`/dashboard/candidates/${cand.id}`} key={cand.id} className="block p-4 hover:bg-gray-50 transition-colors">
                  <div className="flex items-start justify-between gap-3 mb-3">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-full bg-sr-mint text-sr-text-blue flex items-center justify-center font-bold text-sm shrink-0">
                        {initials || "?"}
                      </div>
                      <div className="flex flex-col">
                        <span className="font-semibold text-sr-text-blue hover:text-sr-green transition-colors">
                          {cand.full_name}
                        </span>
                        <span className="text-xs text-gray-500">{cand.email}</span>
                      </div>
                    </div>
                  </div>
                  
                  <div className="grid grid-cols-2 gap-3 mb-3">
                    <div>
                      <div className="text-xs text-gray-500 mb-0.5">Location</div>
                      <div className="text-sm font-medium text-gray-900 truncate">{cand.location || "Not provided"}</div>
                    </div>
                    <div>
                      <div className="text-xs text-gray-500 mb-0.5">Added</div>
                      <div className="text-sm text-gray-900">{addedDate}</div>
                    </div>
                  </div>

                  <div className="flex items-center justify-between mt-3 pt-3 border-t border-gray-100">
                    <span className="text-xs text-gray-500">Source: {formatSource(cand.source)}</span>
                    <span className="text-sr-text-blue hover:text-sr-green transition-colors text-sm font-medium flex items-center gap-1">
                      View
                      <ExtractedSvgIcon03 className="w-4 h-4" />
                    </span>
                  </div>
                </Link>
              );
            })
          ) : (
            <div className="p-8 text-center">
              <div className="mx-auto w-12 h-12 bg-gray-50 rounded-full flex items-center justify-center mb-3">
                <ExtractedSvgIcon04 className="w-6 h-6 text-gray-400" />
              </div>
              <h3 className="text-sm font-semibold text-sr-text-blue mb-1">
                {hasActiveFilters ? "No candidates found" : "No candidates yet"}
              </h3>
              <p className="text-sm text-gray-500">
                {hasActiveFilters
                  ? "Try a different name, source, or location."
                  : "There are no candidate profiles in this workspace yet. Add a candidate to start building your talent pool."}
              </p>
            </div>
          )}
        </div>

        {/* Desktop View (Table) */}
        <div className="hidden lg:block overflow-x-auto">
          <table className="w-full text-left text-sm whitespace-nowrap">
            <thead className="bg-gray-50 text-gray-500 border-b border-gray-200 font-medium">
              <tr>
                <th className="px-6 py-4 font-medium">Candidate</th>
                <th className="px-6 py-4 font-medium">Location</th>
                <th className="px-6 py-4 font-medium">Source</th>
                <th className="px-6 py-4 font-medium">Consent</th>
                <th className="px-6 py-4 font-medium">Added Date</th>
                <th className="px-6 py-4 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {!isLoading && !error && candidates.length > 0 ? (
                candidates.map((cand) => {
                  const addedDate = new Date(cand.created_at).toLocaleDateString("en-US", {
                    month: "short",
                    day: "numeric",
                    year: "numeric",
                  });
                  const initials = getInitials(cand.full_name);

                  return (
                    <tr 
                      key={cand.id} 
                      className="hover:bg-gray-50 transition-colors group cursor-pointer"
                      onClick={() => router.push(`/dashboard/candidates/${cand.id}`)}
                    >
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-3">
                          <div className="w-9 h-9 rounded-full bg-sr-mint text-sr-text-blue flex items-center justify-center font-bold text-xs shrink-0">
                            {initials || "?"}
                          </div>
                          <div className="flex flex-col min-w-0">
                            <span className="font-semibold text-sr-text-blue group-hover:text-sr-green transition-colors truncate">
                              {cand.full_name}
                            </span>
                            <span className="text-xs text-gray-500 truncate">{cand.email}</span>
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <span className="text-gray-900 font-medium">{cand.location || "Not provided"}</span>
                      </td>
                      <td className="px-6 py-4">
                        <span className="text-gray-700">{formatSource(cand.source)}</span>
                      </td>
                      <td className="px-6 py-4">
                        <span className="text-gray-500">{formatSource(cand.consent_status)}</span>
                      </td>
                      <td className="px-6 py-4 text-gray-500">
                        {addedDate}
                      </td>
                      <td className="px-6 py-4 text-right">
                        <button 
                          className="text-gray-400 hover:text-sr-text-blue transition-colors p-1"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <ExtractedSvgIcon05 className="w-5 h-5" />
                        </button>
                      </td>
                    </tr>
                  );
                })
              ) : isLoading ? (
                <tr><td colSpan={6} className="px-6 py-12 text-center text-gray-500" role="status">Loading candidates…</td></tr>
              ) : error ? (
                <tr><td colSpan={6} className="px-6 py-12 text-center text-red-700" role="alert">{error}</td></tr>
              ) : (
                <tr>
                  <td colSpan={6} className="px-6 py-12 text-center">
                    <div className="mx-auto w-12 h-12 bg-gray-50 rounded-full flex items-center justify-center mb-3">
                      <ExtractedSvgIcon04 className="w-6 h-6 text-gray-400" />
                    </div>
                    <h3 className="text-sm font-semibold text-sr-text-blue mb-1">
                      {hasActiveFilters ? "No candidates found" : "No candidates yet"}
                    </h3>
                    <p className="text-sm text-gray-500">
                      {hasActiveFilters
                        ? "Try adjusting your search or filters to find candidates."
                        : "There are no candidate profiles in this workspace yet. Add a candidate to start building your talent pool."}
                    </p>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {candidatesQuery.hasNextPage && !isLoading && !error && (
        <div className="flex justify-center pb-4">
          <Button
            type="button"
            variant="outline"
            onClick={() => void candidatesQuery.fetchNextPage()}
            disabled={candidatesQuery.isFetchingNextPage}
          >
            {candidatesQuery.isFetchingNextPage ? "Loading…" : "Load more candidates"}
          </Button>
        </div>
      )}
    </div>
  );
}
