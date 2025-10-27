// ==============================================================================
// FILE: ChatUI/src/workflows/Generator/components/index.js
// DESCRIPTION: Export Generator workflow-specific UI components
// ==============================================================================

// Import Generator-specific components
import AgentAPIKeysBundleInput from './AgentAPIKeysBundleInput';
import FileDownloadCenter from './FileDownloadCenter';
import ActionPlan from './ActionPlan';
import MermaidSequenceDiagram from './MermaidSequenceDiagram';

/**
 * 🎯 GENERATOR WORKFLOW COMPONENTS
 * 
 * This module exports ONLY Generator workflow-specific UI components.
 * 
 * Components exported here:
 * - AgentAPIKeysBundleInput: Handles consolidated API key requests for multiple services
 * - FileDownloadCenter: Handles file downloads for Generator workflow
 * - ActionPlan: Visualizes workflow steps and status
 * - MermaidSequenceDiagram: Presents the post-approval sequence diagram artifact
 */

const GeneratorComponents = {
  AgentAPIKeysBundleInput,
  FileDownloadCenter,
  ActionPlan,
  MermaidSequenceDiagram
};

export default GeneratorComponents;

// Named exports for convenience
export {
  AgentAPIKeysBundleInput,
  FileDownloadCenter,
  ActionPlan,
  MermaidSequenceDiagram
};
