'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { MapPin, Calendar, Building2 } from 'lucide-react';
import { SidebarProvider } from '@/components/ui/sidebar';
import { Sidebar } from '@/components/Sidebar';
import { ChatHeader } from '@/components/ChatHeader';
import { MessageList } from '@/components/MessageList';
import { MessageInput } from '@/components/MessageInput';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { useChat } from '@/actions/useChat';
import { useConversation } from '@/actions/useConversations';
import { useProjects } from '@/actions/useProjects';

interface ChatContainerProps {
    initialThreadId?: string;
}

// Inner component to access sidebar context
function ChatContainerInner({ initialThreadId }: ChatContainerProps) {
    const router = useRouter();
    const [selectedProjectKey, setSelectedProjectKey] = useState('');
    const { data: projectsData } = useProjects();

    const selectedProject = projectsData?.projects.find(
        (p) => String(p.project_key) === selectedProjectKey
    );

    const {
        messages,
        isStreaming,
        threadId,
        streamingContent,
        thinkingContent,
        isThinking,
        currentToolCall,
        toolOutput,
        isInsight,
        sendMessage,
        editMessage,
        submitFeedback,
        loadConversation,
        startNewChat,
        switchBranch,
    } = useChat();

    // Load conversation if initialThreadId is provided
    const { data: conversationData, isLoading: isLoadingConversation } = useConversation(initialThreadId || null);

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
        sendMessage(content, selectedProjectKey || undefined);
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

    const hasMessages = messages.length > 0 || isStreaming;

    return (
        <div className="flex h-screen w-full">
            <Sidebar
                currentThreadId={threadId}
                onSelectConversation={handleSelectConversation}
                onNewChat={handleNewChat}
            />
            <main className="main-content">
                <ChatHeader
                    title={getChatTitle()}
                    selectedProjectKey={selectedProjectKey}
                    onProjectChange={setSelectedProjectKey}
                    hideBorder={!hasMessages}
                />

                <div className="chat-area-wrapper">
                    <div className="chat-area-main">
                        {isLoadingConversation && initialThreadId ? (
                            // Loading state when fetching conversation history
                            <div className="flex-1 flex items-center justify-center">
                                <LoadingSpinner message="Loading conversation..." size="lg" />
                            </div>
                        ) : hasMessages ? (
                            // Normal chat layout with messages at top, input at bottom
                            <>
                                <MessageList
                                    messages={messages}
                                    streamingContent={streamingContent}
                                    isStreaming={isStreaming}
                                    isThinking={isThinking}
                                    thinkingContent={thinkingContent}
                                    currentToolCall={currentToolCall}
                                    toolOutput={toolOutput}
                                    isInsight={isInsight}
                                    onEditMessage={editMessage}
                                    onFeedback={submitFeedback}
                                    onSwitchBranch={switchBranch}
                                />
                                <MessageInput
                                    onSend={handleSendMessage}
                                    isLoading={isStreaming}
                                />
                            </>
                        ) : (
                            // Centered welcome layout for new conversations
                            <div className="welcome-container">
                                <div className="welcome-content">
                                    <h1 className="welcome-heading">What's on your mind today?</h1>
                                    <MessageInput
                                        onSend={handleSendMessage}
                                        isLoading={isStreaming}
                                    />
                                </div>
                            </div>
                        )}
                    </div>

                    {selectedProject && (
                        <aside className="project-info-card">
                            <div className="project-info-card-header">
                                <Building2 size={18} />
                                <span>Project Details</span>
                            </div>
                            <div className="project-info-card-body">
                                <h3 className="project-info-card-title">{selectedProject.project_description}</h3>
                                <div className="project-info-card-row">
                                    <MapPin size={14} />
                                    <span>{selectedProject.location}</span>
                                </div>
                                {selectedProject.start_date && selectedProject.end_date && (
                                    <div className="project-info-card-row">
                                        <Calendar size={14} />
                                        <span>
                                            {new Date(selectedProject.start_date).toLocaleDateString()} — {new Date(selectedProject.end_date).toLocaleDateString()}
                                        </span>
                                    </div>
                                )}
                            </div>
                        </aside>
                    )}
                </div>
            </main>
        </div>
    );
}

export function ChatContainer({ initialThreadId }: ChatContainerProps) {
    return (
        <SidebarProvider>
            <ChatContainerInner initialThreadId={initialThreadId} />
        </SidebarProvider>
    );
}
