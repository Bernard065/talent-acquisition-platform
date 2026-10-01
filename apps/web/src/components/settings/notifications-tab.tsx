import React, { useState } from "react";
import { INITIAL_NOTIFICATIONS } from "@/constants/dashboard";

export const NotificationsTab = () => {
  const [notifications, setNotifications] = useState(INITIAL_NOTIFICATIONS);

  const toggleNotification = (id: string) => {
    setNotifications(notifications.map((n) => n.id === id ? { ...n, enabled: !n.enabled } : n));
  };

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden flex flex-col">
      <div className="p-6 border-b border-gray-100">
        <h2 className="text-lg font-bold text-sr-text-blue">Notification Preferences</h2>
        <p className="text-sm text-gray-500 mt-1">Choose what updates you want to receive and how you want to be alerted.</p>
      </div>
      <div className="flex-1 divide-y divide-gray-100">
        {notifications.map((notification) => (
          <div key={notification.id} className="p-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <h3 className="text-sm font-semibold text-gray-900">{notification.title}</h3>
              <p className="text-sm text-gray-500 mt-1">{notification.description}</p>
            </div>
            <button
              onClick={() => toggleNotification(notification.id)}
              className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer items-center justify-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-sr-green focus:ring-offset-2 ${notification.enabled ? "bg-sr-green" : "bg-gray-200"}`}
              role="switch"
              aria-checked={notification.enabled}
            >
              <span className="sr-only">Toggle {notification.title}</span>
              <span aria-hidden="true" className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${notification.enabled ? "translate-x-2.5" : "-translate-x-2.5"}`} />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
};
