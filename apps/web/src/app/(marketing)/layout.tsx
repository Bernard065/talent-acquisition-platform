import type { ReactNode } from "react";
import { Header } from "@/components/layout/header";
import { TopNotificationBar } from "@/components/layout/top-notification-bar";
import { GlobalFooter } from "@/components/layout/global-footer";

export default function MarketingLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <>
      <TopNotificationBar />
      <Header />
      <main className="flex-1 flex flex-col">
        {children}
      </main>
      <GlobalFooter />
    </>
  );
}
