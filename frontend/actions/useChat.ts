'use client';

import { useState, useCallback, useRef, useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { getWsUrl, API_BASE } from '@/lib/api';
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
    const [thinkingContent, setThinkingContent] = useState('');
    const [isThinking, setIsThinking] = useState(false);
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
        setIsThinking(true);  // Start in thinking state
        setThinkingContent('');
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
                    case 'thinking':
                        // Show thinking indicator with content
                        console.log(`[FE-THINKING] received, content_len=${data.content?.length || 0}`);
                        setIsThinking(true);
                        if (data.content) {
                            setThinkingContent(prev => prev + data.content);  // Accumulate thinking content
                        }
                        break;
                    case 'stream':
                    case 'content':
                        // Once we start streaming actual content, we're done thinking
                        setIsThinking(false);
                        if (data.content) {
                            accumulatedContentRef.current += data.content;
                            console.log(`[FE-STREAM] seq=${data.seq}, accumulated_len=${accumulatedContentRef.current.length}`);
                            // Display streaming content (no need to filter - backend handles it)
                            setStreamingContent(accumulatedContentRef.current);
                        }
                        break;
                    case 'tool_call':
                        // Show tool call indicator
                        // Reset accumulated content - backend will stream fresh response after tool
                        accumulatedContentRef.current = '';
                        setStreamingContent('');
                        setIsThinking(false);
                        setThinkingContent('');
                        if (data.tool) {
                            setCurrentToolCall(data.tool);
                        }
                        break;
                    case 'tool_result':
                        // Tool completed - clear tool call indicator
                        // Ready for fresh streaming from follow-up LLM call
                        setCurrentToolCall(null);
                        setIsThinking(true);  // LLM will think again after tool result
                        break;
                    case 'end':
                        // Finalize the message
                        const finalContent = accumulatedContentRef.current;
                        const finalThinking = thinkingContent;  // Preserve thinking content
                        console.log(`[FE-END] finalContent_len=${finalContent.length}, thinkingContent_len=${finalThinking.length}`);

                        // Extract message IDs from end event
                        const userMessageId = data.user_message_id;
                        const assistantMessageId = data.assistant_message_id;
                        console.log(`[FE-END] user_message_id=${userMessageId}, assistant_message_id=${assistantMessageId}`);

                        // Clear streaming state FIRST to prevent showing both streaming + final
                        accumulatedContentRef.current = '';
                        setStreamingContent('');
                        // Don't clear thinkingContent - keep it for display
                        setIsThinking(false);
                        setCurrentToolCall(null);
                        setIsStreaming(false);

                        // Then add the finalized message with proper IDs
                        const filteredContent = filterThinkTags(finalContent);
                        console.log(`[FE-END] filteredContent_len=${filteredContent.length}, adding to messages`);

                        setMessages(prev => {
                            const newMessages = [...prev];

                            // Update the last user message with its ID (if available)
                            if (userMessageId) {
                                const lastUserIndex = newMessages.map(m => m.role).lastIndexOf('user');
                                if (lastUserIndex !== -1 && !newMessages[lastUserIndex].id) {
                                    newMessages[lastUserIndex] = { ...newMessages[lastUserIndex], id: userMessageId };
                                }
                            }

                            // Add assistant message with its ID
                            if (filteredContent) {
                                const assistantMessage: Message = {
                                    role: 'assistant',
                                    content: filteredContent,
                                    id: assistantMessageId || undefined
                                };
                                newMessages.push(assistantMessage);
                            }

                            return newMessages;
                        });

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

    const submitFeedback = useCallback(async (messageId: string, feedback: 'positive' | 'negative', note?: string) => {
        try {
            const response = await fetch(`${API_BASE}/messages/${messageId}/feedback`, {
                method: 'POST',
                credentials: 'include',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ feedback, note }),
            });

            if (!response.ok) {
                throw new Error('Failed to submit feedback');
            }

            // Optimistically update UI
            setMessages(prev => prev.map(msg =>
                msg.id === messageId
                    ? { ...msg, feedback, feedbackNote: note }
                    : msg
            ));

        } catch (error) {
            console.error('Error submitting feedback:', error);
            // Revert changes if needed or show toast
        }
    }, []);

    const editMessage = useCallback(async (messageId: string, newContent: string) => {
        try {
            // Find the message index to truncate messages after it
            setMessages(prev => {
                const index = prev.findIndex(m => m.id === messageId);
                if (index === -1) return prev;
                // Keep messages up to including this one (content will be updated)
                const newMessages = prev.slice(0, index + 1);
                // Update content
                newMessages[index] = { ...newMessages[index], content: newContent };
                return newMessages;
            });

            setIsStreaming(true);
            setIsThinking(true);
            setThinkingContent('');
            setStreamingContent('');
            setCurrentToolCall(null);
            accumulatedContentRef.current = '';
            onStreamStart?.();

            const response = await fetch(`${API_BASE}/messages/${messageId}/edit`, {
                method: 'PUT',
                credentials: 'include',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ content: newContent }),
            });

            if (!response.ok || !response.body) {
                throw new Error('Failed to edit message');
            }

            // Valid stream, start reading SSE with buffering for partial chunks
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';  // Buffer for incomplete SSE events

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                // Append new chunk to buffer
                buffer += decoder.decode(value, { stream: true });

                // Process complete SSE events (separated by double newline)
                const eventBoundary = buffer.lastIndexOf('\n\n');
                if (eventBoundary === -1) continue; // No complete events yet

                const completeData = buffer.slice(0, eventBoundary);
                buffer = buffer.slice(eventBoundary + 2); // Keep incomplete part

                const lines = completeData.split('\n\n');

                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;

                    try {
                        const jsonStr = line.slice(6);
                        if (!jsonStr) continue;

                        const data: StreamEvent = JSON.parse(jsonStr);

                        // Reuse switch logic - duplicated for now for simplicity
                        // Ideally extract `handleStreamEvent` fn
                        switch (data.type) {
                            case 'thinking':
                                console.log(`[FE-THINKING] received, content_len=${data.content?.length || 0}`);
                                setIsThinking(true);
                                if (data.content) {
                                    setThinkingContent(prev => prev + data.content);
                                }
                                break;
                            case 'stream':
                            case 'content':
                                setIsThinking(false);
                                if (data.content) {
                                    accumulatedContentRef.current += data.content;
                                    setStreamingContent(accumulatedContentRef.current);
                                }
                                break;
                            case 'tool_call':
                                accumulatedContentRef.current = '';
                                setStreamingContent('');
                                setIsThinking(false);
                                setThinkingContent('');
                                if (data.tool) setCurrentToolCall(data.tool);
                                break;
                            case 'tool_result':
                                setCurrentToolCall(null);
                                setIsThinking(true);
                                break;
                            case 'end':
                                const finalContent = accumulatedContentRef.current;
                                accumulatedContentRef.current = '';
                                setStreamingContent('');
                                setIsThinking(false);
                                setCurrentToolCall(null);
                                setIsStreaming(false);

                                const filteredContent = filterThinkTags(finalContent);
                                if (filteredContent) {
                                    const assistantMessage: Message = { role: 'assistant', content: filteredContent };
                                    setMessages(prev => [...prev, assistantMessage]);
                                }
                                onStreamEnd?.();
                                queryClient.invalidateQueries({ queryKey: ['conversations'] });
                                break;
                            case 'error':
                                console.error('SSE Error:', data.error);
                                break;
                        }
                    } catch (e) {
                        console.error('Error parsing SSE:', e);
                    }
                }
            }

        } catch (error) {
            console.error('Error editing message:', error);
            setIsStreaming(false);
            onStreamEnd?.();
        }
    }, [queryClient, onStreamStart, onStreamEnd]);

    // Switch to a different branch (version) of a message
    const switchBranch = useCallback(async (messageId: string, branchIndex: number) => {
        if (!threadId) return;

        try {
            const response = await fetch(
                `${API_BASE}/messages/${messageId}/switch-branch/${branchIndex}`,
                {
                    method: 'PUT',
                    credentials: 'include',
                    headers: { 'Content-Type': 'application/json' },
                }
            );

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to switch branch');
            }

            // Reload conversation to get the updated branch
            const convResponse = await fetch(
                `${API_BASE}/conversations/${threadId}`,
                { credentials: 'include' }
            );

            if (convResponse.ok) {
                const data = await convResponse.json();
                setMessages(data.messages || []);
            }

            // Invalidate cache
            queryClient.invalidateQueries({ queryKey: ['conversations'] });

        } catch (error) {
            console.error('Error switching branch:', error);
        }
    }, [threadId, queryClient]);

    return {
        messages,
        isStreaming,
        threadId,
        streamingContent,
        thinkingContent,
        isThinking,
        currentToolCall,
        isConnected,
        sendMessage,
        editMessage,
        submitFeedback,
        loadConversation,
        startNewChat,
        stopStreaming,
        setThreadId,
        switchBranch,
    };
}
