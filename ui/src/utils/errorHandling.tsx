import React, { useState, useCallback } from 'react';

// Error types
export interface APIError {
  success: false;
  error: {
    error_id: string;
    error_code: string;
    message: string;
    user_message: string;
    troubleshooting?: string;
    timestamp: string;
    path?: string;
    details?: Record<string, any>;
  };
}

export interface NMSError {
  errorId: string;
  errorCode: string;
  message: string;
  userMessage: string;
  troubleshooting?: string;
  timestamp: string;
  path?: string;
  details?: Record<string, any>;
}

// Hook for handling API errors
export const useErrorHandler = () => {
  const [error, setError] = useState<NMSError | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  const handleError = useCallback((err: any) => {
    console.error('API Error:', err);

    if (err?.error) {
      // This is our structured API error
      const apiError = err as APIError;
      setError({
        errorId: apiError.error.error_id,
        errorCode: apiError.error.error_code,
        message: apiError.error.message,
        userMessage: apiError.error.user_message,
        troubleshooting: apiError.error.troubleshooting,
        timestamp: apiError.error.timestamp,
        path: apiError.error.path,
        details: apiError.error.details
      });
    } else if (err instanceof Error) {
      // Generic JavaScript error
      setError({
        errorId: `FE_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
        errorCode: 'CLIENT_ERROR',
        message: err.message,
        userMessage: 'An unexpected error occurred in the application.',
        troubleshooting: 'Try refreshing the page. If the problem persists, contact support.',
        timestamp: new Date().toISOString()
      });
    } else {
      // Unknown error type
      setError({
        errorId: `FE_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
        errorCode: 'UNKNOWN_ERROR',
        message: 'Unknown error occurred',
        userMessage: 'Something went wrong. Please try again.',
        troubleshooting: 'Refresh the page and try again. Contact support if the issue continues.',
        timestamp: new Date().toISOString()
      });
    }
  }, []);

  const wrapAsync = useCallback(async <T,>(
    asyncFn: () => Promise<T>,
    showLoading = true
  ): Promise<T | null> => {
    if (showLoading) setIsLoading(true);
    clearError();

    try {
      const result = await asyncFn();
      return result;
    } catch (err) {
      handleError(err);
      return null;
    } finally {
      if (showLoading) setIsLoading(false);
    }
  }, [handleError, clearError]);

  return {
    error,
    isLoading,
    clearError,
    handleError,
    wrapAsync
  };
};

// Utility function to make API calls with error handling
export const apiCall = async <T,>(
  url: string,
  options?: RequestInit
): Promise<T> => {
  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers
    },
    ...options
  });

  if (!response.ok) {
    let errorData;
    try {
      errorData = await response.json();
    } catch {
      // If response is not JSON, create a generic error
      errorData = {
        success: false,
        error: {
          error_id: `HTTP_${Date.now()}`,
          error_code: 'HTTP_ERROR',
          message: `HTTP ${response.status}: ${response.statusText}`,
          user_message: `Request failed: ${response.statusText}`,
          troubleshooting: 'Check your network connection and try again.',
          timestamp: new Date().toISOString(),
          path: url
        }
      };
    }

    throw errorData;
  }

  return response.json();
};

// Error display component
interface ErrorDisplayProps {
  error: NMSError;
  onDismiss?: () => void;
  showDetails?: boolean;
}

export const ErrorDisplay: React.FC<ErrorDisplayProps> = ({
  error,
  onDismiss,
  showDetails = true
}) => {
  const getErrorIcon = (errorCode: string) => {
    switch (errorCode) {
      case 'VALIDATION_ERROR':
        return '⚠️';
      case 'RESOURCE_NOT_FOUND':
        return '🔍';
      case 'DATABASE_ERROR':
        return '💾';
      case 'NETWORK_ERROR':
        return '🌐';
      case 'DISCOVERY_ERROR':
        return '🔍';
      case 'AUTHENTICATION_ERROR':
        return '🔒';
      case 'PERMISSION_ERROR':
        return '🚫';
      default:
        return '❌';
    }
  };

  return (
    <div className="error-display" style={{
      padding: '1rem',
      margin: '1rem 0',
      border: '1px solid #ef4444',
      borderRadius: '0.5rem',
      backgroundColor: '#fef2f2',
      color: '#dc2626'
    }}>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: '0.5rem' }}>
        <span style={{ fontSize: '1.25rem', marginRight: '0.5rem' }}>
          {getErrorIcon(error.errorCode)}
        </span>
        <strong>Error {error.errorCode.replace(/_/g, ' ')}</strong>
        {onDismiss && (
          <button
            onClick={onDismiss}
            style={{
              marginLeft: 'auto',
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              fontSize: '1.25rem',
              color: '#dc2626'
            }}
            title="Dismiss error"
          >
            ×
          </button>
        )}
      </div>

      <div style={{ marginBottom: '0.5rem' }}>
        {error.userMessage}
      </div>

      {error.troubleshooting && (
        <div style={{
          padding: '0.5rem',
          backgroundColor: '#f9fafb',
          borderRadius: '0.25rem',
          border: '1px solid #e5e7eb',
          marginBottom: '0.5rem'
        }}>
          <strong>Troubleshooting:</strong> {error.troubleshooting}
        </div>
      )}

      {showDetails && (
        <details>
          <summary style={{ cursor: 'pointer', fontWeight: 'bold' }}>
            Technical Details (Error ID: {error.errorId})
          </summary>
          <div style={{
            marginTop: '0.5rem',
            padding: '0.5rem',
            backgroundColor: '#f9fafb',
            borderRadius: '0.25rem',
            fontFamily: 'monospace',
            fontSize: '0.75rem',
            border: '1px solid #e5e7eb'
          }}>
            <div><strong>Timestamp:</strong> {new Date(error.timestamp).toLocaleString()}</div>
            {error.path && <div><strong>Path:</strong> {error.path}</div>}
            {error.details && (
              <div>
                <strong>Details:</strong>
                <pre style={{ marginTop: '0.25rem', whiteSpace: 'pre-wrap' }}>
                  {JSON.stringify(error.details, null, 2)}
                </pre>
              </div>
            )}
          </div>
        </details>
      )}
    </div>
  );
};

// Loading spinner component
export const LoadingSpinner: React.FC<{ message?: string }> = ({
  message = "Loading..."
}) => (
  <div className="loading-spinner" style={{
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '2rem',
    color: '#6b7280'
  }}>
    <div style={{
      width: '1.5rem',
      height: '1.5rem',
      border: '2px solid #e5e7eb',
      borderTop: '2px solid #3b82f6',
      borderRadius: '50%',
      animation: 'spin 1s linear infinite',
      marginRight: '0.5rem'
    }} />
    {message}
    <style>{`
      @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
      }
    `}</style>
  </div>
);

// Higher-order component for error handling
export const withErrorHandler = <P extends object>(
  Component: React.ComponentType<P>
) => {
  return (props: P) => {
    const { error, clearError } = useErrorHandler();

    return (
      <>
        {error && (
          <ErrorDisplay
            error={error}
            onDismiss={clearError}
          />
        )}
        <Component {...props} />
      </>
    );
  };
};
