'use client';

import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';
import { ProjectsResponse } from '@/lib/types';

/**
 * Fetch projects with automatic token authentication
 * Token is automatically included in Authorization header
 */
async function fetchProjects(): Promise<ProjectsResponse> {
    const response = await apiFetch('/auth/projects');
    console.log('fetchProjects response:', response);
    if (!response.ok) {
        throw new Error(`Failed to load projects: ${response.statusText}`);
    }
    return response.json();
}

export function useProjects() {
    return useQuery({
        queryKey: ['projects'],
        queryFn: fetchProjects,
        staleTime: 5 * 60 * 1000, // Cache for 5 minutes
        gcTime: 10 * 60 * 1000,    // Keep in memory for 10 minutes
    });
}