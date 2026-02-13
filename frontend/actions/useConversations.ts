'use client';

import { useEffect, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { API_BASE } from '@/lib/api';
import { Conversation, ConversationHistory } from '@/lib/types';

// Track preloaded conversations to avoid duplicate calls
const preloadedConversations = new Set<string>();

// Fetch all conversations
async function fetchConversations(): Promise<Conversation[]> {
    const response = await fetch(`${API_BASE}/conversations`);
    if (!response.ok) throw new Error('Failed to load conversations');
    return response.json();
}

// Fetch single conversation
async function fetchConversation(threadId: string): Promise<ConversationHistory> {
    const response = await fetch(`${API_BASE}/conversations/${threadId}`, { credentials: 'include' });
    if (!response.ok) throw new Error('Failed to load conversation');
    return response.json();
}

// Delete conversation
async function deleteConversationApi(threadId: string): Promise<void> {
    const response = await fetch(`${API_BASE}/conversations/${threadId}`, {
        credentials: 'include',
        method: 'DELETE',
    });
    if (!response.ok) throw new Error('Failed to delete conversation');
}

// Pre-warm cache when conversation is about to be loaded
async function preloadConversation(threadId: string): Promise<void> {
    // Skip if already preloaded
    if (preloadedConversations.has(threadId)) {
        return;
    }
    preloadedConversations.add(threadId);

    try {
        await fetch(`${API_BASE}/conversations/${threadId}/preload`, {
            credentials: 'include',
            method: 'POST',
        });
    } catch (error) {
        console.error('Failed to preload conversation:', error);
        // Remove from set so it can be retried
        preloadedConversations.delete(threadId);
    }
}

export function useConversations() {
    return useQuery({
        queryKey: ['conversations'],
        queryFn: fetchConversations,
    });
}

export function useConversation(threadId: string | null) {
    // Pre-warm cache when threadId changes (using useEffect to avoid render-time side effects)
    useEffect(() => {
        if (threadId) {
            preloadConversation(threadId);
        }
    }, [threadId]);

    return useQuery({
        queryKey: ['conversation', threadId],
        queryFn: () => fetchConversation(threadId!),
        enabled: !!threadId,
        staleTime: 30000, // Cache for 30 seconds before refetching
        gcTime: 60000,    // Keep in memory for 1 minute after becoming unused
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
