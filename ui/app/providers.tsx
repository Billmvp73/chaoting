"use client";

import { NavSidebar } from "@/components/layout/NavSidebar";
import { SSEProvider } from "@/components/shared/SSEProvider";

export function ClientProviders({ children }: { children: React.ReactNode }) {
  return (
    <SSEProvider>
      <div className="flex min-h-screen">
        <NavSidebar />
        <main className="flex-1" style={{ marginLeft: 220 }}>
          {children}
        </main>
      </div>
    </SSEProvider>
  );
}
