"use client";

import { CredentialsModal } from "@/components/zouzhe/CredentialsModal";
import { createZouzhe } from "@/lib/api";
import { useChaotingStore } from "@/lib/store";
import { X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

interface CreateZouzheModalProps {
  open: boolean;
  onClose: () => void;
}

export function CreateZouzheModal({ open, onClose }: CreateZouzheModalProps) {
  const router = useRouter();
  const credentials = useChaotingStore((s) => s.credentials);
  const [showCredentials, setShowCredentials] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState("normal");
  const [reviewRequired, setReviewRequired] = useState(1);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!title || !description) return;

    if (!credentials) {
      setShowCredentials(true);
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      const result = await createZouzhe(
        { title, description, priority, review_required: reviewRequired },
        credentials
      );
      onClose();
      router.push(`/zouzhe/${result.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create task");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <CredentialsModal
        open={showCredentials}
        onClose={() => setShowCredentials(false)}
        onSuccess={() => setShowCredentials(false)}
      />

      <div
        className="fixed inset-0 z-50 flex items-center justify-center"
        style={{ backgroundColor: "rgba(0,0,0,0.6)" }}
        onClick={onClose}
      >
        <div
          onClick={(e) => e.stopPropagation()}
          style={{
            backgroundColor: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: 8,
            padding: 24,
            width: 480,
            maxWidth: "90vw",
          }}
        >
          <div className="flex items-center justify-between mb-4">
            <h3
              style={{
                fontSize: 15,
                fontWeight: 600,
                color: "var(--text-primary)",
              }}
            >
              Create New Task
            </h3>
            <button
              onClick={onClose}
              style={{ color: "var(--text-secondary)", cursor: "pointer" }}
            >
              <X size={16} />
            </button>
          </div>

          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            {/* Title */}
            <div>
              <label
                style={{
                  fontSize: 12,
                  color: "var(--text-secondary)",
                  display: "block",
                  marginBottom: 4,
                }}
              >
                Title *
              </label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                required
                autoFocus
                style={{
                  width: "100%",
                  fontSize: 13,
                  padding: "6px 10px",
                  borderRadius: 4,
                  border: "1px solid var(--border)",
                  backgroundColor: "var(--surface-2)",
                  color: "var(--text-primary)",
                  outline: "none",
                }}
              />
            </div>

            {/* Description */}
            <div>
              <label
                style={{
                  fontSize: 12,
                  color: "var(--text-secondary)",
                  display: "block",
                  marginBottom: 4,
                }}
              >
                Description *
              </label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                required
                rows={3}
                style={{
                  width: "100%",
                  fontSize: 13,
                  padding: "6px 10px",
                  borderRadius: 4,
                  border: "1px solid var(--border)",
                  backgroundColor: "var(--surface-2)",
                  color: "var(--text-primary)",
                  outline: "none",
                  resize: "vertical",
                }}
              />
            </div>

            {/* Priority */}
            <div>
              <label
                style={{
                  fontSize: 12,
                  color: "var(--text-secondary)",
                  display: "block",
                  marginBottom: 6,
                }}
              >
                Priority
              </label>
              <div className="flex gap-3">
                {(["normal", "high", "urgent"] as const).map((p) => (
                  <label
                    key={p}
                    className="flex items-center gap-1.5"
                    style={{ fontSize: 12, color: "var(--text-primary)", cursor: "pointer" }}
                  >
                    <input
                      type="radio"
                      name="priority"
                      value={p}
                      checked={priority === p}
                      onChange={() => setPriority(p)}
                      style={{ accentColor: "var(--imperial-gold)" }}
                    />
                    {p}
                  </label>
                ))}
              </div>
            </div>

            {/* Review Required */}
            <div>
              <label
                style={{
                  fontSize: 12,
                  color: "var(--text-secondary)",
                  display: "block",
                  marginBottom: 6,
                }}
              >
                Review Required
              </label>
              <div className="flex gap-3">
                {([
                  { label: "1 vote", value: 1 },
                  { label: "2 votes", value: 2 },
                  { label: "All votes", value: 3 },
                ] as const).map((opt) => (
                  <label
                    key={opt.value}
                    className="flex items-center gap-1.5"
                    style={{ fontSize: 12, color: "var(--text-primary)", cursor: "pointer" }}
                  >
                    <input
                      type="radio"
                      name="review_required"
                      value={opt.value}
                      checked={reviewRequired === opt.value}
                      onChange={() => setReviewRequired(opt.value)}
                      style={{ accentColor: "var(--imperial-gold)" }}
                    />
                    {opt.label}
                  </label>
                ))}
              </div>
            </div>

            {error && (
              <div style={{ fontSize: 12, color: "var(--state-failed)" }}>
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={!title || !description || submitting}
              style={{
                fontSize: 13,
                padding: "8px 16px",
                borderRadius: 4,
                border: "none",
                backgroundColor: "var(--imperial-gold)",
                color: "var(--ink-black)",
                fontWeight: 600,
                cursor:
                  !title || !description || submitting
                    ? "not-allowed"
                    : "pointer",
                opacity: !title || !description || submitting ? 0.5 : 1,
              }}
            >
              {submitting ? "Creating..." : "Create Task"}
            </button>
          </form>
        </div>
      </div>
    </>
  );
}
