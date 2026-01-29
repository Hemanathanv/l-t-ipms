'use client';

import { useState } from 'react';
import { Copy, Check, Pencil, ThumbsUp, ThumbsDown } from 'lucide-react';
import { Message } from '@/lib/types';

interface MessageActionsProps {
    message: Message;
    messageIndex?: number;
    onCopy: (content: string) => void;
    onEdit?: (messageId: string, newContent: string) => void;
    onFeedback?: (messageId: string, feedback: 'positive' | 'negative') => void;
}

export function MessageActions({ message, messageIndex, onCopy, onEdit, onFeedback }: MessageActionsProps) {
    const isUser = message.role === 'user';
    const [copied, setCopied] = useState(false);

    // Use message.id if available, otherwise use index as fallback
    const messageKey = message.id || `msg-${messageIndex}`;

    const handleCopy = () => {
        onCopy(message.content);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
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
                </>
            )}
        </div>
    );
}

