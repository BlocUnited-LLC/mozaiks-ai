// ==============================================================================
// FILE: ChatUI/src/workflows/Generator/components/index.js
// DESCRIPTION: Export Generator workflow-specific UI components
// ==============================================================================

// Import Generator-specific components
import AgentAPIKeyInput from './AgentAPIKeyInput';
import FileDownloadCenter from './FileDownloadCenter';
import ActionPlan from './ActionPlan';

/**
 * 🎯 GENERATOR WORKFLOW COMPONENTS
 * 
 * This module exports ONLY Generator workflow-specific UI components.
 * 
 * Components exported here:
 * - AgentAPIKeyInput: Handles API key requests for Generator workflow
 * - FileDownloadCenter: Handles file downloads for Generator workflow
 * - ActionPlan: Visualizes workflow steps and status
 */

const GeneratorComponents = {
  AgentAPIKeyInput,
  FileDownloadCenter,
  ActionPlan
};



export default GeneratorComponents;

// Named exports for convenience
export {
  AgentAPIKeyInput,
  FileDownloadCenter,
  ActionPlan
};
