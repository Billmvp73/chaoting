"use client";

import { NavSidebar } from "@/components/layout/NavSidebar";
import { CommandPalette } from "@/components/shared/CommandPalette";
import { SSEProvider } from "@/components/shared/SSEProvider";
import { CreateZouzheModal } from "@/components/zouzhe/CreateZouzheModal";
import { useCallback, useEffect, useState } from "react";

export function ClientProviders({ children }: { children: React.ReactNode }) {
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  const [createModalOpen, setCreateModalOpen] = useState(false);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setCommandPaletteOpen((prev) => !prev);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  const handleCreateNew = useCallback(() => {
    setCreateModalOpen(true);
  }, []);

  return (
    <SSEProvider>
      <div className="flex min-h-screen">
        <NavSidebar />
        <main className="flex-1" style={{ marginLeft: 220 }}>
          {children}
        </main>
      </div>
      <CommandPalette
        open={commandPaletteOpen}
        onClose={() => setCommandPaletteOpen(false)}
        onCreateNew={handleCreateNew}
      />
      <CreateZouzheModal
        open={createModalOpen}
        onClose={() => setCreateModalOpen(false)}
      />
    </SSEProvider>
  );
}
