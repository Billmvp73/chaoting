"use client";

import { useChaotingStore } from "@/lib/store";
import { AnimatePresence, motion } from "framer-motion";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

interface CommandItem {
  id: string;
  label: string;
  description?: string;
  action: () => void;
}

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  onCreateNew: () => void;
}

export function CommandPalette({
  open,
  onClose,
  onCreateNew,
}: CommandPaletteProps) {
  const router = useRouter();
  const zouzheList = useChaotingStore((s) => s.zouzheList);
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setQuery("");
      setSelectedIndex(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  const staticCommands: CommandItem[] = useMemo(
    () => [
      {
        id: "cmd-dashboard",
        label: "Dashboard",
        description: "Go to dashboard",
        action: () => {
          router.push("/dashboard");
          onClose();
        },
      },
      {
        id: "cmd-list",
        label: "Task List",
        description: "Go to task list",
        action: () => {
          router.push("/zouzhe");
          onClose();
        },
      },
      {
        id: "cmd-agents",
        label: "Agents",
        description: "Go to agent status",
        action: () => {
          router.push("/agents");
          onClose();
        },
      },
      {
        id: "cmd-create",
        label: "Create New Task",
        description: "Create a new zouzhe",
        action: () => {
          onClose();
          onCreateNew();
        },
      },
    ],
    [router, onClose, onCreateNew]
  );

  const results = useMemo(() => {
    const q = query.toLowerCase().trim();
    if (!q) return staticCommands;

    const items: CommandItem[] = [];

    // Match ZZ-ID prefix
    if (q.startsWith("zz-") || q.match(/^\d{8}/)) {
      const matchingZouzhe = zouzheList.filter(
        (z) =>
          z.id.toLowerCase().includes(q) || z.title.toLowerCase().includes(q)
      );
      for (const z of matchingZouzhe.slice(0, 10)) {
        items.push({
          id: `zouzhe-${z.id}`,
          label: z.id,
          description: z.title,
          action: () => {
            router.push(`/zouzhe/${z.id}`);
            onClose();
          },
        });
      }
    }

    // Match static commands
    if ("dash".includes(q) || "monitor".includes(q) || "dashboard".includes(q)) {
      items.push(staticCommands[0]);
    }
    if ("list".includes(q) || "zouzhe".includes(q) || "tasks".includes(q)) {
      items.push(staticCommands[1]);
    }
    if ("agents".includes(q) || "department".includes(q)) {
      items.push(staticCommands[2]);
    }
    if ("new".includes(q) || "create".includes(q)) {
      items.push(staticCommands[3]);
    }

    // Also search zouzhe by title if not already matched
    if (!q.startsWith("zz-") && !q.match(/^\d{8}/)) {
      const titleMatches = zouzheList.filter((z) =>
        z.title.toLowerCase().includes(q)
      );
      for (const z of titleMatches.slice(0, 5)) {
        const alreadyAdded = items.some((i) => i.id === `zouzhe-${z.id}`);
        if (!alreadyAdded) {
          items.push({
            id: `zouzhe-${z.id}`,
            label: z.id,
            description: z.title,
            action: () => {
              router.push(`/zouzhe/${z.id}`);
              onClose();
            },
          });
        }
      }
    }

    // Deduplicate
    const seen = new Set<string>();
    return items.filter((item) => {
      if (seen.has(item.id)) return false;
      seen.add(item.id);
      return true;
    });
  }, [query, zouzheList, staticCommands, router, onClose]);

  useEffect(() => {
    setSelectedIndex(0);
  }, [results]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setSelectedIndex((i) => Math.min(i + 1, results.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setSelectedIndex((i) => Math.max(i - 1, 0));
      } else if (e.key === "Enter") {
        e.preventDefault();
        if (results[selectedIndex]) {
          results[selectedIndex].action();
        }
      } else if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    },
    [results, selectedIndex, onClose]
  );

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          className="fixed inset-0 z-[100] flex items-start justify-center pt-[15vh]"
          style={{ backgroundColor: "rgba(0,0,0,0.6)" }}
          onClick={onClose}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: -10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: -10 }}
            transition={{ duration: 0.15 }}
            onClick={(e) => e.stopPropagation()}
            style={{
              backgroundColor: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: 10,
              width: 520,
              maxWidth: "90vw",
              overflow: "hidden",
              boxShadow: "0 20px 60px rgba(0,0,0,0.5)",
            }}
          >
            {/* Search input */}
            <div
              style={{
                padding: "12px 16px",
                borderBottom: "1px solid var(--border)",
              }}
            >
              <input
                ref={inputRef}
                type="text"
                placeholder="Search tasks, navigate..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                style={{
                  width: "100%",
                  fontSize: 14,
                  backgroundColor: "transparent",
                  border: "none",
                  outline: "none",
                  color: "var(--text-primary)",
                }}
              />
            </div>

            {/* Results */}
            <div
              style={{
                maxHeight: 320,
                overflow: "auto",
              }}
            >
              {results.length === 0 ? (
                <div
                  style={{
                    padding: "20px 16px",
                    textAlign: "center",
                    fontSize: 13,
                    color: "var(--text-secondary)",
                  }}
                >
                  No results
                </div>
              ) : (
                results.map((item, index) => (
                  <div
                    key={item.id}
                    onClick={item.action}
                    onMouseEnter={() => setSelectedIndex(index)}
                    style={{
                      padding: "10px 16px",
                      cursor: "pointer",
                      backgroundColor:
                        index === selectedIndex
                          ? "var(--surface-2)"
                          : "transparent",
                      transition: "background-color 0.1s",
                    }}
                  >
                    <div
                      style={{
                        fontSize: 13,
                        color:
                          index === selectedIndex
                            ? "var(--imperial-gold)"
                            : "var(--text-primary)",
                        fontWeight: 500,
                      }}
                    >
                      {item.label}
                    </div>
                    {item.description && (
                      <div
                        style={{
                          fontSize: 11,
                          color: "var(--text-secondary)",
                          marginTop: 1,
                        }}
                      >
                        {item.description}
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>

            {/* Footer hint */}
            <div
              style={{
                padding: "8px 16px",
                borderTop: "1px solid var(--border)",
                fontSize: 10,
                color: "var(--text-secondary)",
                display: "flex",
                gap: 12,
              }}
            >
              <span>
                <kbd
                  style={{
                    padding: "1px 4px",
                    borderRadius: 2,
                    backgroundColor: "var(--surface-2)",
                    fontSize: 9,
                  }}
                >
                  ↑↓
                </kbd>{" "}
                Navigate
              </span>
              <span>
                <kbd
                  style={{
                    padding: "1px 4px",
                    borderRadius: 2,
                    backgroundColor: "var(--surface-2)",
                    fontSize: 9,
                  }}
                >
                  Enter
                </kbd>{" "}
                Select
              </span>
              <span>
                <kbd
                  style={{
                    padding: "1px 4px",
                    borderRadius: 2,
                    backgroundColor: "var(--surface-2)",
                    fontSize: 9,
                  }}
                >
                  Esc
                </kbd>{" "}
                Close
              </span>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
