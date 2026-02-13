/**
 * Auth client for FastAPI backend.
 * Matches Better Auth API signatures for seamless migration.
 */

import { API_BASE } from './api';

// Types
export interface User {
    id: string;
    name: string;
    email: string;
    systemRole: string;
    isActive: boolean;
}

export interface AuthResult {
    data?: {
        user: User;
        token?: string;
    };
    error?: {
        message: string;
        code?: string;
    };
}

// Store token in memory and persistent storage
let authToken: string | null = null;

/**
 * Initialize auth from persistent storage
 */
function initializeAuthToken(): void {
    if (typeof window === 'undefined') return;
    authToken = sessionStorage.getItem('auth_token') || localStorage.getItem('auth_token');
}

/**
 * Get stored auth token
 */
export function getAuthToken(): string | null {
    if (!authToken && typeof window !== 'undefined') {
        initializeAuthToken();
    }
    return authToken;
}

/**
 * Set auth token in memory and persistent storage
 */
export function setAuthToken(token: string | null): void {
    authToken = token;
    if (typeof window !== 'undefined') {
        if (token) {
            sessionStorage.setItem('auth_token', token);
            localStorage.setItem('auth_token', token);
        } else {
            sessionStorage.removeItem('auth_token');
            localStorage.removeItem('auth_token');
        }
    }
}

/**
 * Sign in with email and password.
 * Matches Better Auth signIn.email() API.
 */
export const signIn = {
    email: async ({ email, password }: { email: string; password: string }): Promise<AuthResult> => {
        try {
            const response = await fetch(`${API_BASE}/auth/login`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                credentials: 'include', // Include cookies
                body: JSON.stringify({ email, password }),
            });

            const data = await response.json();

            if (!response.ok) {
                return {
                    error: {
                        message: data.detail || 'Login failed',
                        code: String(response.status),
                    },
                };
            }

            // Store token
            if (data.token) {
                setAuthToken(data.token);
            }

            return {
                data: {
                    user: data.user,
                    token: data.token,
                },
            };
        } catch (error) {
            return {
                error: {
                    message: error instanceof Error ? error.message : 'Network error',
                },
            };
        }
    },
};

/**
 * Sign out the current user.
 * Matches Better Auth signOut() API.
 */
export async function signOut(): Promise<{ error?: { message: string } }> {
    try {
        const headers: Record<string, string> = {
            'Content-Type': 'application/json',
        };

        if (authToken) {
            headers['Authorization'] = `Bearer ${authToken}`;
        }

        await fetch(`${API_BASE}auth/logout`, {
            method: 'POST',
            headers,
            credentials: 'include',
        });

        // Clear stored token
        setAuthToken(null);

        return {};
    } catch (error) {
        return {
            error: {
                message: error instanceof Error ? error.message : 'Logout failed',
            },
        };
    }
}

/**
 * Get current session.
 */
export async function getSession(): Promise<{ user: User | null }> {
    try {
        const headers: Record<string, string> = {};

        if (authToken) {
            headers['Authorization'] = `Bearer ${authToken}`;
        }

        const response = await fetch(`${API_BASE}auth/session`, {
            method: 'GET',
            headers,
            credentials: 'include',
        });

        if (!response.ok) {
            return { user: null };
        }

        const data = await response.json();
        return { user: data.user || null };
    } catch (error) {
        return { user: null };
    }
}

/**
 * Auth client object for additional methods.
 * Matches Better Auth authClient API.
 */
export const authClient = {
    /**
     * Change password.
     * Requires old password verification.
     */
    changePassword: async ({
        oldPassword,
        newPassword,
    }: {
        oldPassword: string;
        newPassword: string;
    }): Promise<{ error?: { message: string } }> => {
        try {
            const headers: Record<string, string> = {
                'Content-Type': 'application/json',
            };

            if (authToken) {
                headers['Authorization'] = `Bearer ${authToken}`;
            }

            const response = await fetch(`${API_BASE}auth/change-password`, {
                method: 'POST',
                headers,
                credentials: 'include',
                body: JSON.stringify({
                    old_password: oldPassword,
                    new_password: newPassword,
                }),
            });

            const data = await response.json();

            if (!response.ok) {
                return {
                    error: {
                        message: data.detail || 'Failed to change password',
                    },
                };
            }

            return {};
        } catch (error) {
            return {
                error: {
                    message: error instanceof Error ? error.message : 'Network error',
                },
            };
        }
    },

    /**
     * Placeholder for requestPasswordReset - not implemented (per requirements).
     */
    requestPasswordReset: async (_params: { email: string; redirectTo?: string }) => {
        return {
            error: {
                message: 'Password reset via email is not supported. Please use change password.',
            },
        };
    },

    /**
     * Placeholder for resetPassword - not implemented (per requirements).
     */
    resetPassword: async (_params: { newPassword: string; token: string }) => {
        return {
            error: {
                message: 'Password reset via email is not supported. Please use change password.',
            },
        };
    },
};

// Re-export signUp as a placeholder (not implemented per requirements)
export const signUp = {
    email: async (_params: { name: string; email: string; password: string }) => {
        return {
            error: {
                message: 'Sign up is disabled. Please contact an administrator.',
            },
        };
    },
};
