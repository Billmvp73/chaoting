"use client";

import { CredentialsModal } from "@/components/zouzhe/CredentialsModal";
import { reviseZouzhe } from "@/lib/api";
import { useChaotingStore } from "@/lib/store";
import { X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

interface ReviseModalProps {
  open: boolean;
  onClose: () => void;
  zouzheId: string;
}

export function ReviseModal({ open, onClose, zouzheId }: ReviseModalProps) {
  const router = useRouter();
  const credentials = useChaotingStore((s) => s.credentials);
  const [showCredentials, setShowCredentials] = useState(false);
  const [reason, setReason] = useState("");
  const [reviewRequired, setReviewRequired] = useState(1);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!reason) return;

    if (!credentials) {
      setShowCredentials(true);
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      await reviseZouzhe(
        zouzheId,
        { reason, review_required: reviewRequired },
        credentials
      );
      onClose();
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to revise");
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
            width: 420,
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
              Revise Task
            </h3>
            <button
              onClick={onClose}
              style={{ color: "var(--text-secondary)", cursor: "pointer" }}
            >
              <X size={16} />
            </button>
          </div>

          <div
            style={{
              fontSize: 12,
              color: "var(--state-escalated)",
              marginBottom: 12,
              padding: "6px 10px",
              backgroundColor: "rgba(230,126,34,0.1)",
              borderRadius: 4,
            }}
          >
            This will reset the task to planning state
          </div>

          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div>
              <label
                style={{
                  fontSize: 12,
                  color: "var(--text-secondary)",
                  display: "block",
                  marginBottom: 4,
                }}
              >
                Reason *
              </label>
              <textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                required
                rows={3}
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
                  resize: "vertical",
                }}
              />
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
              disabled={!reason || submitting}
              style={{
                fontSize: 13,
                padding: "8px 16px",
                borderRadius: 4,
                border: "none",
                backgroundColor: "var(--state-escalated)",
                color: "#fff",
                fontWeight: 600,
                cursor: !reason || submitting ? "not-allowed" : "pointer",
                opacity: !reason || submitting ? 0.5 : 1,
              }}
            >
              {submitting ? "Submitting..." : "Revise"}
            </button>
          </form>
        </div>
      </div>
    </>
  );
}
