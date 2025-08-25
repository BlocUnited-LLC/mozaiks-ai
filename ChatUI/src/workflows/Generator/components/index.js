// ==============================================================================
// FILE: ChatUI/src/workflows/Generator/components/index.js
// DESCRIPTION: Export Generator workflow-specific UI components
// ==============================================================================

// Import Generator-specific components
import AgentAPIKeyInput, { componentMetadata as apiKeyMetadata } from './AgentAPIKeyInput';
import FileDownloadCenter, { componentMetadata as downloadMetadata } from './FileDownloadCenter';

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

// Export component metadata for dynamic UI system
export const componentMetadata = {
  AgentAPIKeyInput: apiKeyMetadata,
  FileDownloadCenter: downloadMetadata
};

export default GeneratorComponents;

// Named exports for convenience
export {
  AgentAPIKeyInput,
  FileDownloadCenter
};
