'use client';

import { useState, useRef, useEffect, FormEvent } from 'react';

interface MessageInputProps {
    onSend: (message: string) => void;
    isLoading: boolean;
}

export function MessageInput({ onSend, isLoading }: MessageInputProps) {
    const [message, setMessage] = useState('');
    const textareaRef = useRef<HTMLTextAreaElement>(null);

    const autoResizeTextarea = () => {
        if (textareaRef.current) {
            textareaRef.current.style.height = 'auto';
            textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 120) + 'px';
        }
    };

    useEffect(() => {
        autoResizeTextarea();
    }, [message]);

    const handleSubmit = (e: FormEvent) => {
        e.preventDefault();
        const trimmedMessage = message.trim();
        if (!trimmedMessage || isLoading) return;

        onSend(trimmedMessage);
        setMessage('');
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSubmit(e as unknown as FormEvent);
        }
    };

    return (
        <div className="input-container">
            <form className="chat-form" onSubmit={handleSubmit}>
                <div className="input-wrapper">
                    <textarea
                        ref={textareaRef}
                        value={message}
                        onChange={(e) => setMessage(e.target.value)}
                        onKeyDown={handleKeyDown}
                        placeholder="Type your message..."
                        rows={1}
                        autoFocus
                    />
                    <button type="submit" className="send-btn" disabled={isLoading || !message.trim()}>
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M22 2L11 13M22 2L15 22L11 13L2 9L22 2Z" />
                        </svg>
                    </button>
                </div>
            </form>
        </div>
    );
}
