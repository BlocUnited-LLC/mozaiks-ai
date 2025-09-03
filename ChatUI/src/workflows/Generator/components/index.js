// ==============================================================================
// FILE: ChatUI/src/workflows/Generator/components/index.js
// DESCRIPTION: Export Generator workflow-specific UI components
// ==============================================================================

// Import Generator-specific components
import AgentAPIKeyInput from './AgentAPIKeyInput';
import FileDownloadCenter from './FileDownloadCenter';

/**
 * 🎯 GENERATOR WORKFLOW COMPONENTS
 * 
 * This module exports ONLY Generator workflow-specific UI components.
 * 
 * Components exported here:
 * - AgentAPIKeyInput: Handles API key requests for Generator workflow
 * - FileDownloadCenter: Handles file downloads for Generator workflow
 */

const GeneratorComponents = {
  AgentAPIKeyInput,
  FileDownloadCenter
};



export default GeneratorComponents;

// Named exports for convenience
export {
  AgentAPIKeyInput,
  FileDownloadCenter
};
