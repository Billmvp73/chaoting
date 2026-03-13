"use client";

import { useChaotingStore } from "@/lib/store";
import { X } from "lucide-react";
import { useState } from "react";

interface CredentialsModalProps {
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export function CredentialsModal({
  open,
  onClose,
  onSuccess,
}: CredentialsModalProps) {
  const setCredentials = useChaotingStore((s) => s.setCredentials);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  if (!open) return null;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!username || !password) return;
    setCredentials({ username, password });
    onSuccess();
  }

  return (
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
          width: 380,
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
            Authentication Required
          </h3>
          <button
            onClick={onClose}
            style={{ color: "var(--text-secondary)", cursor: "pointer" }}
          >
            <X size={16} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <div>
            <label
              style={{
                fontSize: 12,
                color: "var(--text-secondary)",
                display: "block",
                marginBottom: 4,
              }}
            >
              Username
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
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

          <div>
            <label
              style={{
                fontSize: 12,
                color: "var(--text-secondary)",
                display: "block",
                marginBottom: 4,
              }}
            >
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
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

          <button
            type="submit"
            disabled={!username || !password}
            style={{
              marginTop: 4,
              fontSize: 13,
              padding: "8px 16px",
              borderRadius: 4,
              border: "none",
              backgroundColor: "var(--imperial-gold)",
              color: "var(--ink-black)",
              fontWeight: 600,
              cursor: !username || !password ? "not-allowed" : "pointer",
              opacity: !username || !password ? 0.5 : 1,
            }}
          >
            Login
          </button>
        </form>
      </div>
    </div>
  );
}
