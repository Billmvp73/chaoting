"use client";

import { CredentialsModal } from "@/components/zouzhe/CredentialsModal";
import { decideZouzhe } from "@/lib/api";
import { useChaotingStore } from "@/lib/store";
import { X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

interface DecideModalProps {
  open: boolean;
  onClose: () => void;
  zouzheId: string;
}

export function DecideModal({ open, onClose, zouzheId }: DecideModalProps) {
  const router = useRouter();
  const credentials = useChaotingStore((s) => s.credentials);
  const [showCredentials, setShowCredentials] = useState(false);
  const [verdict, setVerdict] = useState<"approve" | "reject" | "revise" | "">(
    ""
  );
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  const reasonRequired = verdict === "revise";

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!verdict) return;
    if (reasonRequired && !reason) return;

    if (!credentials) {
      setShowCredentials(true);
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      await decideZouzhe(
        zouzheId,
        {
          verdict: verdict as "approve" | "reject" | "revise",
          reason: reason || undefined,
        },
        credentials
      );
      onClose();
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to decide");
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
              Decide on Escalation
            </h3>
            <button
              onClick={onClose}
              style={{ color: "var(--text-secondary)", cursor: "pointer" }}
            >
              <X size={16} />
            </button>
          </div>

          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            {/* Verdict */}
            <div>
              <label
                style={{
                  fontSize: 12,
                  color: "var(--text-secondary)",
                  display: "block",
                  marginBottom: 6,
                }}
              >
                Verdict *
              </label>
              <div className="flex gap-3">
                {(
                  [
                    { label: "Approve", value: "approve" as const },
                    { label: "Reject", value: "reject" as const },
                    { label: "Revise", value: "revise" as const },
                  ] as const
                ).map((opt) => (
                  <label
                    key={opt.value}
                    className="flex items-center gap-1.5"
                    style={{
                      fontSize: 12,
                      color: "var(--text-primary)",
                      cursor: "pointer",
                    }}
                  >
                    <input
                      type="radio"
                      name="verdict"
                      value={opt.value}
                      checked={verdict === opt.value}
                      onChange={() => setVerdict(opt.value)}
                      style={{ accentColor: "var(--imperial-gold)" }}
                    />
                    {opt.label}
                  </label>
                ))}
              </div>
            </div>

            {/* Reason */}
            <div>
              <label
                style={{
                  fontSize: 12,
                  color: "var(--text-secondary)",
                  display: "block",
                  marginBottom: 4,
                }}
              >
                Reason {reasonRequired ? "*" : "(optional)"}
              </label>
              <textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                required={reasonRequired}
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

            {error && (
              <div style={{ fontSize: 12, color: "var(--state-failed)" }}>
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={!verdict || (reasonRequired && !reason) || submitting}
              style={{
                fontSize: 13,
                padding: "8px 16px",
                borderRadius: 4,
                border: "none",
                backgroundColor: "var(--imperial-gold)",
                color: "var(--ink-black)",
                fontWeight: 600,
                cursor:
                  !verdict || (reasonRequired && !reason) || submitting
                    ? "not-allowed"
                    : "pointer",
                opacity:
                  !verdict || (reasonRequired && !reason) || submitting
                    ? 0.5
                    : 1,
              }}
            >
              {submitting ? "Submitting..." : "Submit Decision"}
            </button>
          </form>
        </div>
      </div>
    </>
  );
}
