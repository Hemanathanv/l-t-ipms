'use client';

import { useRef, useEffect, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import html2canvas from 'html2canvas';
import { Message } from '@/lib/types';

// Avatar icons from public/ (root)
const AVATAR_USER = '/human.svg';
const AVATAR_BOT = '/bot.svg';

// Dynamic AI sphere / bubble for insight loading (rotating + subtle wave)
function InsightLoadingSphere() {
    return (
        <div className="insight-loading-wrap" aria-hidden>
            <div className="insight-sphere">
                <div className="insight-sphere-inner" />
            </div>
            <span className="insight-loading-label">Preparing insight…</span>
        </div>
    );
}

interface MessageListProps {
    messages: Message[];
    streamingContent: string;
    isStreaming: boolean;
    isThinking?: boolean;
    thinkingContent?: string;
    currentToolCall?: string | null;
    toolOutput?: string | null;
    isInsight?: boolean;
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

// Collapsible tool output block — shows raw data from tool execution
function ToolOutputBlock({ content }: { content: string }) {
    const [isExpanded, setIsExpanded] = useState(true);

    return (
        <div className="tool-output-block">
            <button
                className="tool-output-toggle"
                onClick={() => setIsExpanded(!isExpanded)}
            >
                <span className="tool-output-icon">{'\uD83D\uDCCA'}</span>
                <span>Data Retrieved</span>
                <span className="toggle-chevron">{isExpanded ? '\u25BE' : '\u25B8'}</span>
            </button>
            {isExpanded && (
                <div className="tool-output-content">
                    <MarkdownContent content={content} />
                </div>
            )}
        </div>
    );
}

// Dynamic messages shown while thinking (no seconds)
const THINKING_PHRASES = [
    'Thinking…',
    'Analyzing your question…',
    'Checking project data…',
    'Preparing response…',
    'Reviewing context…',
    'Gathering information…',
];

// Collapsible thinking indicator — dynamic label, no seconds
function ThinkingIndicator({ isThinking, thinkingContent }: { isThinking: boolean; thinkingContent?: string }) {
    const [isExpanded, setIsExpanded] = useState(false);
    const [phraseIndex, setPhraseIndex] = useState(0);

    useEffect(() => {
        if (!isThinking) return;
        const interval = setInterval(() => {
            setPhraseIndex((i) => (i + 1) % THINKING_PHRASES.length);
        }, 2200);
        return () => clearInterval(interval);
    }, [isThinking]);

    if (!isThinking && !thinkingContent) return null;

    return (
        <div className="thinking-indicator thinking-bubble">
            <button
                className="thinking-toggle"
                onClick={() => setIsExpanded(!isExpanded)}
                type="button"
            >
                <span className="thinking-dots" aria-hidden>
                    <span className="thinking-dot" />
                    <span className="thinking-dot" />
                    <span className="thinking-dot" />
                </span>
                <span className="thinking-label">
                    {isThinking ? THINKING_PHRASES[phraseIndex] : 'Thought process'}
                </span>
                <span className={`thinking-chevron ${isExpanded ? 'expanded' : ''}`} aria-hidden>
                    {'\u203A'}
                </span>
            </button>
            {isExpanded && (
                <div className="thinking-content">
                    {isThinking ? (
                        <p className="thinking-placeholder">Processing…</p>
                    ) : (
                        thinkingContent && <MarkdownContent content={thinkingContent} />
                    )}
                </div>
            )}
        </div>
    );
}

import { MessageActions } from '@/components/MessageActions';

// Helper: render assistant content, splitting on INSIGHT marker if present
function AssistantContent({ content }: { content: string }) {
    const marker = '<!-- INSIGHT -->';
    const idx = content.indexOf(marker);
    if (idx !== -1) {
        const dataPart = content.slice(0, idx).trim();
        const insightPart = content.slice(idx + marker.length).trim();
        return (
            <>
                <MarkdownContent content={dataPart} />
                <div className="ai-insight-card">
                    <div className="ai-insight-header">
                        <span className="ai-insight-icon" aria-hidden>
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 3l1.5 3 3 .5-2 2.5.5 3L12 11l-2.5 1.5.5-3-2-2.5 3-.5L12 3z"/></svg>
                        </span>
                        <span>AI Insight</span>
                    </div>
                    <div className="ai-insight-body">
                        <MarkdownContent content={insightPart} />
                    </div>
                </div>
            </>
        );
    }
    return <MarkdownContent content={content} />;
}

export function MessageList({
    messages,
    streamingContent,
    isStreaming,
    isThinking = false,
    thinkingContent = '',
    currentToolCall,
    toolOutput,
    isInsight = false,
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
    }, [messages, streamingContent, currentToolCall, isThinking, toolOutput]);

    const handleCopy = (content: string) => {
        navigator.clipboard.writeText(content);
    };

    const handleCopyImage = async (element: HTMLElement): Promise<boolean> => {
        try {
            const canvas = await html2canvas(element, {
                useCORS: true,
                scale: 2,
                logging: false,
                backgroundColor: '#f7f7f7',
                ignoreElements: (el) => el.classList.contains('message-actions'),
            });
            const blob = await new Promise<Blob | null>((resolve) => {
                canvas.toBlob(resolve, 'image/png', 1);
            });
            if (!blob) return false;
            if (navigator.clipboard?.write) {
                try {
                    await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]);
                    return true;
                } catch {
                    // Fall through to download fallback
                }
            }
            // Fallback: download the image so user can save it
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'message-screenshot.png';
            a.click();
            URL.revokeObjectURL(url);
            return true;
        } catch {
            return false;
        }
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
                        <div className="welcome-icon">
                            <img src={AVATAR_BOT} alt="" aria-hidden />
                        </div>
                        <h2>Experience smarter conversations</h2>
                        <p>Ask about your projects, metrics, deadlines, or get help with project management—powered by AI.</p>
                    </div>
                )}

                {messages.map((message, index) => {
                    const messageKey = message.id || `msg-${index}`;
                    const isEditing = editingId === messageKey;

                    return (
                        <div key={index} className={`message ${message.role} message-enter`}>
                            <div className="message-avatar">
                                <img src={message.role === 'user' ? AVATAR_USER : AVATAR_BOT} alt={message.role === 'user' ? 'User' : 'Assistant'} />
                            </div>
                            <div className="message-body">
                                <div className={`message-content${message.role === 'assistant' ? ' prose-chat' : ''}`}>
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
                                                <AssistantContent content={message.content} />
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
                                        onCopyImage={handleCopyImage}
                                        onEdit={onEditMessage ? handleEditStart : undefined}
                                        onFeedback={onFeedback}
                                        onSwitchBranch={onSwitchBranch}
                                    />
                                )}
                            </div>
                        </div>
                    );
                })}

                {isStreaming && (
                    <div className="message assistant streaming message-enter">
                        <div className="message-avatar">
                            <img src={AVATAR_BOT} alt="Assistant" />
                        </div>
                        <div className="message-body">
                            <div className="message-content prose-chat">
                                {/* Thinking indicator — generic label; no specific details while thinking */}
                                <ThinkingIndicator isThinking={isThinking} thinkingContent={thinkingContent} />

                                {/* Tool call indicator */}
                                {currentToolCall && (
                                    <div className="tool-call-indicator">
                                        <span className="tool-spinner" aria-hidden>
                                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>
                                        </span>
                                        <span>Calling {formatToolName(currentToolCall)}…</span>
                                    </div>
                                )}

                                {/* Tool output as plain markdown (outside insight card) */}
                                {toolOutput && <MarkdownContent content={toolOutput} />}

                                {/* AI Insight: while filling, show only dynamic sphere — no content inside card until done */}
                                {isInsight ? (
                                    <div className="ai-insight-card ai-insight-loading">
                                        <div className="ai-insight-header">
                                            <span className="ai-insight-icon" aria-hidden>
                                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 3l1.5 3 3 .5-2 2.5.5 3L12 11l-2.5 1.5.5-3-2-2.5 3-.5L12 3z"/></svg>
                                            </span>
                                            <span>AI Insight</span>
                                        </div>
                                        <div className="ai-insight-body">
                                            <InsightLoadingSphere />
                                        </div>
                                    </div>
                                ) : streamingContent ? (
                                    <MarkdownContent content={streamingContent} />
                                ) : null}
                            </div>
                            {!currentToolCall && !isThinking && streamingContent && !isInsight && (
                                <span className="streaming-cursor" aria-hidden />
                            )}
                        </div>
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
