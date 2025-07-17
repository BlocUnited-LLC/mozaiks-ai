import React, { createContext, useContext, useEffect, useState } from 'react';
import services from '../services';
import config from '../config';
import { initializeAgentSystem } from '../agents';

const ChatUIContext = createContext(null);

export const useChatUI = () => {
  const context = useContext(ChatUIContext);
  if (!context) {
    throw new Error('useChatUI must be used within a ChatUIProvider');
  }
  return context;
};

export const ChatUIProvider = ({ 
  children,
  authAdapter = null,
  apiAdapter = null,
  onReady = () => {},
  agents = []
}) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [initialized, setInitialized] = useState(false);
  const [authAdapterInstance, setAuthAdapterInstance] = useState(null);
  const [apiAdapterInstance, setApiAdapterInstance] = useState(null);
  const [agentSystemInitialized, setAgentSystemInitialized] = useState(false);

  useEffect(() => {
    const initializeServices = async () => {
      try {
        // Initialize services with custom adapters
        services.initialize({ authAdapter, apiAdapter });

        // Get the adapter instances
        const authAdapterInst = services.getAuthAdapter();
        const apiAdapterInst = services.getApiAdapter();
        
        setAuthAdapterInstance(authAdapterInst);
        setApiAdapterInstance(apiAdapterInst);

        // Get initial user
        const currentUser = await authAdapterInst?.getCurrentUser();
        setUser(currentUser);

        // Listen for auth state changes
        if (authAdapterInst?.onAuthStateChange) {
          authAdapterInst.onAuthStateChange((newUser) => {
            setUser(newUser);
          });
        }

        // Initialize the agent system
        try {
          console.log('🚀 Initializing agent system...');
          await initializeAgentSystem();
          setAgentSystemInitialized(true);
          console.log('✅ Agent system initialized');
        } catch (error) {
          console.error('❌ Failed to initialize agent system:', error);
          // Continue loading even if agent system fails
        }

        setInitialized(true);
        setLoading(false);
        onReady();

      } catch (error) {
        console.error('Failed to initialize ChatUI:', error);
        setLoading(false);
      }
    };

    initializeServices();
  }, [authAdapter, apiAdapter, onReady]);

  useEffect(() => {
    // Agents are auto-discovered through the workflow system
    if (agents.length > 0) {
      console.warn('Custom agent registration via props is not supported. Agents are defined in workflow.json files.');
    }
  }, [agents]);

  const contextValue = {
    // User state
    user,
    setUser,
    loading,
    initialized,

    // Agent system state
    agentSystemInitialized,

    // Configuration
    config: config.getConfig(),

    // Services (use state instances to avoid initialization errors)
    auth: authAdapterInstance,
    api: apiAdapterInstance,

    // Actions
    logout: async () => {
      if (authAdapterInstance) {
        await authAdapterInstance.logout();
        setUser(null);
      }
    },
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gradient-to-br from-gray-900 to-blue-900">
        <div className="text-white text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-white mx-auto mb-4"></div>
          <p className="techfont">Initializing ChatUI...</p>
        </div>
      </div>
    );
  }

  return (
    <ChatUIContext.Provider value={contextValue}>
      {children}
    </ChatUIContext.Provider>
  );
};
