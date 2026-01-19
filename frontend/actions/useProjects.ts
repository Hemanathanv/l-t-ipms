'use client';

import { useQuery } from '@tanstack/react-query';
import { API_BASE } from '@/lib/api';
import { ProjectsResponse } from '@/lib/types';

async function fetchProjects(): Promise<ProjectsResponse> {
    const response = await fetch(`${API_BASE}/api/projects`);
    if (!response.ok) throw new Error('Failed to load projects');
    return response.json();
}

export function useProjects() {
    return useQuery({
        queryKey: ['projects'],
        queryFn: fetchProjects,
    });
}
