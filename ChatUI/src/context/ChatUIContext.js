import React, { createContext, useContext, useEffect, useState } from 'react';
import services from '../services';
import config from '../config';
// Import workflow registry for UI tool registration
import { workflowsInitialized as workflowsInitPromise } from '../workflows';

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
  const [workflowsInitialized, setWorkflowsInitialized] = useState(false);

  useEffect(() => {
    const initializeServices = async () => {
      try {
        // Initialize workflow registry first (UI tools need to be registered)
        console.log('🔧 Initializing workflow registry...');
        await workflowsInitPromise;
        setWorkflowsInitialized(true);
        console.log('✅ Workflow registry initialized');

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

        // Initialize the workflow registry (includes agent system functionality)
        try {
          console.log('🚀 Agent system replaced by workflow registry...');
          
          // Wait for workflows to be properly initialized (workflowsInitPromise is a Promise)
          try {
            await workflowsInitPromise;
            console.log('✅ Workflows are initialized and ready');
          } catch (workflowError) {
            console.warn('⚠️ Workflows not yet initialized, proceeding with caution:', workflowError);
          }
          
          // Agent system functionality is now handled by workflow registration
          setAgentSystemInitialized(true);
          console.log('✅ Workflow-based agent system ready');
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
  }, [authAdapter, apiAdapter, onReady, workflowsInitPromise]);

  useEffect(() => {
    // Agents are auto-discovered through the workflow system
    if (agents.length > 0) {
      console.warn('Custom agent registration via props is not supported. Agents are defined in the agents.yaml file.');
    }
  }, [agents]);

  const contextValue = {
    // User state
    user,
    setUser,
    loading,
    initialized,

    // System state
    agentSystemInitialized,
    workflowsInitialized,

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
