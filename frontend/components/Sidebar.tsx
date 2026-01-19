'use client';

import { useConversations, useDeleteConversation } from '@/actions/useConversations';
import { Conversation } from '@/lib/types';

interface SidebarProps {
    currentThreadId: string | null;
    onSelectConversation: (threadId: string) => void;
    onNewChat: () => void;
    isOpen: boolean;
    onClose: () => void;
}

function formatDate(dateString: string) {
    if (!dateString) return '';
    const date = new Date(dateString);
    const now = new Date();
    const diff = now.getTime() - date.getTime();

    if (diff < 86400000) {
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } else if (diff < 604800000) {
        return date.toLocaleDateString([], { weekday: 'short' });
    }
    return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

export function Sidebar({
    currentThreadId,
    onSelectConversation,
    onNewChat,
    isOpen,
    onClose
}: SidebarProps) {
    const { data: conversations, isLoading } = useConversations();
    const deleteConversation = useDeleteConversation();

    const handleDelete = async (e: React.MouseEvent, threadId: string) => {
        e.stopPropagation();
        if (confirm('Are you sure you want to delete this conversation?')) {
            deleteConversation.mutate(threadId);
            if (currentThreadId === threadId) {
                onNewChat();
            }
        }
    };

    return (
        <aside className={`sidebar ${isOpen ? 'open' : ''}`}>
            <div className="sidebar-header">
                <h1 className="logo">L&T-IPMS</h1>
                <button className="new-chat-btn" onClick={() => { onNewChat(); onClose(); }}>
                    <span className="icon">+</span> New Chat
                </button>
            </div>
            <div className="conversations-list">
                {isLoading ? (
                    <p style={{ padding: '16px', color: 'var(--text-muted)' }}>Loading...</p>
                ) : !conversations?.length ? (
                    <p style={{ padding: '16px', color: 'var(--text-muted)' }}>No conversations yet</p>
                ) : (
                    conversations.map((conv: Conversation) => (
                        <div
                            key={conv.threadId}
                            className={`conversation-item ${conv.threadId === currentThreadId ? 'active' : ''}`}
                            onClick={() => { onSelectConversation(conv.threadId); onClose(); }}
                        >
                            <div className="conversation-content">
                                <div className="conversation-title">{conv.title || 'Untitled'}</div>
                                <div className="conversation-date">{formatDate(conv.createdAt)}</div>
                            </div>
                            <button
                                className="delete-btn"
                                onClick={(e) => handleDelete(e, conv.threadId)}
                                title="Delete conversation"
                            >
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                    <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
                                </svg>
                            </button>
                        </div>
                    ))
                )}
            </div>
        </aside>
    );
}
