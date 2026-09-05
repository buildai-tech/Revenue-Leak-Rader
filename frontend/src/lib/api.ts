/**
 * API client interacting with backend endpoints.
 *
 * API_BASE resolution order:
 *   1. VITE_API_URL env var (set in Vercel for production, e.g. https://your-api.onrender.com/api)
 *   2. '/api'  — works locally via the Vite dev proxy (vite.config.ts → localhost:8000)
 */

const API_BASE: string = (import.meta.env.VITE_API_URL as string) || '/api';


export async function fetchApi<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`;
  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    ...options,
  });

  if (!response.ok) {
    let errorMessage = `API Error: ${response.status} ${response.statusText}`;
    try {
      const errorJson = await response.json();
      errorMessage = errorJson.detail || errorJson.error || errorMessage;
    } catch {
      // ignore
    }
    throw new Error(errorMessage);
  }

  return response.json();
}

export async function deleteImport(importId: string): Promise<{
  status: string;
  import_id: string;
  filename: string;
  deleted_leads: number;
  deleted_leakage_events: number;
}> {
  return fetchApi(`/imports/${importId}`, { method: 'DELETE' });
}

export async function clearDemoImports(): Promise<{
  status: string;
  deleted_batches: number;
  deleted_leads: number;
  deleted_leakage_events: number;
}> {
  return fetchApi('/imports/demo/clear', { method: 'DELETE' });
}

// ── Types ─────────────────────────────────────────────────────────────

export interface DashboardSummary {
  revenue_at_risk: number;
  revenue_at_risk_tier: string;
  revenue_at_risk_confidence: number;
  potentially_recoverable: number;
  high_priority_count: number;
  confirmed_recovered: number;
  confirmed_recovered_tier: string;
}

export interface LeakageBreakdownItem {
  category: string;
  event_count: number;
  affected_leads: number;
  exposure: number;
  additivity_note: string;
}

export interface HighPriorityIssue {
  id: string;
  category: string;
  title: string;
  status: string;
  lead_name: string;
  lead_budget?: number;
  lead_status?: string;
  financial_impact?: number;
  confidence?: number;
  tier?: string;
  created_at?: string;
}

export interface RecoveryPipeline {
  detected: number;
  reviewed: number;
  recommended: number;
  intervention_started: number;
  recovered: number;
  is_cumulative: boolean;
  definition: string;
}

export interface RecentRecovery {
  id: string;
  intervention_id: string;
  outcome_type: string;
  booking_amount_inr?: number;
  confirmed_at?: string;
}

export interface ResponseBucket {
  bucket_key: string;
  bucket_label: string;
  lead_count: number;
  converted_count: number;
  conversion_rate?: number;
  sample_too_small: boolean;
  avg_response_minutes?: number;
}

export interface ResponseLeakageAnalysis {
  buckets: ResponseBucket[];
  never_contacted?: ResponseBucket;
  total_leads: number;
  leads_with_response: number;
  baseline_conversion_rate?: number;
  correlation_not_causation: boolean;
  disclaimer: string;
}

export interface LeadListItem {
  id: string;
  name: string;
  phone_normalized?: string;
  email?: string;
  status?: string;
  budget?: number;
  source?: string;
  project_name?: string;
  sales_rep_name?: string;
  created_at?: string;
}

export interface LeadListResponse {
  items: LeadListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface LeadDetail extends LeadListItem {
  phone_raw?: string;
  status_raw?: string;
  project_id?: string;
  sales_rep_id?: string;
  recovery_score: number;
  risk_level: string;
  contributing_factors: Array<{
    rule: string;
    points: number;
    evidence: any[];
  }>;
  events: Array<{
    id: string;
    event_type: string;
    occurred_at: string;
    event_payload: any;
    source: string;
  }>;
  leakage_events: Array<{
    id: string;
    category: string;
    title: string;
    status: string;
    created_at: string;
  }>;
  last_followup_at?: string;
}

export interface LeakageEventDetail {
  id: string;
  category: string;
  title: string;
  status: string;
  tier: string;
  lead_name?: string;
  lead_id?: string;
  lead_budget?: number;
  lead_status?: string;
  evidence: Array<{
    id?: string;
    evidence_type: string;
    evidence_payload: any;
  }>;
  financial_calculations?: Array<{
    id: string;
    tier: string;
    amount_inr: number;
    confidence: number;
    formula_id: string;
    formula_version: string;
    assumptions: any;
    data_source: string;
    calculated_at: string;
  }>;
  financial?: {
    amount_inr?: number;
    confidence?: number;
    tier?: string;
    formula_id?: string;
    formula_version?: string;
    assumptions?: any;
    data_source?: string;
  };
  created_at?: string;
}

export interface LeakageListResponse {
  items: LeakageEventDetail[];
  total: number;
}

export interface Recommendation {
  id: string;
  leakage_event_id: string;
  playbook_key: string;
  generated_copy: string;
  generated_by: string;
  lead_name?: string;
  category?: string;
  created_at?: string;
}

export interface Intervention {
  id: string;
  recommendation_id: string;
  assigned_rep_name?: string;
  status: string;
  notes?: string;
  lead_name?: string;
  category?: string;
  playbook_key?: string;
  created_at?: string;
  updated_at?: string;
}

export interface ImportPreview {
  id: string;
  filename: string;
  file_type: string;
  status: string;
  columns: string[];
  preview_rows: Record<string, any>[];
  row_count?: number;
  created_at?: string;
  mappings?: Array<{
    source_column: string;
    target_field: string;
    confidence?: number;
    confirmed: boolean;
    suggested_by?: string;
  }>;
}
