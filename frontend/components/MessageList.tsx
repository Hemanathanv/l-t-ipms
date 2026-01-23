'use client';

import { useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Message } from '@/lib/types';

interface MessageListProps {
    messages: Message[];
    streamingContent: string;
    isStreaming: boolean;
    currentToolCall?: string | null;
}

// Format tool name for display (e.g., sra_status_pei -> SRA Status PEI)
function formatToolName(toolName: string): string {
    return toolName
        .split('_')
        .map(word => word.charAt(0).toUpperCase() + word.slice(1))
        .join(' ');
}

// Markdown component for rendering AI messages
function MarkdownContent({ content }: { content: string }) {
    return (
        <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
                // Custom code block rendering
                code({ className, children, ...props }) {
                    const match = /language-(\w+)/.exec(className || '');
                    const isInline = !match;
                    return isInline ? (
                        <code className="inline-code" {...props}>
                            {children}
                        </code>
                    ) : (
                        <pre className="code-block">
                            <code className={className} {...props}>
                                {children}
                            </code>
                        </pre>
                    );
                },
                // Custom table rendering
                table({ children }) {
                    return (
                        <div className="table-wrapper">
                            <table>{children}</table>
                        </div>
                    );
                },
            }}
        >
            {content}
        </ReactMarkdown>
    );
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
                        <div className="message-content">
                            {message.role === 'assistant' ? (
                                <MarkdownContent content={message.content} />
                            ) : (
                                message.content
                            )}
                        </div>
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
                            {/* Streaming content with markdown */}
                            {streamingContent && <MarkdownContent content={streamingContent} />}
                        </div>
                        {!currentToolCall && <div className="streaming-cursor">▊</div>}
                    </div>
                )}
            </div>
        </div>
    );
}

