// React hook for handling AG2 token streaming
// Enhanced streaming support for ChatGPT-like progressive text rendering

import { useState, useRef, useCallback } from 'react';

export const useStreamingText = () => {
    const [streamingMessages, setStreamingMessages] = useState(new Map());
    const streamingTimeouts = useRef(new Map());
    
    const handleStreamEvent = useCallback((event) => {
        const { type, data, agent_name } = event;
        
        switch (type) {
            case 'text_stream_start':
                // Initialize streaming message
                setStreamingMessages(prev => {
                    const newMap = new Map(prev);
                    newMap.set(data.stream_id, {
                        id: data.stream_id,
                        agent_name: agent_name || 'Agent',
                        content: '',
                        isStreaming: true,
                        timestamp: Date.now()
                    });
                    return newMap;
                });
                break;
                
            case 'text_stream_chunk':
                // Add chunk to streaming message with typing effect
                setStreamingMessages(prev => {
                    const newMap = new Map(prev);
                    const existing = newMap.get(data.stream_id);
                    if (existing) {
                        newMap.set(data.stream_id, {
                            ...existing,
                            content: existing.content + data.chunk,
                            timestamp: Date.now()
                        });
                    }
                    return newMap;
                });
                break;
                
            case 'text_stream_end':
                // Mark streaming as complete
                setStreamingMessages(prev => {
                    const newMap = new Map(prev);
                    const existing = newMap.get(data.stream_id);
                    if (existing) {
                        newMap.set(data.stream_id, {
                            ...existing,
                            isStreaming: false,
                            timestamp: Date.now()
                        });
                        
                        // Clean up after 5 seconds
                        setTimeout(() => {
                            setStreamingMessages(current => {
                                const updated = new Map(current);
                                updated.delete(data.stream_id);
                                return updated;
                            });
                        }, 5000);
                    }
                    return newMap;
                });
                break;
                
            // Legacy support for existing events
            case 'TEXT_MESSAGE_START':
                setStreamingMessages(prev => {
                    const newMap = new Map(prev);
                    newMap.set(data.messageId, {
                        id: data.messageId,
                        agent_name: agent_name || 'Agent',
                        content: '',
                        isStreaming: true,
                        timestamp: Date.now()
                    });
                    return newMap;
                });
                break;
                
            case 'TEXT_MESSAGE_CONTENT':
                setStreamingMessages(prev => {
                    const newMap = new Map(prev);
                    const existing = newMap.get(data.messageId);
                    if (existing) {
                        newMap.set(data.messageId, {
                            ...existing,
                            content: existing.content + (data.delta || data.content || ''),
                            timestamp: Date.now()
                        });
                    }
                    return newMap;
                });
                break;
                
            case 'TEXT_MESSAGE_END':
                setStreamingMessages(prev => {
                    const newMap = new Map(prev);
                    const existing = newMap.get(data.messageId);
                    if (existing) {
                        newMap.set(data.messageId, {
                            ...existing,
                            isStreaming: false,
                            timestamp: Date.now()
                        });
                        
                        // Clean up after 5 seconds
                        setTimeout(() => {
                            setStreamingMessages(current => {
                                const updated = new Map(current);
                                updated.delete(data.messageId);
                                return updated;
                            });
                        }, 5000);
                    }
                    return newMap;
                });
                break;
        }
    }, []);
    
    const clearAllStreams = useCallback(() => {
        setStreamingMessages(new Map());
        streamingTimeouts.current.forEach(timeout => clearTimeout(timeout));
        streamingTimeouts.current.clear();
    }, []);
    
    const getStreamingArray = useCallback(() => {
        return Array.from(streamingMessages.values());
    }, [streamingMessages]);
    
    return {
        streamingMessages,
        handleStreamEvent,
        clearAllStreams,
        getStreamingArray
    };
};
