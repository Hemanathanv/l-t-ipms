export const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
// Strip any /ws/chat suffix from WS_BASE to prevent double paths
const rawWsBase = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000';
export const WS_BASE = rawWsBase.replace(/\/ws\/chat\/?$/, '');
export const getWsUrl = (threadId?: string | null) => `${WS_BASE}/ws/chat/${threadId || 'new'}`;
