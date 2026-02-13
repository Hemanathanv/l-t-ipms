export const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
// Strip any /ws/chat suffix from WS_BASE to prevent double paths
const rawWsBase = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000';
export const WS_BASE = rawWsBase.replace(/\/ws\/chat\/?$/, '');

// Get auth token from sessionStorage or localStorage
export const getAuthToken = (): string | null => {
    if (typeof window === 'undefined') return null;
    return sessionStorage.getItem('auth_token') || localStorage.getItem('auth_token');
};

// Get authorization headers with token
export const getAuthHeaders = () => {
    const token = getAuthToken();
    return token ? { 'Authorization': `Bearer ${token}` } : {};
};

export const apiFetch = async (
    endpoint: string,
    options: RequestInit = {}
): Promise<Response> => {
    // Build full URL
    const url = endpoint.startsWith('http') ? endpoint : `${API_BASE}${endpoint}`;
    
    // Get authorization headers
    const authHeaders = getAuthHeaders();
    
    // Merge headers with auth token
    const headers = {
        'Content-Type': 'application/json',
        ...authHeaders,
        ...(options.headers as Record<string, string> || {}),
    };
    
    const response = await fetch(url, {
        ...options,
        credentials: 'include',
    });
    
    // Handle 401 Unauthorized - token expired or invalid
    if (response.status === 401) {
        // Clear token from storage
        if (typeof window !== 'undefined') {
            sessionStorage.removeItem('auth_token');
            localStorage.removeItem('auth_token');
        }
        // Redirect to login if needed
        if (typeof window !== 'undefined' && window.location.pathname !== '/login') {
            console.warn('Unauthorized - Token expired or invalid');
        }
    }
    
    return response;
};

export const getWsUrl = (threadId?: string | null, token?: string) => {
    const baseUrl = `${WS_BASE}/ws/chat/${threadId || 'new'}`;
    const authToken = token || getAuthToken();
    if (authToken) {
        return `${baseUrl}?token=${encodeURIComponent(authToken)}`;
    }
    return baseUrl;
};
