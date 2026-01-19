'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { API_BASE } from '@/lib/api';
import { Conversation, ConversationHistory } from '@/lib/types';

// Fetch all conversations
async function fetchConversations(): Promise<Conversation[]> {
    const response = await fetch(`${API_BASE}/api/conversations`);
    if (!response.ok) throw new Error('Failed to load conversations');
    return response.json();
}

// Fetch single conversation
async function fetchConversation(threadId: string): Promise<ConversationHistory> {
    const response = await fetch(`${API_BASE}/conversations/${threadId}`);
    if (!response.ok) throw new Error('Failed to load conversation');
    return response.json();
}

// Delete conversation
async function deleteConversationApi(threadId: string): Promise<void> {
    const response = await fetch(`${API_BASE}/conversations/${threadId}`, {
        method: 'DELETE',
    });
    if (!response.ok) throw new Error('Failed to delete conversation');
}

export function useConversations() {
    return useQuery({
        queryKey: ['conversations'],
        queryFn: fetchConversations,
    });
}

export function useConversation(threadId: string | null) {
    return useQuery({
        queryKey: ['conversation', threadId],
        queryFn: () => fetchConversation(threadId!),
        enabled: !!threadId,
    });
}

export function useDeleteConversation() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: deleteConversationApi,
        onMutate: async (threadId: string) => {
            // Cancel any outgoing refetches
            await queryClient.cancelQueries({ queryKey: ['conversations'] });

            // Snapshot the previous value
            const previousConversations = queryClient.getQueryData<Conversation[]>(['conversations']);

            // Optimistically update: remove the conversation from the list
            queryClient.setQueryData<Conversation[]>(['conversations'], (old) =>
                old ? old.filter(c => c.threadId !== threadId) : []
            );

            return { previousConversations };
        },
        onError: (err, threadId, context) => {
            // If the mutation fails, restore the previous value
            if (context?.previousConversations) {
                queryClient.setQueryData(['conversations'], context.previousConversations);
            }
        },
        onSettled: () => {
            // Always refetch after error or success
            queryClient.invalidateQueries({ queryKey: ['conversations'] });
        },
    });
}
