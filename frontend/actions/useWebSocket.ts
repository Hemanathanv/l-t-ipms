'use client';

import { useEffect, useRef, useCallback, useState } from 'react';
import { WS_URL } from '@/lib/api';
import { StreamEvent } from '@/lib/types';

interface UseWebSocketOptions {
    onMessage: (event: StreamEvent) => void;
    onOpen?: () => void;
    onClose?: () => void;
    onError?: (error: Event) => void;
}

export function useWebSocket(options: UseWebSocketOptions) {
    const { onMessage, onOpen, onClose, onError } = options;
    const wsRef = useRef<WebSocket | null>(null);
    const [isConnected, setIsConnected] = useState(false);
    const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

    const connect = useCallback(() => {
        if (wsRef.current?.readyState === WebSocket.OPEN) return;

        const ws = new WebSocket(WS_URL);

        ws.onopen = () => {
            setIsConnected(true);
            onOpen?.();
        };

        ws.onmessage = (event) => {
            try {
                const data: StreamEvent = JSON.parse(event.data);
                onMessage(data);
            } catch (e) {
                console.error('Failed to parse WebSocket message:', e);
            }
        };

        ws.onclose = () => {
            setIsConnected(false);
            onClose?.();
            // Auto-reconnect after 3 seconds
            reconnectTimeoutRef.current = setTimeout(() => {
                connect();
            }, 3000);
        };

        ws.onerror = (error) => {
            console.error('WebSocket error:', error);
            onError?.(error);
        };

        wsRef.current = ws;
    }, [onMessage, onOpen, onClose, onError]);

    const disconnect = useCallback(() => {
        if (reconnectTimeoutRef.current) {
            clearTimeout(reconnectTimeoutRef.current);
        }
        wsRef.current?.close();
        wsRef.current = null;
        setIsConnected(false);
    }, []);

    const sendMessage = useCallback((data: object) => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify(data));
        } else {
            console.error('WebSocket is not connected');
        }
    }, []);

    useEffect(() => {
        return () => {
            disconnect();
        };
    }, [disconnect]);

    return {
        isConnected,
        connect,
        disconnect,
        sendMessage,
    };
}
