export type Classification = "deterministic" | "ai_investigation" | "human_review";

export interface Evidence {
  repo: string;
  issue_number: number;
  title: string;
  body: string;
  labels: string[];
  comments: string[];
}

export type Severity = "low" | "medium" | "high";

export interface Diagnosis {
  root_cause: string;
  severity: Severity;
  missing_info: string[];
  recommended_next_steps: string[];
  citations: string[];
}

export type ReviewOutcome = "approve" | "escalate_to_human" | "reject_retrieve_more";

export interface ReviewResult {
  outcome: ReviewOutcome;
  groundedness_ok: boolean;
  risk_ok: boolean;
  permission_ok: boolean;
  reasoning: string;
}

export interface ProposedAction {
  comment: string;
  label?: string | null;
}

export interface PendingApproval {
  classification: Classification;
  proposed_action: ProposedAction;
}

export interface ExecutionResult {
  comment?: { id: number } | Record<string, unknown>;
  label?: { ok: boolean } | Record<string, unknown>;
}

export interface GraphResult {
  thread_id: string;
  evidence: Evidence | null;
  classification: Classification | null;
  diagnosis: Diagnosis | null;
  review_result: ReviewResult | null;
  pending_approval: PendingApproval | null;
  execution_result: ExecutionResult | null;
  rejected: boolean;
}
