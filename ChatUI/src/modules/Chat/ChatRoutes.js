import React from 'react';
import { Routes, Route } from 'react-router-dom';
import ChatPage from './pages/ChatPage';

const ChatRoutes = () => {
  return (
    <Routes>
      <Route path="/" element={<ChatPage />} />
      <Route path="/chat" element={<ChatPage />} />
      <Route path="/chat/:enterpriseId" element={<ChatPage />} />
    </Routes>
  );
};

export default ChatRoutes;
