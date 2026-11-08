/**
 * BetriebsPilot AI - API Client SDK
 * Handles REST requests and Server-Sent Events (SSE) streaming from FastAPI Agent Server.
 */

import {
  CustomerSummary,
  ProcessInputResponse,
  ApproveAndExportRequest,
  ApproveAndExportResponse,
  CatalogSearchResult,
  SystemHealth,
  TraceEvent
} from '../types/erp';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export class AgentClient {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE) {
    this.baseUrl = baseUrl.replace(/\/$/, '');
  }

  /**
   * Diagnostic health check for Postgres, Qdrant, and Ollama/Cloud LLM
   */
  async getHealth(): Promise<SystemHealth> {
    const res = await fetch(`${this.baseUrl}/health`);
    if (!res.ok) {
      throw new Error(`Health check failed: HTTP ${res.status}`);
    }
    return res.json();
  }

  /**
   * Retrieves list of seeded German B2B customers for the UI dropdown
   */
  async getCustomers(): Promise<CustomerSummary[]> {
    const res = await fetch(`${this.baseUrl}/api/v1/customers`);
    if (!res.ok) {
      throw new Error(`Failed to load customer directory: HTTP ${res.status}`);
    }
    return res.json();
  }

  /**
   * Ingests PDF or raw email/chat text and executes the LangGraph agent pipeline
   */
  async processInput(formData: FormData): Promise<ProcessInputResponse> {
    const res = await fetch(`${this.baseUrl}/api/v1/process-input`, {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `Processing failed: HTTP ${res.status}`);
    }
    return res.json();
  }

  /**
   * 1-Click human approval: updates customer SKU aliases and returns OpenTRANS XML / SAP B1 JSON
   */
  async approveAndExport(payload: ApproveAndExportRequest): Promise<ApproveAndExportResponse> {
    const res = await fetch(`${this.baseUrl}/api/v1/approve-and-export`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `Export approval failed: HTTP ${res.status}`);
    }
    return res.json();
  }

  /**
   * Vector similarity catalog search in Qdrant for clerk manual overrides
   */
  async searchCatalog(query: string, limit: number = 5): Promise<CatalogSearchResult[]> {
    const params = new URLSearchParams({ query, limit: limit.toString() });
    const res = await fetch(`${this.baseUrl}/api/v1/erp-catalog/search?${params}`);
    if (!res.ok) {
      throw new Error(`Catalog search failed: HTTP ${res.status}`);
    }
    return res.json();
  }

  /**
   * Subscribes to real-time Server-Sent Events (SSE) streaming LangGraph execution traces
   */
  subscribeTrace(
    taskId: string,
    onEvent: (event: TraceEvent) => void,
    onComplete?: () => void,
    onError?: (err: any) => void
  ): () => void {
    const eventSource = new EventSource(`${this.baseUrl}/api/v1/stream-trace/${taskId}`);

    eventSource.addEventListener('trace', (e) => {
      try {
        const data: TraceEvent = JSON.parse(e.data);
        onEvent(data);
        if (data.status === 'COMPLETED' && data.node === 'confidence_gate') {
          if (onComplete) onComplete();
        }
      } catch (err) {
        console.error('Failed to parse SSE trace event', err);
      }
    });

    eventSource.onerror = (err) => {
      if (onError) onError(err);
      eventSource.close();
    };

    // Return unsubscriber function
    return () => {
      eventSource.close();
    };
  }
}

export const agentClient = new AgentClient();
