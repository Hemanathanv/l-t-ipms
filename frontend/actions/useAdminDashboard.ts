'use client';

import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';

export interface TokenUsageSummary {
    total_input_tokens: number;
    total_output_tokens: number;
    total_tokens: number;
    total_messages: number;
    total_conversations: number;
    total_tool_calls: number;
    avg_latency_ms: number | null;
}

export interface MessageRow {
    id: string;
    conversation_id: string;
    thread_id: string | null;
    role: string;
    content: string;
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
    tool_name: string | null;
    tool_calls: any[] | null;
    model: string | null;
    latency_ms: number | null;
    feedback: string | null;
    created_at: string | null;
}

export interface TokenUsageResponse {
    summary: TokenUsageSummary;
    messages: MessageRow[];
}

async function fetchTokenUsage(): Promise<TokenUsageResponse> {
    const res = await apiFetch('/admin/token-usage');
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(err.detail || `Error ${res.status}`);
    }
    return res.json();
}

export function useAdminDashboard() {
    return useQuery<TokenUsageResponse>({
        queryKey: ['admin', 'token-usage'],
        queryFn: fetchTokenUsage,
        staleTime: 30_000, // 30s
        refetchOnWindowFocus: false,
    });
}
