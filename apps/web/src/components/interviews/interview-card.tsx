import React from "react";
import type { Interview } from "@/types/interviews";
import { Calendar, Clock, Video, MapPin, Users, ChevronRight, FileText } from "lucide-react";

interface InterviewCardProps {
  interview: Interview;
  onAction?: (action: string, interviewId: string) => void;
}

export const InterviewCard = ({ interview, onAction }: InterviewCardProps) => {
  const isUpcoming = interview.status === "Scheduled";
  const needsFeedback = interview.status === "Pending Feedback";

  const getBadgeStyle = (type: string) => {
    switch (type) {
      case "Technical": return "bg-blue-50 text-blue-700 border-blue-200";
      case "Culture Fit": return "bg-purple-50 text-purple-700 border-purple-200";
      case "Final Round": return "bg-amber-50 text-amber-700 border-amber-200";
      case "Executive": return "bg-rose-50 text-rose-700 border-rose-200";
      default: return "bg-gray-50 text-gray-700 border-gray-200";
    }
  };

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5 sm:p-6 hover:border-sr-green/30 transition-all flex flex-col md:flex-row gap-6 justify-between group">
      <div className="flex-1 flex flex-col sm:flex-row gap-5">
        
        {/* Candidate Info */}
        <div className="flex gap-4 min-w-[240px]">
          <div className="w-12 h-12 rounded-full bg-gray-100 flex items-center justify-center font-bold text-gray-600 shrink-0 border border-gray-200">
            {interview.candidateInitials}
          </div>
          <div>
            <h3 className="font-bold text-sr-text-blue text-lg">{interview.candidateName}</h3>
            <p className="text-sm text-gray-500 font-medium">{interview.jobTitle}</p>
            <span className={`inline-flex items-center mt-2 px-2.5 py-0.5 rounded-full text-xs font-semibold border ${getBadgeStyle(interview.type)}`}>
              {interview.type}
            </span>
          </div>
        </div>

        {/* Time & Location */}
        <div className="flex-1 space-y-2.5 pl-0 sm:pl-6 sm:border-l border-gray-100">
          <div className="flex items-center gap-2 text-sm text-gray-700">
            <Calendar className="w-4 h-4 text-gray-400" />
            <span className="font-medium">{interview.date}</span>
          </div>
          <div className="flex items-center gap-2 text-sm text-gray-700">
            <Clock className="w-4 h-4 text-gray-400" />
            <span>{interview.startTime} - {interview.endTime}</span>
          </div>
          <div className="flex items-center gap-2 text-sm text-gray-700">
            {interview.isVideoCall ? (
              <>
                <Video className="w-4 h-4 text-blue-500" />
                <span>Video Call</span>
              </>
            ) : (
              <>
                <MapPin className="w-4 h-4 text-gray-400" />
                <span>On-site</span>
              </>
            )}
          </div>
        </div>

        {/* Interviewers */}
        <div className="flex-1 pl-0 sm:pl-6 sm:border-l border-gray-100">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-gray-500 mb-2 uppercase tracking-wider">
            <Users className="w-3.5 h-3.5" /> Interviewers
          </div>
          <div className="flex flex-wrap gap-2">
            {interview.interviewers.map((inv, idx) => (
              <div key={idx} className="flex items-center gap-2 bg-gray-50 border border-gray-100 px-2 py-1 rounded-lg" title={inv.role}>
                <div className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold ${inv.avatarBg}`}>
                  {inv.initials}
                </div>
                <span className="text-xs font-medium text-gray-700">{inv.name}</span>
              </div>
            ))}
          </div>
        </div>

      </div>

      {/* Actions */}
      <div className="flex flex-row md:flex-col items-center justify-end md:justify-center gap-3 pt-4 md:pt-0 border-t md:border-t-0 border-gray-100 w-full md:w-auto md:min-w-[140px]">
        {isUpcoming && interview.meetingLink && (
          <a
            href={interview.meetingLink}
            target="_blank"
            rel="noopener noreferrer"
            className="w-full text-center px-4 py-2 bg-sr-mint text-sr-text-blue hover:bg-sr-green hover:text-white rounded-lg text-sm font-bold transition-colors flex items-center justify-center gap-2"
          >
            Join Call
          </a>
        )}
        
        {needsFeedback && (
          <button 
            onClick={() => onAction?.("feedback", interview.id)}
            className="w-full px-4 py-2 bg-amber-500 text-white hover:bg-amber-600 rounded-lg text-sm font-bold transition-colors flex items-center justify-center gap-1.5 shadow-sm"
          >
            <FileText className="w-4 h-4" />
            Scorecard
          </button>
        )}

        <button 
          onClick={() => onAction?.("view", interview.id)}
          className="w-full px-4 py-2 bg-white text-gray-700 border border-gray-200 hover:bg-gray-50 hover:text-gray-900 rounded-lg text-sm font-semibold transition-colors flex items-center justify-center gap-1"
        >
          Details <ChevronRight className="w-4 h-4 text-gray-400 group-hover:text-gray-600 transition-colors" />
        </button>
      </div>
    </div>
  );
};
