'use client';

import { useState, useCallback, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { API_BASE } from '@/lib/api';
import { Message, StreamEvent } from '@/lib/types';

interface UseChatOptions {
    onStreamStart?: () => void;
    onStreamEnd?: () => void;
}

// Filter out <think>...</think> content from Qwen model responses
function filterThinkTags(content: string): string {
    return content.replace(/<think>[\s\S]*?<\/think>/g, '').trim();
}

export function useChat(options: UseChatOptions = {}) {
    const { onStreamStart, onStreamEnd } = options;
    const [messages, setMessages] = useState<Message[]>([]);
    const [isStreaming, setIsStreaming] = useState(false);
    const [threadId, setThreadId] = useState<string | null>(null);
    const [streamingContent, setStreamingContent] = useState('');
    const [currentToolCall, setCurrentToolCall] = useState<string | null>(null);
    const queryClient = useQueryClient();
    const abortControllerRef = useRef<AbortController | null>(null);

    const loadConversation = useCallback((newMessages: Message[], newThreadId: string) => {
        // Filter think tags from loaded messages
        const filteredMessages = newMessages.map(m => ({
            ...m,
            content: filterThinkTags(m.content)
        }));
        setMessages(filteredMessages);
        setThreadId(newThreadId);
        setStreamingContent('');
        setCurrentToolCall(null);
    }, []);

    const startNewChat = useCallback(() => {
        setMessages([]);
        setThreadId(null);
        setStreamingContent('');
        setCurrentToolCall(null);
    }, []);

    const sendMessage = useCallback(async (content: string, projectId?: string) => {
        // Add user message immediately
        const userMessage: Message = { role: 'user', content };
        setMessages(prev => [...prev, userMessage]);
        setIsStreaming(true);
        setStreamingContent('');
        setCurrentToolCall(null);
        onStreamStart?.();

        // Abort any existing request
        abortControllerRef.current?.abort();
        abortControllerRef.current = new AbortController();

        try {
            const response = await fetch(`${API_BASE}/chat/stream`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: content,
                    thread_id: threadId,
                    project_id: projectId || null,
                }),
                signal: abortControllerRef.current.signal,
            });

            if (!response.ok) throw new Error('Failed to start stream');

            const reader = response.body?.getReader();
            if (!reader) throw new Error('No response body');

            const decoder = new TextDecoder();
            let buffer = '';
            let accumulatedContent = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data: StreamEvent = JSON.parse(line.slice(6));

                            switch (data.type) {
                                case 'init':
                                    if (data.thread_id && !threadId) {
                                        setThreadId(data.thread_id);
                                    }
                                    break;
                                case 'stream':
                                case 'content':
                                    if (data.content) {
                                        accumulatedContent += data.content;
                                        // Filter think tags in real-time and display
                                        setStreamingContent(filterThinkTags(accumulatedContent));
                                    }
                                    break;
                                case 'tool_call':
                                    // Show tool call indicator
                                    if (data.tool) {
                                        setCurrentToolCall(data.tool);
                                    }
                                    break;
                                case 'tool_result':
                                    // Tool completed - clear tool call indicator
                                    setCurrentToolCall(null);
                                    break;
                                case 'end':
                                    // Finalize the message
                                    const filteredContent = filterThinkTags(accumulatedContent);
                                    if (filteredContent) {
                                        const assistantMessage: Message = { role: 'assistant', content: filteredContent };
                                        setMessages(prev => [...prev, assistantMessage]);
                                        setStreamingContent('');
                                    }
                                    setCurrentToolCall(null);
                                    break;
                                case 'error':
                                    console.error('Stream error:', data.error);
                                    setCurrentToolCall(null);
                                    break;
                            }
                        } catch (e) {
                            console.error('Failed to parse SSE data:', e);
                        }
                    }
                }
            }

            // Invalidate conversations list to refresh sidebar
            queryClient.invalidateQueries({ queryKey: ['conversations'] });
        } catch (error) {
            if ((error as Error).name !== 'AbortError') {
                console.error('Chat error:', error);
                const errorMessage: Message = {
                    role: 'assistant',
                    content: `Error: ${(error as Error).message}`
                };
                setMessages(prev => [...prev, errorMessage]);
            }
        } finally {
            setIsStreaming(false);
            setStreamingContent('');
            setCurrentToolCall(null);
            onStreamEnd?.();
        }
    }, [threadId, queryClient, onStreamStart, onStreamEnd]);

    const stopStreaming = useCallback(() => {
        abortControllerRef.current?.abort();
        setIsStreaming(false);
        setCurrentToolCall(null);
    }, []);

    return {
        messages,
        isStreaming,
        threadId,
        streamingContent,
        currentToolCall,
        sendMessage,
        loadConversation,
        startNewChat,
        stopStreaming,
        setThreadId,
    };
}
