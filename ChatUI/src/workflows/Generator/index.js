// ==============================================================================
// FILE: ChatUI/src/workflows/generator/index.js
// DESCRIPTION: Generator workflow component registration
// ==============================================================================

import { registerUiTool } from '../../core/uiToolRegistry';
import FileDownloadCenter from './components/FileDownloadCenter';
import AgentAPIKeyInput from './components/AgentAPIKeyInput';

/**
 * Generator Workflow Registration
 * 
 * Registers all UI tools/components for the Generator workflow.
 * This follows the workflow-agnostic pattern where each workflow
 * registers its own components with the central registry.
 */

// Component metadata for better debugging and management
const WORKFLOW_NAME = 'generator';
const WORKFLOW_VERSION = '1.0.0';

const componentMetadata = {
  workflow: WORKFLOW_NAME,
  version: WORKFLOW_VERSION,
  registeredAt: new Date().toISOString()
};

// Register Generator workflow components
console.log(`🚀 Registering ${WORKFLOW_NAME} workflow components...`);

// File Download Tool
registerUiTool(
  'file_download', 
  FileDownloadCenter, 
  {
    ...componentMetadata,
    description: 'UI component for downloading generated files',
    category: 'artifact',
    supports: ['single_download', 'bulk_download', 'download_status']
  }
);

// API Key Input Tool  
registerUiTool(
  'agent_api_key_input',
  AgentAPIKeyInput,
  {
    ...componentMetadata,
    description: 'UI component for secure API key collection',
    category: 'inline',
    supports: ['masked_input', 'service_specific', 'validation']
  }
);

console.log(`✅ ${WORKFLOW_NAME} workflow components registered successfully`);

// Export workflow info for introspection
export const workflowInfo = {
  name: WORKFLOW_NAME,
  version: WORKFLOW_VERSION,
  components: [
    {
      toolId: 'file_download',
      component: 'FileDownloadCenter',
      category: 'artifact'
    },
    {
      toolId: 'api_key_input', 
      component: 'AgentAPIKeyInput',
      category: 'inline'
    }
  ],
  registeredAt: new Date().toISOString()
};

// Export components for direct import if needed
export {
  FileDownloadCenter,
  AgentAPIKeyInput
};

export default workflowInfo;
