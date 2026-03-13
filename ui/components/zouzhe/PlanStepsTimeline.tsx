"use client";

import { Check, Circle, Diamond } from "lucide-react";

interface PlanStepsTimelineProps {
  steps: string[];
  zoubaoCount: number;
  latestZoubaoText?: string;
}

export function PlanStepsTimeline({
  steps,
  zoubaoCount,
  latestZoubaoText,
}: PlanStepsTimelineProps) {
  if (steps.length === 0) {
    return (
      <div style={{ color: "var(--text-secondary)", fontSize: 13 }}>
        No plan steps available
      </div>
    );
  }

  const currentStepIndex = Math.min(
    Math.max(zoubaoCount - 1, 0),
    steps.length - 1
  );

  return (
    <div className="flex flex-col gap-0">
      {steps.map((step, index) => {
        const isCompleted = index < currentStepIndex;
        const isCurrent = index === currentStepIndex;

        return (
          <div key={index} className="flex items-start gap-3 relative">
            {/* Vertical line */}
            {index < steps.length - 1 && (
              <div
                style={{
                  position: "absolute",
                  left: 9,
                  top: 22,
                  bottom: -8,
                  width: 1,
                  backgroundColor: isCompleted
                    ? "var(--state-done)"
                    : "var(--border)",
                }}
              />
            )}

            {/* Icon */}
            <div className="flex-shrink-0 mt-0.5">
              {isCompleted ? (
                <Check
                  size={18}
                  style={{ color: "var(--state-done)" }}
                />
              ) : isCurrent ? (
                <Diamond
                  size={18}
                  style={{ color: "var(--state-executing)" }}
                />
              ) : (
                <Circle
                  size={18}
                  style={{ color: "var(--text-secondary)", opacity: 0.4 }}
                />
              )}
            </div>

            {/* Content */}
            <div className="pb-5 flex-1">
              <div
                style={{
                  fontSize: 13,
                  color: isCompleted
                    ? "var(--text-primary)"
                    : isCurrent
                      ? "var(--text-primary)"
                      : "var(--text-secondary)",
                  opacity: isCompleted ? 0.6 : 1,
                }}
              >
                {step}
              </div>
              {isCurrent && latestZoubaoText && (
                <div
                  style={{
                    fontSize: 11,
                    color: "var(--text-secondary)",
                    marginTop: 4,
                    padding: "4px 8px",
                    backgroundColor: "var(--surface-2)",
                    borderRadius: 4,
                    borderLeft: "2px solid var(--state-executing)",
                  }}
                >
                  {latestZoubaoText}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
