export interface Message {
    id?: string;
    role: 'user' | 'assistant';
    content: string;
    created_at?: string;
    feedback?: 'positive' | 'negative' | null;
    feedbackNote?: string;
    editedFrom?: string;
}

export interface Conversation {
    threadId: string;
    title: string;
    createdAt: string;
}

export interface Project {
    id: string;
    name: string;
}

export interface ProjectsResponse {
    projects: Project[];
    dateRange: {
        from: string;
        to: string;
    };
}

export interface ConversationHistory {
    thread_id: string;
    messages: Message[];
    created_at?: string;
}

// WebSocket stream events
export interface StreamEvent {
    type: 'init' | 'stream' | 'content' | 'thinking' | 'tool_call' | 'tool_result' | 'final' | 'error' | 'end';
    thread_id?: string;
    content?: string;
    tool?: string;
    error?: string;
    seq?: number;
    agent?: string;
}

export interface ChatState {
    messages: Message[];
    isStreaming: boolean;
    threadId: string | null;
    streamingContent: string;
}
