export interface Message {
    id?: string;
    role: 'user' | 'assistant';
    content: string;
    created_at?: string;
    feedback?: 'positive' | 'negative' | null;
    feedbackNote?: string;
    editedFrom?: string;
    // Branching fields for ChatGPT-style navigation
    position_index?: number;
    branch_index?: number;
    total_branches?: number;
    // Tool output + AI insight fields
    tool_output?: string;
    is_insight?: boolean;
}

export interface Conversation {
    threadId: string;
    title: string;
    createdAt: string;
}

export interface Project {
    project_key: number;
    name: string;
    project_description: string;
    start_date: string | null;
    end_date: string | null;
    location: string;
    /** Start date variants for display (priority: actual → forecast → baseline) */
    actual_start_date?: string | null;
    forecast_start_date?: string | null;
    baseline_start_date?: string | null;
    /** End date variants for display (priority: forecast → contractual → baseline) */
    forecast_finish_date?: string | null;
    contractual_finish_date?: string | null;
    baseline_finish_date?: string | null;
    /** Contract dates */
    contract_start_date?: string | null;
    contract_end_date?: string | null;
    /** Progress & duration for panel */
    progress_pct?: number | null;
    elapsed_days?: number | null;
    total_days?: number | null;
    /** Max forecast delay (days) for PEI status — E/P/C/Overall */
    max_forecast_delay_days_engineering?: number | null;
    max_forecast_delay_days_construction?: number | null;
    max_forecast_delay_days_procurement?: number | null;
    max_forecast_delay_days_overall?: number | null;
}

export interface ProjectsResponse {
    projects: Project[];
}

export interface ConversationHistory {
    thread_id: string;
    messages: Message[];
    created_at?: string;
}

// WebSocket stream events
export interface StreamEvent {
    type: 'init' | 'stream' | 'content' | 'thinking' | 'tool_call' | 'tool_result' | 'insight_start' | 'final' | 'error' | 'end';
    thread_id?: string;
    content?: string;
    tool?: string;
    error?: string;
    seq?: number;
    agent?: string;
    // Message IDs sent with 'end' event for edit/feedback functionality
    user_message_id?: string;
    assistant_message_id?: string;
}

export interface ChatState {
    messages: Message[];
    isStreaming: boolean;
    threadId: string | null;
    streamingContent: string;
}
