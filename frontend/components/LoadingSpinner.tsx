'use client';

interface LoadingSpinnerProps {
    message?: string;
    size?: 'sm' | 'md' | 'lg';
}

export function LoadingSpinner({ message = 'Loading...', size = 'md' }: LoadingSpinnerProps) {
    const sizeClasses = {
        sm: 'w-4 h-4 border-2',
        md: 'w-8 h-8 border-2',
        lg: 'w-12 h-12 border-3'
    };

    return (
        <div className="flex flex-col items-center gap-3">
            <div
                className={`${sizeClasses[size]} animate-spin rounded-full border-gray-200 border-t-blue-600`}
                style={{ borderTopColor: '#2563eb', borderColor: '#e5e7eb', borderTopWidth: size === 'lg' ? '3px' : '2px' }}
            />
            {message && (
                <p className="text-sm text-gray-500 animate-pulse">{message}</p>
            )}
        </div>
    );
}
