import React, { useState, useEffect } from 'react';

/**
 * AgentOAuthFlow - OAuth connection flow for third-party services
 * 
 * Props:
 * - agentId: string - ID of the agent initiating OAuth
 * - service: string - Name of the service (e.g., "GitHub", "Google", "Slack")
 * - scopes: array - List of permission scopes being requested
 * - onAction: function - Callback for OAuth events
 * - redirectUrl: string - OAuth redirect URL
 * - clientId: string - OAuth client ID
 * - authUrl: string - OAuth authorization URL
 * - description: string - What the connection will be used for
 */
const AgentOAuthFlow = ({ 
  agentId, 
  service = "Third-party Service",
  scopes = [],
  onAction,
  redirectUrl = window.location.origin + '/oauth/callback',
  clientId,
  authUrl,
  description = "Connect your account to enable enhanced functionality."
}) => {
  const [status, setStatus] = useState('ready'); // ready, connecting, connected, error
  const [authWindow, setAuthWindow] = useState(null);
  const [error, setError] = useState(null);
  const [connectionData, setConnectionData] = useState(null);

  // Service configurations
  const serviceConfig = {
    github: {
      icon: '🐙',
      color: 'text-gray-300',
      bg: 'bg-gray-500/10',
      border: 'border-gray-500/20'
    },
    google: {
      icon: '🔍',
      color: 'text-blue-400',
      bg: 'bg-blue-500/10',
      border: 'border-blue-500/20'
    },
    slack: {
      icon: '💬',
      color: 'text-purple-400',
      bg: 'bg-purple-500/10',
      border: 'border-purple-500/20'
    },
    discord: {
      icon: '🎮',
      color: 'text-indigo-400',
      bg: 'bg-indigo-500/10',
      border: 'border-indigo-500/20'
    },
    default: {
      icon: '🔗',
      color: 'text-cyan-400',
      bg: 'bg-cyan-500/10',
      border: 'border-cyan-500/20'
    }
  };

  const config = serviceConfig[service.toLowerCase()] || serviceConfig.default;

  // Listen for OAuth callback
  useEffect(() => {
    const handleMessage = (event) => {
      if (event.origin !== window.location.origin) return;
      
      if (event.data.type === 'oauth_success') {
        setStatus('connected');
        setConnectionData(event.data.data);
        setAuthWindow(null);
        
        onAction?.({
          type: 'oauth_success',
          agentId,
          data: {
            service,
            connectionData: event.data.data,
            scopes,
            timestamp: new Date().toISOString()
          }
        });
      } else if (event.data.type === 'oauth_error') {
        setStatus('error');
        setError(event.data.error);
        setAuthWindow(null);
        
        onAction?.({
          type: 'oauth_error',
          agentId,
          data: {
            service,
            error: event.data.error,
            timestamp: new Date().toISOString()
          }
        });
      }
    };

    window.addEventListener('message', handleMessage);
    
    return () => {
      window.removeEventListener('message', handleMessage);
      if (authWindow) {
        authWindow.close();
      }
    };
  }, [agentId, service, scopes, onAction, authWindow]);

  const initiateOAuth = () => {
    if (!authUrl || !clientId) {
      setError('OAuth configuration missing');
      setStatus('error');
      return;
    }

    setStatus('connecting');
    setError(null);

    // Build OAuth URL
    const oauthParams = new URLSearchParams({
      client_id: clientId,
      redirect_uri: redirectUrl,
      scope: scopes.join(' '),
      response_type: 'code',
      state: `${agentId}_${Date.now()}`
    });

    const oauthUrl = `${authUrl}?${oauthParams.toString()}`;

    // Open OAuth popup
    const popup = window.open(
      oauthUrl,
      'oauth_popup',
      'width=600,height=700,scrollbars=yes,resizable=yes'
    );

    setAuthWindow(popup);

    // Check if popup was blocked
    if (!popup || popup.closed) {
      setError('Popup blocked. Please allow popups for this site.');
      setStatus('error');
      return;
    }

    // Monitor popup closure
    const checkClosed = setInterval(() => {
      if (popup.closed) {
        clearInterval(checkClosed);
        if (status === 'connecting') {
          setStatus('ready');
          setError('Authorization cancelled');
        }
      }
    }, 1000);
  };

  const disconnect = () => {
    setStatus('ready');
    setConnectionData(null);
    setError(null);
    
    onAction?.({
      type: 'oauth_disconnect',
      agentId,
      data: {
        service,
        timestamp: new Date().toISOString()
      }
    });
  };

  const getStatusContent = () => {
    switch (status) {
      case 'ready':
        return (
          <div className="text-center space-y-4">
            <div className={`text-6xl ${config.color}`}>{config.icon}</div>
            <div>
              <h3 className="text-cyan-300 font-semibold mb-2 oxanium">
                Connect to {service}
              </h3>
              <p className="text-white text-sm techfont mb-4">
                {description}
              </p>
            </div>
          </div>
        );
        
      case 'connecting':
        return (
          <div className="text-center space-y-4">
            <div className="text-6xl animate-pulse">🔄</div>
            <div>
              <h3 className="text-cyan-300 font-semibold mb-2 oxanium">
                Connecting...
              </h3>
              <p className="text-white text-sm techfont">
                Please complete the authorization in the popup window
              </p>
            </div>
          </div>
        );
        
      case 'connected':
        return (
          <div className="text-center space-y-4">
            <div className="text-6xl text-green-400">✅</div>
            <div>
              <h3 className="text-green-300 font-semibold mb-2 oxanium">
                Connected to {service}
              </h3>
              <p className="text-white text-sm techfont mb-2">
                Successfully authorized with the following permissions:
              </p>
              {connectionData && (
                <div className="text-xs text-cyan-300 techfont">
                  Connected as: {connectionData.username || connectionData.email || 'User'}
                </div>
              )}
            </div>
          </div>
        );
        
      case 'error':
        return (
          <div className="text-center space-y-4">
            <div className="text-6xl text-red-400">❌</div>
            <div>
              <h3 className="text-red-300 font-semibold mb-2 oxanium">
                Connection Failed
              </h3>
              <p className="text-white text-sm techfont mb-2">
                {error || 'An error occurred during authorization'}
              </p>
            </div>
          </div>
        );
        
      default:
        return null;
    }
  };

  return (
    <div className="w-full max-w-md p-6 bg-black/60 backdrop-blur-lg border border-cyan-500/20 rounded-xl">
      {/* Header */}
      <div className="flex items-center mb-6">
        <div className="w-2 h-2 bg-cyan-400 rounded-full mr-3 animate-pulse"></div>
        <h3 className="text-cyan-300 font-semibold oxanium">
          🔗 OAuth Connection
        </h3>
      </div>

      {/* Status Content */}
      {getStatusContent()}

      {/* Scopes List */}
      {scopes.length > 0 && status !== 'connecting' && (
        <div className="mt-6 space-y-2">
          <h4 className="text-cyan-300 text-sm font-medium techfont">Requested Permissions:</h4>
          <ul className="space-y-1">
            {scopes.map((scope, index) => (
              <li key={index} className="text-white text-xs techfont flex items-center">
                <span className="w-1.5 h-1.5 bg-cyan-400 rounded-full mr-2"></span>
                {scope}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Action Buttons */}
      <div className="mt-6 space-y-3">
        {status === 'ready' && (
          <button
            onClick={initiateOAuth}
            className="w-full py-3 bg-gradient-to-r from-cyan-500/90 to-blue-500/90 hover:from-cyan-400/90 hover:to-blue-400/90 text-white font-bold rounded-lg techfont transition-all hover:shadow-[0_0_20px_rgba(0,209,255,0.5)]"
          >
            🔗 Connect to {service}
          </button>
        )}
        
        {status === 'connecting' && (
          <button
            onClick={() => {
              if (authWindow) authWindow.close();
              setStatus('ready');
            }}
            className="w-full py-3 bg-gray-600/80 hover:bg-gray-500/80 text-white font-bold rounded-lg techfont transition-all"
          >
            ❌ Cancel Connection
          </button>
        )}
        
        {status === 'connected' && (
          <button
            onClick={disconnect}
            className="w-full py-3 bg-red-600/80 hover:bg-red-500/80 text-white font-bold rounded-lg techfont transition-all"
          >
            🔌 Disconnect from {service}
          </button>
        )}
        
        {status === 'error' && (
          <button
            onClick={() => {
              setStatus('ready');
              setError(null);
            }}
            className="w-full py-3 bg-gradient-to-r from-cyan-500/90 to-blue-500/90 hover:from-cyan-400/90 hover:to-blue-400/90 text-white font-bold rounded-lg techfont transition-all"
          >
            🔄 Try Again
          </button>
        )}
      </div>
    </div>
  );
};

export default AgentOAuthFlow;
