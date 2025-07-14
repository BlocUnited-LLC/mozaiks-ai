import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { ChatUIProvider } from './context/ChatUIContext';
import ChatPage from './modules/Chat/pages/ChatPage';
import './styles/TransportAwareChat.css';

// Unified ChatUI App - Transport-agnostic chat with Simple Events integration
function App() {
  const handleChatUIReady = () => {
    console.log('ChatUI is ready!');
  };

  return (
    <ChatUIProvider onReady={handleChatUIReady}>
      <Router>
        <Routes>
          {/* Main chat page - supports all transport types and Simple Events protocol */}
          <Route path="/" element={<ChatPage />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/chat/:enterpriseId" element={<ChatPage />} />
          <Route path="/enterprise/:enterpriseId" element={<ChatPage />} />
          <Route path="/enterprise/:enterpriseId/:workflowType" element={<ChatPage />} />
          
          {/* Catch-all route redirects to main chat */}
          <Route path="*" element={<ChatPage />} />
        </Routes>
      </Router>
    </ChatUIProvider>
  );
}

export default App;
