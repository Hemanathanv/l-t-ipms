'use client';

import { useState, useCallback, useRef, useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { getWsUrl } from '@/lib/api';
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
    const [isConnected, setIsConnected] = useState(false);
    const queryClient = useQueryClient();
    const wsRef = useRef<WebSocket | null>(null);
    const accumulatedContentRef = useRef('');
    const pendingMessageRef = useRef<{ content: string; projectId?: string } | null>(null);
    const currentThreadIdRef = useRef<string | null>(null);

    // Helper to send message on a WebSocket
    const sendMessageInternal = useCallback((ws: WebSocket, content: string, projectId?: string) => {
        // Add user message immediately
        const userMessage: Message = { role: 'user', content };
        setMessages(prev => [...prev, userMessage]);
        setIsStreaming(true);
        setStreamingContent('');
        setCurrentToolCall(null);
        accumulatedContentRef.current = '';
        onStreamStart?.();

        // Send message via WebSocket (thread_id is now in the URL path)
        ws.send(JSON.stringify({
            message: content,
            project_id: projectId || null,
        }));
    }, [onStreamStart]);

    // Connect to WebSocket with specific thread
    const connect = useCallback((wsThreadId?: string | null) => {
        // Close existing connection if connecting to a different thread
        if (wsRef.current) {
            wsRef.current.close();
            wsRef.current = null;
        }

        currentThreadIdRef.current = wsThreadId || null;
        const wsUrl = getWsUrl(wsThreadId);
        console.log('[WS] Connecting to:', wsUrl);
        const ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            console.log('[WS] Connected');
            setIsConnected(true);

            // If there's a pending message, send it now
            if (pendingMessageRef.current) {
                const { content, projectId } = pendingMessageRef.current;
                pendingMessageRef.current = null;
                sendMessageInternal(ws, content, projectId);
            }
        };

        ws.onmessage = (event) => {
            try {
                const data: StreamEvent = JSON.parse(event.data);

                switch (data.type) {
                    case 'init':
                        // Update threadId from server (especially for new chats)
                        if (data.thread_id) {
                            setThreadId(data.thread_id);
                            currentThreadIdRef.current = data.thread_id;
                        }
                        break;
                    case 'stream':
                    case 'content':
                        if (data.content) {
                            accumulatedContentRef.current += data.content;
                            // Filter think tags in real-time and display
                            setStreamingContent(filterThinkTags(accumulatedContentRef.current));
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
                        const filteredContent = filterThinkTags(accumulatedContentRef.current);
                        if (filteredContent) {
                            const assistantMessage: Message = { role: 'assistant', content: filteredContent };
                            setMessages(prev => [...prev, assistantMessage]);
                            setStreamingContent('');
                        }
                        accumulatedContentRef.current = '';
                        setCurrentToolCall(null);
                        setIsStreaming(false);
                        onStreamEnd?.();
                        // Invalidate conversations list to refresh sidebar
                        queryClient.invalidateQueries({ queryKey: ['conversations'] });
                        break;
                    case 'error':
                        console.error('WebSocket error:', data.error);
                        setCurrentToolCall(null);
                        setIsStreaming(false);
                        onStreamEnd?.();
                        break;
                }
            } catch (e) {
                console.error('Failed to parse WebSocket message:', e);
            }
        };

        ws.onclose = () => {
            console.log('[WS] Disconnected');
            setIsConnected(false);
        };

        ws.onerror = () => {
            // WebSocket onerror events don't contain useful info
            // The actual error handling happens in onclose
            console.debug('[WS] Connection error - will retry on close');
        };

        wsRef.current = ws;
    }, [queryClient, onStreamEnd, sendMessageInternal]);

    // Connect on mount for new chat
    useEffect(() => {
        connect(null);
        return () => {
            wsRef.current?.close();
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

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

        // Reconnect WebSocket to the loaded thread
        connect(newThreadId);
    }, [connect]);

    const startNewChat = useCallback(() => {
        setMessages([]);
        setThreadId(null);
        setStreamingContent('');
        setCurrentToolCall(null);

        // Connect to a new WebSocket for new chat
        connect(null);
    }, [connect]);

    const sendMessage = useCallback((content: string, projectId?: string) => {
        // If not connected, store message and connect
        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
            pendingMessageRef.current = { content, projectId };
            connect(currentThreadIdRef.current);
            return;
        }

        sendMessageInternal(wsRef.current, content, projectId);
    }, [connect, sendMessageInternal]);

    const stopStreaming = useCallback(() => {
        // Close and reconnect to stop the current stream
        wsRef.current?.close();
        setIsStreaming(false);
        setCurrentToolCall(null);
    }, []);

    return {
        messages,
        isStreaming,
        threadId,
        streamingContent,
        currentToolCall,
        isConnected,
        sendMessage,
        loadConversation,
        startNewChat,
        stopStreaming,
        setThreadId,
    };
}
