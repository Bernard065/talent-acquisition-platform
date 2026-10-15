"use client";

import React, { useState } from "react";
import { useSession } from "next-auth/react";
import type { SettingsTab } from "@/types/dashboard";
import { ProfileTab } from "@/components/settings/profile-tab";
import { IntegrationsTab } from "@/components/settings/integrations-tab";
import { NotificationsTab } from "@/components/settings/notifications-tab";
import { OnboardingTemplateManager } from "@/components/settings/onboarding-template-manager";

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<SettingsTab>("profile");
  const { data: session } = useSession();
  const canManageOnboarding = session?.roles?.some((role) =>
    role === "tenant_admin" || role === "people_operations",
  ) ?? false;

  return (
    <div className="flex flex-col gap-6 max-w-300 mx-auto w-full">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-sr-text-blue tracking-tight">Settings</h1>
        <p className="text-sm text-gray-500 mt-1">View your account details and manage integrations and notifications</p>
      </div>

      {/* Tabs Navigation */}
      <div className="border-b border-gray-200">
        <nav className="flex items-center gap-6 overflow-x-auto whitespace-nowrap" style={{ scrollbarWidth: "none" }}>
          <button
            onClick={() => setActiveTab("profile")}
            className={`py-3 text-sm font-medium border-b-2 transition-colors ${
              activeTab === "profile"
                ? "border-sr-green text-sr-text-blue"
                : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
            }`}
          >
            Profile
          </button>
          <button
            onClick={() => setActiveTab("integrations")}
            className={`py-3 text-sm font-medium border-b-2 transition-colors ${
              activeTab === "integrations"
                ? "border-sr-green text-sr-text-blue"
                : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
            }`}
          >
            Integrations
          </button>
          <button
            onClick={() => setActiveTab("notifications")}
            className={`py-3 text-sm font-medium border-b-2 transition-colors ${
              activeTab === "notifications"
                ? "border-sr-green text-sr-text-blue"
                : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
            }`}
          >
            Notifications
          </button>
          {canManageOnboarding && (
            <button
              onClick={() => setActiveTab("onboarding")}
              className={`py-3 text-sm font-medium border-b-2 transition-colors ${
                activeTab === "onboarding"
                  ? "border-sr-green text-sr-text-blue"
                  : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
              }`}
            >
              Onboarding
            </button>
          )}
        </nav>
      </div>

      {/* Tab Content */}
      <div className="pt-2">
        {activeTab === "profile" && <ProfileTab />}
        {activeTab === "integrations" && <IntegrationsTab />}
        {activeTab === "notifications" && <NotificationsTab />}
        {activeTab === "onboarding" && canManageOnboarding && <OnboardingTemplateManager />}
      </div>
    </div>
  );
}
