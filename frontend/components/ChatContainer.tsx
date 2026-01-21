'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Sidebar } from '@/components/Sidebar';
import { ChatHeader } from '@/components/ChatHeader';
import { MessageList } from '@/components/MessageList';
import { MessageInput } from '@/components/MessageInput';
import { useChat } from '@/actions/useChat';
import { useConversation } from '@/actions/useConversations';

interface ChatContainerProps {
    initialThreadId?: string;
}

export function ChatContainer({ initialThreadId }: ChatContainerProps) {
    const router = useRouter();
    const [selectedProjectId, setSelectedProjectId] = useState('');
    const [sidebarOpen, setSidebarOpen] = useState(false);

    const {
        messages,
        isStreaming,
        threadId,
        streamingContent,
        currentToolCall,
        sendMessage,
        loadConversation,
        startNewChat,
        setThreadId,
    } = useChat();

    // Load conversation if initialThreadId is provided
    const { data: conversationData } = useConversation(initialThreadId || null);

    useEffect(() => {
        if (initialThreadId && conversationData) {
            loadConversation(conversationData.messages, initialThreadId);
        }
    }, [initialThreadId, conversationData, loadConversation]);

    // Update URL when threadId changes - use history API to avoid remount
    useEffect(() => {
        if (threadId && !initialThreadId) {
            const expectedPath = `/chat/${threadId}`;
            // Only update if not already on the correct path
            if (window.location.pathname !== expectedPath) {
                // Use history.replaceState to update URL without remounting component
                // This preserves the chat state during the first message
                window.history.replaceState(
                    { ...window.history.state, as: expectedPath, url: expectedPath },
                    '',
                    expectedPath
                );
            }
        }
    }, [threadId, initialThreadId]);

    const handleSelectConversation = (selectedThreadId: string) => {
        router.push(`/chat/${selectedThreadId}`);
    };

    const handleNewChat = () => {
        startNewChat();
        router.push('/');
    };

    const handleSendMessage = (content: string) => {
        sendMessage(content, selectedProjectId || undefined);
    };

    const getChatTitle = () => {
        if (messages.length > 0) {
            const firstUserMessage = messages.find(m => m.role === 'user');
            if (firstUserMessage) {
                return firstUserMessage.content.length > 30
                    ? firstUserMessage.content.substring(0, 30) + '...'
                    : firstUserMessage.content;
            }
        }
        return 'New Conversation';
    };

    return (
        <div className="app-container">
            <Sidebar
                currentThreadId={threadId}
                onSelectConversation={handleSelectConversation}
                onNewChat={handleNewChat}
                isOpen={sidebarOpen}
                onClose={() => setSidebarOpen(false)}
            />
            <main className="main-content">
                <ChatHeader
                    title={getChatTitle()}
                    selectedProjectId={selectedProjectId}
                    onProjectChange={setSelectedProjectId}
                    onMenuToggle={() => setSidebarOpen(!sidebarOpen)}
                />
                <MessageList
                    messages={messages}
                    streamingContent={streamingContent}
                    isStreaming={isStreaming}
                    currentToolCall={currentToolCall}
                />
                <MessageInput
                    onSend={handleSendMessage}
                    isLoading={isStreaming}
                />
            </main>
        </div>
    );
}
