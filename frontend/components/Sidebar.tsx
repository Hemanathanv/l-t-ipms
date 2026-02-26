'use client';

import React, { useState } from "react"
import { Menu, X, Plus, Trash2 } from 'lucide-react';
import {
    Sidebar as SidebarUI,
    SidebarContent as SidebarUIContent,
    SidebarHeader,
    SidebarTrigger,
    useSidebar,
} from '@/components/ui/sidebar';
import { useConversations, useDeleteConversation } from '@/actions/useConversations';
import { Conversation } from '@/lib/types';

interface SidebarProps {
    currentThreadId: string | null;
    onSelectConversation: (threadId: string) => void;
    onNewChat: () => void;
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

function SidebarInnerContent({
    currentThreadId,
    onSelectConversation,
    onNewChat,
}: Omit<SidebarProps, 'isOpen' | 'onClose'>) {
    const { data: conversations, isLoading } = useConversations();
    const deleteConversation = useDeleteConversation();
    const { setOpen } = useSidebar();

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
        <>
            <SidebarHeader className="border-b">
                {/* Logo and Trigger Row */}
                <div className="sidebar-header-row">
                    {/* Logo - always visible */}
                    <div className="sidebar-logo">
                        <img
                            src="/logo.png"
                            alt="L&T-IPMS"
                            className="w-8 h-8 object-contain"
                            onError={(e) => {
                                // Fallback to text if image doesn't exist
                                e.currentTarget.style.display = 'none';
                                e.currentTarget.nextElementSibling?.classList.remove('hidden');
                            }}
                        />
                        <span className="hidden text-lg font-bold text-blue-600">LT</span>
                    </div>

                    {/* Title - hidden when collapsed */}
                    <h1 className="sidebar-title group-data-[collapsible=icon]:hidden">
                        L&T-IPMS
                    </h1>

                    {/* Sidebar Trigger - on right, hidden when collapsed, appears on hover */}
                    <div className="sidebar-trigger-wrapper">
                        <SidebarTrigger className="sidebar-trigger-btn" />
                    </div>
                </div>

                {/* New Chat Button */}
                <button
                    onClick={() => {
                        onNewChat();
                        setOpen(false);
                    }}
                    className="sidebar-new-chat-btn mt-3 w-full flex items-center justify-center gap-2 px-4 py-2 rounded-lg transition-all active:scale-[0.98] group-data-[collapsible=icon]:w-8 group-data-[collapsible=icon]:h-8 group-data-[collapsible=icon]:p-0 group-data-[collapsible=icon]:mt-2"
                >
                    <Plus size={18} />
                    <span className="group-data-[collapsible=icon]:hidden">New Chat</span>
                </button>
            </SidebarHeader>
            <SidebarUIContent className="flex flex-col gap-1 p-3 group-data-[collapsible=icon]:hidden">
                {isLoading ? (
                    <p className="text-sm text-gray-500 text-center py-4">Loading...</p>
                ) : !conversations?.length ? (
                    <p className="text-sm text-gray-500 text-center py-4">No conversations yet</p>
                ) : (
                    conversations.map((conv: Conversation) => (
                        <div
                            key={conv.threadId}
                            className={`sidebar-conv-item group p-2.5 rounded-lg cursor-pointer transition-all border ${conv.threadId === currentThreadId
                                ? 'sidebar-conv-item-active'
                                : 'sidebar-conv-item-inactive'
                                }`}
                            onClick={() => {
                                onSelectConversation(conv.threadId);
                                setOpen(false);
                            }}
                        >
                            <div className="flex items-start justify-between gap-2">
                                <div className="flex-1 min-w-0">
                                    <p className="sidebar-conv-title truncate">
                                        {conv.title || 'Untitled'}
                                    </p>
                                    <p className="sidebar-conv-date">
                                        {formatDate(conv.createdAt)}
                                    </p>
                                </div>
                                <button
                                    className="sidebar-conv-delete opacity-0 group-hover:opacity-100 p-1.5 rounded transition-all"
                                    onClick={(e) => handleDelete(e, conv.threadId)}
                                    title="Delete conversation"
                                >
                                    <Trash2 size={14} />
                                </button>
                            </div>
                        </div>
                    ))
                )}
            </SidebarUIContent>
        </>
    );
}

export function Sidebar({
    currentThreadId,
    onSelectConversation,
    onNewChat,
}: SidebarProps) {
    return (
        <SidebarUI collapsible="icon">
            <SidebarInnerContent
                currentThreadId={currentThreadId}
                onSelectConversation={onSelectConversation}
                onNewChat={onNewChat}
            />
        </SidebarUI>
    );
}
