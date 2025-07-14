// =============================================================================
// FRONTEND MESSAGE HANDLER FOR UNIFIED ROUTING
// Handles the async timing fix by processing unified messages
// =============================================================================

/**
 * Processes unified messages from the backend and routes them to appropriate components
 * All component rendering is handled dynamically via workflow resolution
 */

const UnifiedMessageHandler = {
  
  // =============================================================================
  // PROCESS UNIFIED MESSAGE FROM BACKEND
  // =============================================================================
  
  processUnifiedMessage: (unifiedMessage) => {
    console.log('Processing unified message:', unifiedMessage);
    
    // Route based on routingTarget using new component system
    if (unifiedMessage.routingTarget === 'inline_component' || unifiedMessage.routingTarget === 'chat_pane') {
      return UnifiedMessageHandler.handleInlineComponentMessage(unifiedMessage);
    } else if (unifiedMessage.routingTarget === 'artifact_component' || unifiedMessage.routingTarget === 'artifact_panel') {
      return UnifiedMessageHandler.handleArtifactComponentMessage(unifiedMessage);
    } else {
      console.warn('Unknown routing target:', unifiedMessage.routingTarget);
      return UnifiedMessageHandler.handleInlineComponentMessage(unifiedMessage); // fallback
    }
  },
  
  // =============================================================================
  // INLINE COMPONENT MESSAGE HANDLING
  // =============================================================================
  
  handleInlineComponentMessage: (message) => {
    if (message.hasComponent) {
      // Message with interactive inline component
      return {
        type: 'chat_message_with_inline_component',
        messageId: `msg_${Date.now()}`,
        sender: message.sender,
        content: message.content,
        timestamp: message.timestamp || new Date().toISOString(),
        inlineComponent: {
          id: message.component.id,
          name: message.component.name || message.component.type,
          data: message.component.data,
          needsWorkflowResolution: true
        }
      };
    } else {
      // Standard text message
      return {
        type: 'chat_message',
        messageId: `msg_${Date.now()}`,
        sender: message.sender,
        content: message.content,
        timestamp: message.timestamp || new Date().toISOString()
      };
    }
  },
  
  // =============================================================================
  // ARTIFACT COMPONENT MESSAGE HANDLING
  // =============================================================================
  
  handleArtifactComponentMessage: (message) => {
    return {
      type: 'artifact_component',
      artifactId: `artifact_${Date.now()}`,
      title: message.title,
      content: message.content,
      artifactType: message.artifactType,
      componentName: message.componentName || message.componentType,
      language: message.language,
      timestamp: message.timestamp || new Date().toISOString(),
      componentData: message.componentData || message.data,
      componentProps: {
        title: message.title,
        content: message.content,
        category: message.category,
        language: message.language,
        ...message.componentProps
      },
      needsWorkflowResolution: true
    };
  }
};

export default UnifiedMessageHandler;
