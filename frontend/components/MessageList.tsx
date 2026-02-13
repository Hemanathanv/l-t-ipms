'use client';

import { useRef, useEffect, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Message } from '@/lib/types';

interface MessageListProps {
    messages: Message[];
    streamingContent: string;
    isStreaming: boolean;
    isThinking?: boolean;
    thinkingContent?: string;
    currentToolCall?: string | null;
    onEditMessage?: (id: string, newContent: string) => void;
    onFeedback?: (id: string, feedback: 'positive' | 'negative') => void;
    onSwitchBranch?: (messageId: string, branchIndex: number) => void;
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

// Collapsible thinking indicator - ChatGPT style
function ThinkingIndicator({ isThinking, thinkingContent }: { isThinking: boolean; thinkingContent?: string }) {
    const [isExpanded, setIsExpanded] = useState(false);
    const [thinkingSeconds, setThinkingSeconds] = useState(0);

    useEffect(() => {
        if (!isThinking) {
            return;
        }

        const interval = setInterval(() => {
            setThinkingSeconds(prev => prev + 1);
        }, 1000);

        return () => clearInterval(interval);
    }, [isThinking]);

    // Reset timer when new thinking session starts
    useEffect(() => {
        if (isThinking) {
            setThinkingSeconds(0);
        }
    }, [isThinking]);

    if (!isThinking && !thinkingContent) return null;

    return (
        <div className="thinking-indicator">
            <button
                className="thinking-toggle"
                onClick={() => setIsExpanded(!isExpanded)}
            >
                {/* <span className="thinking-icon">💭</span> */}
                <span className="thinking-label">
                    {isThinking ? (
                        <>Thinking for {thinkingSeconds}s</>
                    ) : (
                        <>Thought for {thinkingSeconds}s</>
                    )}
                </span>
                <span className={`thinking-chevron ${isExpanded ? 'expanded' : ''}`}>
                    ›
                </span>
            </button>
            {isExpanded && thinkingContent && (
                <div className="thinking-content">
                    <MarkdownContent content={thinkingContent} />
                </div>
            )}
        </div>
    );
}

import { MessageActions } from '@/components/MessageActions';

export function MessageList({
    messages,
    streamingContent,
    isStreaming,
    isThinking = false,
    thinkingContent = '',
    currentToolCall,
    onEditMessage,
    onFeedback,
    onSwitchBranch
}: MessageListProps) {
    const containerRef = useRef<HTMLDivElement>(null);
    const [editingId, setEditingId] = useState<string | null>(null);
    const [editContent, setEditContent] = useState('');

    useEffect(() => {
        if (containerRef.current) {
            containerRef.current.scrollTop = containerRef.current.scrollHeight;
        }
    }, [messages, streamingContent, currentToolCall, isThinking]);

    const handleCopy = (content: string) => {
        navigator.clipboard.writeText(content);
    };

    const handleEditStart = (id: string, content: string) => {
        setEditingId(id);
        setEditContent(content);
    };

    const handleEditSubmit = () => {
        if (editingId && onEditMessage) {
            onEditMessage(editingId, editContent);
            setEditingId(null);
        }
    };

    const handleEditCancel = () => {
        setEditingId(null);
        setEditContent('');
    };

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

                {messages.map((message, index) => {
                    const messageKey = message.id || `msg-${index}`;
                    const isEditing = editingId === messageKey;

                    return (
                        <div key={index} className={`message ${message.role}`}>
                            <div className="message-avatar">
                                {message.role === 'user' ? '👤' : '🤖'}
                            </div>
                            <div className="message-body">
                                <div className="message-content">
                                    {isEditing ? (
                                        <div className="edit-mode">
                                            <textarea
                                                value={editContent}
                                                onChange={(e) => setEditContent(e.target.value)}
                                                className="edit-textarea"
                                                rows={3}
                                                autoFocus
                                            />
                                            <div className="edit-actions">
                                                <button className="btn-cancel" onClick={handleEditCancel}>Cancel</button>
                                                <button className="btn-send" onClick={handleEditSubmit}>Send</button>
                                            </div>
                                        </div>
                                    ) : (
                                        <>
                                            {message.role === 'assistant' ? (
                                                <MarkdownContent content={message.content} />
                                            ) : (
                                                message.content
                                            )}
                                        </>
                                    )}
                                </div>
                                {/* Actions below the message */}
                                {!isEditing && (
                                    <MessageActions
                                        message={message}
                                        messageIndex={index}
                                        onCopy={handleCopy}
                                        onEdit={onEditMessage ? handleEditStart : undefined}
                                        onFeedback={onFeedback}
                                    />
                                )}
                            </div>
                        </div>
                    );
                })}

                {isStreaming && (
                    <div className="message assistant streaming">
                        <div className="message-avatar">🤖</div>
                        <div className="message-content">
                            {/* Thinking indicator - ChatGPT style */}
                            <ThinkingIndicator isThinking={isThinking} thinkingContent={thinkingContent} />

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
                        {!currentToolCall && !isThinking && streamingContent && (
                            <div className="streaming-cursor">▊</div>
                        )}
                    </div>
                )}
            </div>

            <style jsx>{`
                .edit-mode {
                    width: 100%;
                    min-width: 400px;
                    background: transparent;
                    border-radius: 16px;
                    padding: 8px;
                }
                .edit-textarea {
                    width: 100%;
                    padding: 12px;
                    border: none;
                    border-radius: 12px;
                    background: rgba(255, 255, 255, 0.15);
                    color: white;
                    resize: none;
                    font-family: inherit;
                    font-size: 1rem;
                    line-height: 1.5;
                    margin-bottom: 12px;
                    outline: none;
                }
                .edit-textarea::placeholder {
                    color: rgba(255, 255, 255, 0.7);
                }
                .edit-actions {
                    display: flex;
                    gap: 8px;
                    justify-content: flex-end;
                }
                .btn-cancel {
                    background: white;
                    color: #333;
                    border: 1px solid #d9d9d9;
                    padding: 8px 16px;
                    border-radius: 20px;
                    cursor: pointer;
                    font-size: 0.875rem;
                    font-weight: 500;
                    transition: all 0.2s ease;
                }
                .btn-cancel:hover {
                    background: #f5f5f5;
                }
                .btn-send {
                    background: #1a1a1a;
                    color: white;
                    border: none;
                    padding: 8px 16px;
                    border-radius: 20px;
                    cursor: pointer;
                    font-size: 0.875rem;
                    font-weight: 500;
                    transition: all 0.2s ease;
                }
                .btn-send:hover {
                    background: #333;
                }
            `}</style>
        </div>
    );
}
