'use client';

import { useState } from 'react';
import { Copy, Check, Pencil, ThumbsUp, ThumbsDown, ChevronLeft, ChevronRight } from 'lucide-react';
import { Message } from '@/lib/types';

interface MessageActionsProps {
    message: Message;
    messageIndex?: number;
    onCopy: (content: string) => void;
    onEdit?: (messageId: string, newContent: string) => void;
    onFeedback?: (messageId: string, feedback: 'positive' | 'negative') => void;
    onSwitchBranch?: (messageId: string, branchIndex: number) => void;
}

export function MessageActions({ message, messageIndex, onCopy, onEdit, onFeedback, onSwitchBranch }: MessageActionsProps) {
    const isUser = message.role === 'user';
    const [copied, setCopied] = useState(false);

    // Use message.id if available, otherwise use index as fallback
    const messageKey = message.id || `msg-${messageIndex}`;

    // Branch navigation
    const hasBranches = (message.total_branches || 1) > 1;
    const currentBranch = (message.branch_index ?? 0) + 1;  // Display as 1-indexed
    const totalBranches = message.total_branches || 1;

    const handleCopy = () => {
        onCopy(message.content);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    const handlePrevBranch = () => {
        if (message.id && onSwitchBranch && (message.branch_index ?? 0) > 0) {
            onSwitchBranch(message.id, (message.branch_index ?? 0) - 1);
        }
    };

    const handleNextBranch = () => {
        if (message.id && onSwitchBranch && currentBranch < totalBranches) {
            onSwitchBranch(message.id, (message.branch_index ?? 0) + 1);
        }
    };

    return (
        <div className={`message-actions ${isUser ? 'user-actions' : 'assistant-actions'}`}>
            {/* Assistant message actions - ChatGPT style */}
            {!isUser && (
                <>
                    <button
                        className="action-btn"
                        onClick={handleCopy}
                        title="Copy"
                    >
                        {copied ? <Check size={16} /> : <Copy size={16} />}
                    </button>

                    {onFeedback && (
                        <>
                            <button
                                className={`action-btn ${message.feedback === 'positive' ? 'active' : ''}`}
                                onClick={() => onFeedback(messageKey, 'positive')}
                                title="Good response"
                            >
                                <ThumbsUp size={16} />
                            </button>
                            <button
                                className={`action-btn ${message.feedback === 'negative' ? 'active' : ''}`}
                                onClick={() => onFeedback(messageKey, 'negative')}
                                title="Bad response"
                            >
                                <ThumbsDown size={16} />
                            </button>
                        </>
                    )}

                    {/* Branch navigation for assistant messages */}
                    {hasBranches && onSwitchBranch && (
                        <div className="branch-nav">
                            <button
                                className="action-btn"
                                onClick={handlePrevBranch}
                                disabled={currentBranch <= 1}
                                title="Previous version"
                            >
                                <ChevronLeft size={16} />
                            </button>
                            <span className="branch-counter">{currentBranch}/{totalBranches}</span>
                            <button
                                className="action-btn"
                                onClick={handleNextBranch}
                                disabled={currentBranch >= totalBranches}
                                title="Next version"
                            >
                                <ChevronRight size={16} />
                            </button>
                        </div>
                    )}
                </>
            )}

            {/* User message actions */}
            {isUser && (
                <>
                    <button
                        className="action-btn"
                        onClick={handleCopy}
                        title="Copy"
                    >
                        {copied ? <Check size={16} /> : <Copy size={16} />}
                    </button>

                    {onEdit && (
                        <button
                            className="action-btn"
                            onClick={() => onEdit(messageKey, message.content)}
                            title="Edit message"
                        >
                            <Pencil size={16} />
                        </button>
                    )}

                    {/* Branch navigation for user messages */}
                    {hasBranches && onSwitchBranch && (
                        <div className="branch-nav">
                            <button
                                className="action-btn"
                                onClick={handlePrevBranch}
                                disabled={currentBranch <= 1}
                                title="Previous version"
                            >
                                <ChevronLeft size={16} />
                            </button>
                            <span className="branch-counter">{currentBranch}/{totalBranches}</span>
                            <button
                                className="action-btn"
                                onClick={handleNextBranch}
                                disabled={currentBranch >= totalBranches}
                                title="Next version"
                            >
                                <ChevronRight size={16} />
                            </button>
                        </div>
                    )}
                </>
            )}
        </div>
    );
}
