"use client";
import { ExtractedSvgIcon02, ExtractedSvgIcon03, ExtractedSvgIcon04, ExtractedSvgIcon05 } from "@/components/icons";


import React, { useState, useMemo } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { mockCandidates } from "@/lib/mock-candidates";
import type { CandidateStage } from "@/lib/mock-candidates";
import { CandidateFilters } from "@/components/candidates/candidate-filters";
import { CandidateStageBadge } from "@/components/candidates/candidate-stage-badge";

import { useRouter } from "next/navigation";

export default function CandidatesPage() {
  const router = useRouter();
  const [activeStage, setActiveStage] = useState<CandidateStage | "all">("all");
  const [activeDepartment, setActiveDepartment] = useState("All Departments");
  const [searchQuery, setSearchQuery] = useState("");

  const filteredCandidates = useMemo(() => {
    return mockCandidates.filter((cand) => {
      const matchesStage = activeStage === "all" || cand.stage === activeStage;
      const matchesDepartment =
        activeDepartment === "All Departments" || cand.department === activeDepartment;
      const matchesSearch =
        searchQuery === "" ||
        cand.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        cand.email.toLowerCase().includes(searchQuery.toLowerCase()) ||
        cand.role.toLowerCase().includes(searchQuery.toLowerCase());
      return matchesStage && matchesDepartment && matchesSearch;
    });
  }, [activeStage, activeDepartment, searchQuery]);

  return (
    <div className="flex flex-col gap-6 max-w-[1600px] mx-auto w-full">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-sr-text-blue tracking-tight">Candidates</h1>
          <p className="text-sm text-gray-500 mt-1">
            Review and manage all applicants across open positions
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
        onStageChange={setActiveStage}
        onDepartmentChange={setActiveDepartment}
        onSearchChange={setSearchQuery}
        activeStage={activeStage}
        activeDepartment={activeDepartment}
        searchQuery={searchQuery}
        totalCount={mockCandidates.length}
        filteredCount={filteredCandidates.length}
      />

      {/* Candidates List (Cards on Mobile, Table on Desktop) */}
      <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden flex flex-col">
        
        {/* Mobile View (Cards) */}
        <div className="block lg:hidden divide-y divide-gray-200">
          {filteredCandidates.length > 0 ? (
            filteredCandidates.map((cand) => {
              const appliedDate = new Date(cand.appliedDate).toLocaleDateString("en-US", {
                month: "short",
                day: "numeric",
              });

              return (
                <Link href={`/dashboard/candidates/${cand.id}`} key={cand.id} className="block p-4 hover:bg-gray-50 transition-colors">
                  <div className="flex items-start justify-between gap-3 mb-3">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-full bg-sr-mint text-sr-text-blue flex items-center justify-center font-bold text-sm shrink-0">
                        {cand.initials}
                      </div>
                      <div className="flex flex-col">
                        <span className="font-semibold text-sr-text-blue hover:text-sr-green transition-colors">
                          {cand.name}
                        </span>
                        <span className="text-xs text-gray-500">{cand.email}</span>
                      </div>
                    </div>
                    <CandidateStageBadge stage={cand.stage} />
                  </div>
                  
                  <div className="grid grid-cols-2 gap-3 mb-3">
                    <div>
                      <div className="text-xs text-gray-500 mb-0.5">Role</div>
                      <div className="text-sm font-medium text-gray-900 truncate">{cand.role}</div>
                    </div>
                    <div>
                      <div className="text-xs text-gray-500 mb-0.5">Applied</div>
                      <div className="text-sm text-gray-900">{appliedDate}</div>
                    </div>
                  </div>

                  <div className="flex items-center justify-between mt-3 pt-3 border-t border-gray-100">
                    <div className="flex items-center gap-2">
                      <div className="w-20 h-1.5 bg-gray-100 rounded-full overflow-hidden shrink-0">
                        <div 
                          className={`h-full rounded-full ${cand.matchScore >= 80 ? 'bg-green-500' : cand.matchScore >= 60 ? 'bg-amber-500' : 'bg-red-500'}`}
                          style={{ width: `${cand.matchScore}%` }}
                        />
                      </div>
                      <span className="text-xs font-medium text-gray-700">{cand.matchScore}% Match</span>
                    </div>
                    <button className="text-sr-text-blue hover:text-sr-green transition-colors text-sm font-medium flex items-center gap-1">
                      View
                      <ExtractedSvgIcon03 className="w-4 h-4" />
                    </button>
                  </div>
                </Link>
              );
            })
          ) : (
            <div className="p-8 text-center">
              <div className="mx-auto w-12 h-12 bg-gray-50 rounded-full flex items-center justify-center mb-3">
                <ExtractedSvgIcon04 className="w-6 h-6 text-gray-400" />
              </div>
              <h3 className="text-sm font-semibold text-sr-text-blue mb-1">No candidates found</h3>
              <p className="text-sm text-gray-500">Adjust filters to find candidates.</p>
            </div>
          )}
        </div>

        {/* Desktop View (Table) */}
        <div className="hidden lg:block overflow-x-auto">
          <table className="w-full text-left text-sm whitespace-nowrap">
            <thead className="bg-gray-50 text-gray-500 border-b border-gray-200 font-medium">
              <tr>
                <th className="px-6 py-4 font-medium">Candidate</th>
                <th className="px-6 py-4 font-medium">Role</th>
                <th className="px-6 py-4 font-medium">Stage</th>
                <th className="px-6 py-4 font-medium">Match Score</th>
                <th className="px-6 py-4 font-medium">Applied Date</th>
                <th className="px-6 py-4 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {filteredCandidates.length > 0 ? (
                filteredCandidates.map((cand) => {
                  const appliedDate = new Date(cand.appliedDate).toLocaleDateString("en-US", {
                    month: "short",
                    day: "numeric",
                    year: "numeric",
                  });

                  return (
                    <tr 
                      key={cand.id} 
                      className="hover:bg-gray-50 transition-colors group cursor-pointer"
                      onClick={() => router.push(`/dashboard/candidates/${cand.id}`)}
                    >
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-3">
                          <div className="w-9 h-9 rounded-full bg-sr-mint text-sr-text-blue flex items-center justify-center font-bold text-xs shrink-0">
                            {cand.initials}
                          </div>
                          <div className="flex flex-col min-w-0">
                            <span className="font-semibold text-sr-text-blue group-hover:text-sr-green transition-colors truncate">
                              {cand.name}
                            </span>
                            <span className="text-xs text-gray-500 truncate">{cand.email}</span>
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex flex-col min-w-0">
                          <span className="text-gray-900 font-medium truncate">{cand.role}</span>
                          <span className="text-xs text-gray-500 truncate">{cand.department}</span>
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <CandidateStageBadge stage={cand.stage} />
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-2">
                          <div className="w-16 h-1.5 bg-gray-100 rounded-full overflow-hidden shrink-0">
                            <div 
                              className={`h-full rounded-full ${cand.matchScore >= 80 ? 'bg-green-500' : cand.matchScore >= 60 ? 'bg-amber-500' : 'bg-red-500'}`}
                              style={{ width: `${cand.matchScore}%` }}
                            />
                          </div>
                          <span className="text-sm font-medium text-gray-700">{cand.matchScore}%</span>
                        </div>
                      </td>
                      <td className="px-6 py-4 text-gray-500">
                        {appliedDate}
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
              ) : (
                <tr>
                  <td colSpan={6} className="px-6 py-12 text-center">
                    <div className="mx-auto w-12 h-12 bg-gray-50 rounded-full flex items-center justify-center mb-3">
                      <ExtractedSvgIcon04 className="w-6 h-6 text-gray-400" />
                    </div>
                    <h3 className="text-sm font-semibold text-sr-text-blue mb-1">No candidates found</h3>
                    <p className="text-sm text-gray-500">
                      Try adjusting your search or filters to find what you&apos;re looking for.
                    </p>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Results count on mobile */}
      <div className="text-sm text-gray-500 text-center lg:hidden pb-4">
        Showing {filteredCandidates.length} of {mockCandidates.length} candidates
      </div>
    </div>
  );
}
