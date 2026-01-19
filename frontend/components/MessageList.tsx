'use client';

import { useRef, useEffect } from 'react';
import { Message } from '@/lib/types';

interface MessageListProps {
    messages: Message[];
    streamingContent: string;
    isStreaming: boolean;
    currentToolCall?: string | null;
}

function escapeHtml(text: string): string {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Format tool name for display (e.g., sra_status_pei -> SRA Status PEI)
function formatToolName(toolName: string): string {
    return toolName
        .split('_')
        .map(word => word.charAt(0).toUpperCase() + word.slice(1))
        .join(' ');
}

export function MessageList({ messages, streamingContent, isStreaming, currentToolCall }: MessageListProps) {
    const containerRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (containerRef.current) {
            containerRef.current.scrollTop = containerRef.current.scrollHeight;
        }
    }, [messages, streamingContent, currentToolCall]);

    return (
        <div className="chat-container" ref={containerRef}>
            <div className="messages-wrapper">
                {messages.length === 0 && !isStreaming && (
                    <div className="welcome-message">
                        <div className="welcome-icon">🤖</div>
                        <h2>Welcome to L&T IPMS Assistant</h2>
                        <p>Ask me anything about your projects, metrics, or get help with project management tasks.</p>
                    </div>
                )}

                {messages.map((message, index) => (
                    <div key={index} className={`message ${message.role}`}>
                        <div className="message-avatar">
                            {message.role === 'user' ? '👤' : '🤖'}
                        </div>
                        <div
                            className="message-content"
                            dangerouslySetInnerHTML={{ __html: escapeHtml(message.content) }}
                        />
                    </div>
                ))}

                {isStreaming && (
                    <div className="message assistant streaming">
                        <div className="message-avatar">🤖</div>
                        <div className="message-content">
                            {/* Tool call indicator */}
                            {currentToolCall && (
                                <div className="tool-call-indicator">
                                    <span className="tool-spinner">⚙️</span>
                                    <span>Calling {formatToolName(currentToolCall)}...</span>
                                </div>
                            )}
                            {/* Streaming content */}
                            {streamingContent || (!currentToolCall && '')}
                        </div>
                        {!currentToolCall && <div className="streaming-cursor">▊</div>}
                    </div>
                )}
            </div>
        </div>
    );
}
