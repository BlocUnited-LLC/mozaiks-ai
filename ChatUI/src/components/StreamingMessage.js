// StreamingMessage component for displaying progressive text
// Enhanced with ChatGPT-like animations and transitions

import React from 'react';

const StreamingMessage = ({ message, isStreaming }) => {
    return (
        <div className="flex flex-col gap-2 p-4 bg-gray-50 rounded-lg border transition-all duration-200">
            <div className="flex items-center gap-2">
                <div className="font-semibold text-blue-600">
                    {message.agent_name}
                </div>
                {isStreaming && (
                    <div className="flex items-center gap-1">
                        <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse"></div>
                        <span className="text-xs text-gray-500">typing...</span>
                    </div>
                )}
            </div>
            
            <div className="whitespace-pre-wrap text-gray-800">
                {message.content}
                {isStreaming && (
                    <span className="inline-block w-2 h-5 bg-gray-400 ml-1 animate-pulse">
                        |
                    </span>
                )}
            </div>
        </div>
    );
};

// Main chat container that combines regular and streaming messages
const ChatContainer = ({ messages, streamingMessages, className = "" }) => {
    // Combine regular messages with streaming messages
    const allMessages = [...messages];
    
    // Add streaming messages
    if (streamingMessages && streamingMessages.size > 0) {
        streamingMessages.forEach(streamMsg => {
            allMessages.push({
                id: streamMsg.id,
                content: streamMsg.content,
                agent_name: streamMsg.agent_name,
                isStreaming: streamMsg.isStreaming,
                timestamp: streamMsg.timestamp,
                type: 'streaming'
            });
        });
    }
    
    // Sort by timestamp to maintain order
    allMessages.sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0));
    
    return (
        <div className={`flex flex-col gap-4 max-h-96 overflow-y-auto p-4 ${className}`}>
            {allMessages.map((message, index) => (
                <StreamingMessage
                    key={message.id || index}
                    message={message}
                    isStreaming={message.isStreaming || false}
                />
            ))}
        </div>
    );
};

// Simplified streaming display for basic use cases
const StreamingDisplay = ({ streamingMessages }) => {
    if (!streamingMessages || streamingMessages.size === 0) {
        return null;
    }
    
    return (
        <div className="streaming-container">
            {Array.from(streamingMessages.values()).map(message => (
                <StreamingMessage
                    key={message.id}
                    message={message}
                    isStreaming={message.isStreaming}
                />
            ))}
        </div>
    );
};

export { StreamingMessage, ChatContainer, StreamingDisplay };
