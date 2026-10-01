import React, { useState } from "react";
import { INITIAL_INTEGRATIONS } from "@/constants/dashboard";

export const IntegrationsTab = () => {
  const [integrations, setIntegrations] = useState(INITIAL_INTEGRATIONS);

  const toggleIntegration = (id: string) => {
    setIntegrations(integrations.map((i) => i.id === id ? { ...i, connected: !i.connected } : i));
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
      {integrations.map((integration) => (
        <div key={integration.id} className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm flex flex-col justify-between hover:border-gray-300 transition-colors">
          <div>
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded-xl bg-gray-50 border border-gray-100 flex items-center justify-center shrink-0">
                  <span className="font-bold text-lg text-sr-text-blue">{integration.name.charAt(0)}</span>
                </div>
                <div>
                  <h3 className="font-bold text-gray-900">{integration.name}</h3>
                  <p className="text-xs text-gray-500 mt-0.5">{integration.category}</p>
                </div>
              </div>
              <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${integration.connected ? "bg-emerald-50 text-emerald-700 border-emerald-200/60" : "bg-gray-50 text-gray-500 border-gray-200"}`}>
                <span className={`w-1.5 h-1.5 rounded-full ${integration.connected ? "bg-emerald-500" : "bg-gray-400"}`} />
                {integration.connected ? "Connected" : "Not Connected"}
              </span>
            </div>
            <p className="text-sm text-gray-600 mt-4 leading-relaxed">{integration.description}</p>
          </div>
          <div className="mt-6 pt-6 border-t border-gray-100">
            <button onClick={() => toggleIntegration(integration.id)} className={`w-full h-10 rounded-lg font-medium text-sm transition-colors border ${integration.connected ? "bg-white text-red-600 border-red-200 hover:bg-red-50" : "bg-white text-gray-700 border-gray-200 hover:bg-gray-50 hover:text-gray-900"}`}>
              {integration.connected ? "Disconnect" : "Connect"}
            </button>
          </div>
        </div>
      ))}
    </div>
  );
};
