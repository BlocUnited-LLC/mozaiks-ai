import React from 'react';
import { BrowserRouter as Router, Routes, Route, useLocation } from 'react-router-dom';
import { ChatUIProvider, useChatUI } from './context/ChatUIContext';
import ChatPage from './pages/ChatPage';
import MyWorkflowsPage from './pages/MyWorkflowsPage';
import './styles/TransportAwareChat.css';

/**
 * AppContent - Inner component that has access to context and location
 */
const NullRoute = () => null;

const AppContent = () => {
  const location = useLocation();
  const { 
    layoutMode,
    setLayoutMode,
    previousLayoutMode,
    setPreviousLayoutMode,
    isInDiscoveryMode,
    setIsInDiscoveryMode
  } = useChatUI();

  const isOnWorkflowsPage = location.pathname === '/workflows' || location.pathname === '/my-workflows';

  React.useEffect(() => {
    if (isOnWorkflowsPage && !isInDiscoveryMode) {
      setPreviousLayoutMode(layoutMode);
      setIsInDiscoveryMode(true);
    } else if (!isOnWorkflowsPage && isInDiscoveryMode) {
      setIsInDiscoveryMode(false);
      setLayoutMode(previousLayoutMode || 'full');
    }
  }, [isOnWorkflowsPage, isInDiscoveryMode, layoutMode, previousLayoutMode, setIsInDiscoveryMode, setLayoutMode, setPreviousLayoutMode]);

  return (
    <>
      <ChatPage />
      <Routes>
        <Route path="/" element={<NullRoute />} />
        <Route path="/workflows" element={<MyWorkflowsPage />} />
        <Route path="/my-workflows" element={<MyWorkflowsPage />} />
        <Route path="*" element={<NullRoute />} />
      </Routes>
    </>
  );
};

// Unified ChatUI App - Transport-agnostic chat with Simple Events integration
function App() {
  const handleChatUIReady = () => {
    console.log('ChatUI is ready!');
  };

  return (
    <ChatUIProvider onReady={handleChatUIReady}>
      <Router future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <AppContent />
      </Router>
    </ChatUIProvider>
  );
}

export default App;
