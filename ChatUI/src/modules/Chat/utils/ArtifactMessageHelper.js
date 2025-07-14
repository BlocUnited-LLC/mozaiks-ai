/**
 * Backend integration helper for creating artifact-enabled chat messages
 */

/**
 * Create a chat message with embedded artifacts
 * @param {string} baseMessage - The base message text
 * @param {Array} artifacts - Array of artifact configurations
 * @returns {Object} - Chat message with artifact data
 */
export const createArtifactMessage = (baseMessage, artifacts = []) => {
  let messageContent = baseMessage;
  const artifactData = {};

  // Add artifact markers to message and prepare artifact data
  artifacts.forEach(artifact => {
    const marker = `[ARTIFACT:${artifact.type}]`;
    messageContent += ` ${marker}`;
    artifactData[artifact.type] = artifact.data;
  });

  return {
    content: messageContent,
    artifactData: artifactData,
    sender: "assistant"
  };
};

/**
 * Create file browser artifact message
 * @param {string} message - Base message
 * @param {Object} fileData - File browser data
 * @returns {Object} - Artifact message
 */
export const createFileBrowserMessage = (message, fileData) => {
  return createArtifactMessage(message, [{
    type: 'file_browser',
    data: fileData
  }]);
};

/**
 * Create download center artifact message
 * @param {string} message - Base message
 * @param {Object} downloadData - Download center data
 * @returns {Object} - Artifact message
 */
export const createDownloadMessage = (message, downloadData) => {
  return createArtifactMessage(message, [{
    type: 'download_center',
    data: downloadData
  }]);
};

/**
 * Create upload center artifact message
 * @param {string} message - Base message
 * @param {Object} uploadData - Upload center data
 * @returns {Object} - Artifact message
 */
export const createUploadMessage = (message, uploadData) => {
  return createArtifactMessage(message, [{
    type: 'upload_center',
    data: uploadData
  }]);
};

/**
 * Create workflow viewer artifact message
 * @param {string} message - Base message
 * @param {Object} workflowData - Workflow viewer data
 * @returns {Object} - Artifact message
 */
export const createWorkflowViewerMessage = (message, workflowData) => {
  return createArtifactMessage(message, [{
    type: 'workflow_viewer',
    data: workflowData
  }]);
};

/**
 * Create multi-artifact message
 * @param {string} message - Base message
 * @param {Array} artifactConfigs - Array of artifact configurations
 * @returns {Object} - Multi-artifact message
 */
export const createMultiArtifactMessage = (message, artifactConfigs) => {
  return createArtifactMessage(message, artifactConfigs);
};

/**
 * Convert workflow export result to artifact message
 * @param {Object} exportResult - Result from file_manager_plugin export
 * @returns {Object} - Artifact message
 */
export const convertWorkflowExportToArtifact = (exportResult) => {
  if (!exportResult.success) {
    return {
      content: `Export failed: ${exportResult.error}`,
      sender: "assistant"
    };
  }

  const workflowName = exportResult.workflow_name || "GeneratedWorkflow";
  const workflowDir = exportResult.workflow_dir || `workflows/${workflowName}`;

  // Create multiple artifacts for comprehensive workflow management
  const artifacts = [
    {
      type: 'workflow_viewer',
      data: {
        workflowName: workflowName,
        workflowDir: workflowDir,
        totalFiles: exportResult.export_result?.total_files || 0,
        workflowFiles: exportResult.export_result?.files_by_category || {},
        workflowStructure: exportResult.export_result?.workflow_structure || {}
      }
    },
    {
      type: 'file_browser',
      data: {
        workflowDir: workflowDir,
        files: exportResult.export_result?.all_files || [],
        totalFiles: exportResult.export_result?.total_files || 0
      }
    },
    {
      type: 'download_center',
      data: {
        workflowName: workflowName,
        files: exportResult.export_result?.all_files || [],
        totalFiles: exportResult.export_result?.total_files || 0,
        totalSize: exportResult.export_result?.total_size || 0,
        readyForDownload: true
      }
    }
  ];

  return createArtifactMessage(
    `Successfully generated workflow "${workflowName}"! You can now:`,
    artifacts
  );
};

/**
 * Example usage for backend integration
 */
export const exampleUsage = {
  // Basic artifact message
  fileManager: createFileBrowserMessage(
    "Your workflow files are ready for review:",
    {
      workflowDir: "workflows/MyWorkflow",
      files: [
        { name: "agent1.yaml", size: 1024, type: ".yaml" },
        { name: "config.yaml", size: 512, type: ".yaml" }
      ],
      totalFiles: 2
    }
  ),

  // Multi-artifact message
  workflowComplete: createMultiArtifactMessage(
    "Workflow generation complete!",
    [
      {
        type: 'workflow_viewer',
        data: { workflowName: "MyWorkflow", totalFiles: 5 }
      },
      {
        type: 'download_center',
        data: { workflowName: "MyWorkflow", readyForDownload: true }
      }
    ]
  )
};

export default {
  createArtifactMessage,
  createFileBrowserMessage,
  createDownloadMessage,
  createUploadMessage,
  createWorkflowViewerMessage,
  createMultiArtifactMessage,
  convertWorkflowExportToArtifact,
  exampleUsage
};
