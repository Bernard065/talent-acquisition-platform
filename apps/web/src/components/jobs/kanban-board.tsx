"use client";
import { ExtractedSvgIcon25 } from "@/components/icons";


import React, { useState } from "react";
import type { Candidate, CandidateStage } from "@/lib/mock-candidates";
import Link from "next/link";

interface KanbanBoardProps {
  initialCandidates: Candidate[];
}

const STAGES: { id: CandidateStage; title: string }[] = [
  { id: "new", title: "New Applied" },
  { id: "screening", title: "Screening" },
  { id: "interview", title: "Interviewing" },
  { id: "offer", title: "Offered" },
  { id: "hired", title: "Hired" },
  { id: "rejected", title: "Rejected" },
];

export const KanbanBoard = ({ initialCandidates }: KanbanBoardProps) => {
  const [candidates, setCandidates] = useState<Candidate[]>(initialCandidates);
  const [draggedCandidateId, setDraggedCandidateId] = useState<string | null>(null);
  const [dragOverStage, setDragOverStage] = useState<CandidateStage | null>(null);

  const handleDragStart = (e: React.DragEvent, id: string) => {
    setDraggedCandidateId(id);
    // Needed for Firefox
    e.dataTransfer.setData("text/plain", id);
    e.dataTransfer.effectAllowed = "move";

    // Slight delay to allow the drag ghost to generate before we add opacity to the original
    setTimeout(() => {
      const el = document.getElementById(`candidate-${id}`);
      if (el) el.classList.add("opacity-50");
    }, 0);
  };

  const handleDragEnd = (e: React.DragEvent, id: string) => {
    setDraggedCandidateId(null);
    setDragOverStage(null);
    const el = document.getElementById(`candidate-${id}`);
    if (el) el.classList.remove("opacity-50");
  };

  const handleDragOver = (e: React.DragEvent, stage: CandidateStage) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    if (dragOverStage !== stage) {
      setDragOverStage(stage);
    }
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    // We only clear dragOverStage if we're not dropping (handled in drop)
  };

  const handleDrop = (e: React.DragEvent, stage: CandidateStage) => {
    e.preventDefault();
    setDragOverStage(null);

    if (!draggedCandidateId) return;

    setCandidates((prev) =>
      prev.map((c) =>
        c.id === draggedCandidateId ? { ...c, stage } : c
      )
    );
  };

  return (
    <div className="flex gap-4 sm:gap-6 overflow-x-auto pb-6 h-full items-start snap-x snap-mandatory" style={{ scrollbarWidth: "none", WebkitOverflowScrolling: "touch" }}>
      {STAGES.map((stage) => {
        const stageCandidates = candidates.filter((c) => c.stage === stage.id);
        const isDragOver = dragOverStage === stage.id;

        return (
          <div
            key={stage.id}
            className={`snap-center shrink-0 w-[85vw] sm:w-80 flex flex-col bg-gray-50/50 rounded-xl border transition-colors duration-200 ${
              isDragOver ? "border-sr-green bg-green-50/30" : "border-gray-200"
            }`}
            onDragOver={(e) => handleDragOver(e, stage.id)}
            onDragLeave={handleDragLeave}
            onDrop={(e) => handleDrop(e, stage.id)}
          >
            {/* Column Header */}
            <div className="flex items-center justify-between p-4 border-b border-gray-200 bg-gray-50 rounded-t-xl">
              <h3 className="font-semibold text-gray-900">{stage.title}</h3>
              <span className="bg-white text-gray-500 text-xs font-medium px-2 py-1 rounded-full border border-gray-200 shadow-sm">
                {stageCandidates.length}
              </span>
            </div>

            {/* Column Body */}
            <div className="p-3 flex flex-col gap-3 min-h-37.5 max-h-[calc(100vh-280px)] overflow-y-auto">
              {stageCandidates.map((candidate) => (
                <div
                  key={candidate.id}
                  id={`candidate-${candidate.id}`}
                  draggable
                  onDragStart={(e) => handleDragStart(e, candidate.id)}
                  onDragEnd={(e) => handleDragEnd(e, candidate.id)}
                  className="bg-white p-4 rounded-xl border border-gray-200 shadow-sm hover:shadow-md hover:border-gray-300 transition-all cursor-grab active:cursor-grabbing group"
                >
                  <div className="flex items-start gap-3 mb-3">
                    <div className="w-10 h-10 rounded-full bg-sr-mint text-sr-text-blue flex items-center justify-center font-bold text-sm shrink-0">
                      {candidate.initials}
                    </div>
                    <div className="flex flex-col min-w-0 flex-1">
                      <Link href={`/dashboard/candidates/${candidate.id}`} className="font-semibold text-sr-text-blue hover:text-sr-green transition-colors truncate">
                        {candidate.name}
                      </Link>
                      <span className="text-xs text-gray-500 truncate">{candidate.role}</span>
                    </div>
                  </div>

                  <div className="flex items-center justify-between mt-3 pt-3 border-t border-gray-100">
                    <div className="flex items-center gap-2">
                      <div className="w-16 h-1.5 bg-gray-100 rounded-full overflow-hidden shrink-0">
                        <div
                          className={`h-full rounded-full ${candidate.matchScore >= 80 ? 'bg-green-500' : candidate.matchScore >= 60 ? 'bg-amber-500' : 'bg-red-500'}`}
                          style={{ width: `${candidate.matchScore}%` }}
                        />
                      </div>
                      <span className="text-xs font-medium text-gray-700">{candidate.matchScore}%</span>
                    </div>

                    <div className="text-gray-300 group-hover:text-sr-text-blue transition-colors">
                      <ExtractedSvgIcon25 className="w-4 h-4" />
                    </div>
                  </div>
                </div>
              ))}

              {/* Empty state drop zone styling */}
              {stageCandidates.length === 0 && (
                <div className="h-24 rounded-xl border-2 border-dashed border-gray-200 flex items-center justify-center text-sm text-gray-400">
                  Drop candidate here
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
};
