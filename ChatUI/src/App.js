import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { ChatUIProvider } from './context/ChatUIContext';
import ChatPage from './pages/ChatPage';
import MyWorkflowsPage from './pages/MyWorkflowsPage';
import './styles/TransportAwareChat.css';

/**
 * AppContent - Inner component that has access to context and location
 */
const NullRoute = () => null;

const AppContent = () => {
  // Widget mode is now managed by individual pages via useWidgetMode() hook
  // and by ChatPage when processing returns from widget mode.
  // No need for App.js to manage it centrally.

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
