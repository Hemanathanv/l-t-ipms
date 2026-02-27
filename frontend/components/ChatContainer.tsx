'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { MapPin, Calendar, Building2, TrendingUp, Clock, FileSignature } from 'lucide-react';
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

    // When only one project exists, select it by default
    useEffect(() => {
        const projects = projectsData?.projects;
        if (projects?.length === 1 && !selectedProjectKey) {
            setSelectedProjectKey(String(projects[0].project_key));
        }
    }, [projectsData?.projects, selectedProjectKey]);

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

    // Start: Actual → Forecast → Planned. End: Forecast → Contractual → Planned. Labels use "Planned" instead of "Baseline".
    const startDateDisplay = selectedProject
        ? (() => {
            const v = selectedProject.actual_start_date ?? selectedProject.forecast_start_date ?? selectedProject.baseline_start_date ?? selectedProject.start_date ?? null;
            const label = selectedProject.actual_start_date ? 'Start Date (Actual)' : selectedProject.forecast_start_date ? 'Start Date (Forecast)' : 'Start Date (Planned)';
            return { label, value: v };
        })()
        : null;
    const endDateDisplay = selectedProject
        ? (() => {
            const v = selectedProject.forecast_finish_date ?? selectedProject.contractual_finish_date ?? selectedProject.baseline_finish_date ?? selectedProject.end_date ?? null;
            const label = selectedProject.forecast_finish_date ? 'End Date (Forecast)' : selectedProject.contractual_finish_date ? 'End Date (Contractual)' : 'End Date (Planned)';
            return { label, value: v };
        })()
        : null;

    return (
        <div className="flex h-screen w-full bg-[var(--chat-surface)]">
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
                                    <h1 className="welcome-heading">What would you like to know?</h1>
                                    <p className="welcome-subtitle">Ask me about your projects, metrics, deadlines, or team performance.</p>
                                    <MessageInput
                                        onSend={handleSendMessage}
                                        isLoading={isStreaming}
                                    />
                                </div>
                            </div>
                        )}
                    </div>

                    {selectedProject && (
                        <aside className="project-info-card project-panel-ref">
                            <div className="project-info-card-header">
                                <div className="flex items-center gap-2">
                                    <div className="project-panel-icon-wrap">
                                        <Building2 size={14} />
                                    </div>
                                    <span className="text-[0.75rem] font-semibold uppercase tracking-wider text-muted-foreground">Active Project</span>
                                </div>
                                <h3 className="project-info-card-title mt-2">{selectedProject.project_description || selectedProject.name}</h3>
                            </div>
                            <div className="project-info-card-body">
                                {selectedProject.location && (
                                    <div className="project-panel-row">
                                        <MapPin size={14} className="project-panel-row-icon" />
                                        <div>
                                            <p className="project-panel-label">Location</p>
                                            <p className="project-panel-value">{selectedProject.location}</p>
                                        </div>
                                    </div>
                                )}
                                {startDateDisplay && (
                                    <div className="project-panel-row">
                                        <Calendar size={14} className="project-panel-row-icon" />
                                        <div>
                                            <p className="project-panel-label">{startDateDisplay.label}</p>
                                            <p className="project-panel-value">
                                                {startDateDisplay.value ? new Date(startDateDisplay.value).toLocaleDateString() : '—'}
                                            </p>
                                        </div>
                                    </div>
                                )}
                                {endDateDisplay && (
                                    <div className="project-panel-row">
                                        <Calendar size={14} className="project-panel-row-icon" />
                                        <div>
                                            <p className="project-panel-label">{endDateDisplay.label}</p>
                                            <p className="project-panel-value">
                                                {endDateDisplay.value ? new Date(endDateDisplay.value).toLocaleDateString() : '—'}
                                            </p>
                                        </div>
                                    </div>
                                )}
                                {/* Contract Start / End */}
                                <div className="project-panel-row">
                                    <FileSignature size={14} className="project-panel-row-icon" />
                                    <div className="flex-1 min-w-0">
                                        <p className="project-panel-label">Contract Start Date</p>
                                        <p className="project-panel-value">
                                            {selectedProject.contract_start_date ? new Date(selectedProject.contract_start_date).toLocaleDateString() : '—'}
                                        </p>
                                    </div>
                                </div>
                                <div className="project-panel-row">
                                    <FileSignature size={14} className="project-panel-row-icon" />
                                    <div className="flex-1 min-w-0">
                                        <p className="project-panel-label">Contract End Date</p>
                                        <p className="project-panel-value">
                                            {selectedProject.contract_end_date ? new Date(selectedProject.contract_end_date).toLocaleDateString() : '—'}
                                        </p>
                                    </div>
                                </div>
                                {/* Progress — label "Progress" with bar and % on same row */}
                                {(selectedProject.progress_pct != null || (selectedProject.elapsed_days != null && selectedProject.total_days != null)) && (
                                    <div className="project-panel-row project-panel-progress-row">
                                        <TrendingUp size={14} className="project-panel-row-icon" />
                                        <div className="flex-1 min-w-0">
                                            <p className="project-panel-label">Progress</p>
                                            {selectedProject.progress_pct != null && (() => {
                                                const pct = Number(selectedProject.progress_pct);
                                                const displayPct = pct <= 1 ? pct * 100 : pct;
                                                const width = Math.min(100, Math.max(0, displayPct));
                                                return (
                                                    <div className="project-panel-progress-wrap">
                                                        <div className="project-panel-progress-bar">
                                                            <div className="project-panel-progress-fill" style={{ width: `${width}%` }} />
                                                        </div>
                                                        <span className="project-panel-progress-pct">{displayPct.toFixed(0)}%</span>
                                                    </div>
                                                );
                                            })()}
                                            {selectedProject.progress_pct == null && selectedProject.elapsed_days != null && selectedProject.total_days != null && (
                                                <p className="project-panel-value">{selectedProject.elapsed_days} of {selectedProject.total_days} days</p>
                                            )}
                                        </div>
                                    </div>
                                )}
                                {/* Duration — intelligent: when elapsed > total show overrun */}
                                {selectedProject.elapsed_days != null && selectedProject.total_days != null && (
                                    <div className="project-panel-row">
                                        <Clock size={14} className="project-panel-row-icon" />
                                        <div>
                                            <p className="project-panel-label">Duration</p>
                                            <p className="project-panel-value">
                                                {selectedProject.elapsed_days <= selectedProject.total_days
                                                    ? `${selectedProject.elapsed_days} of ${selectedProject.total_days} days elapsed`
                                                    : `${selectedProject.total_days} days total · ${selectedProject.elapsed_days} elapsed (${selectedProject.elapsed_days - selectedProject.total_days} days overrun)`
                                                }
                                            </p>
                                        </div>
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
