// Auto-discovery and manifest generation
export class ComponentManifestGenerator {
  
  async discoverAndGenerateManifest(workflowName) {
    const workflowPath = `workflows/${workflowName}/Components`;
    
    // Scan for actual component files
    const artifactFiles = await this.scanDirectory(`${workflowPath}/Artifacts`);
    const inlineFiles = await this.scanDirectory(`${workflowPath}/Inline`);
    
    // Generate manifest based on discovered files
    const manifest = {
      version: "1.0.0",
      lastUpdated: new Date().toISOString(),
      workflow: workflowName,
      artifacts: {
        manifestPath: "./Artifacts/components.json",
        components: artifactFiles.map(f => f.replace('.js', ''))
      },
      inline: {
        manifestPath: "./Inline/components.json",
        components: inlineFiles.map(f => f.replace('.js', ''))
      }
    };
    
    // Auto-generate individual manifests
    await this.generateArtifactsManifest(workflowName, artifactFiles);
    await this.generateInlineManifest(workflowName, inlineFiles);
    
    return manifest;
  }
  
  async generateArtifactsManifest(workflowName, files) {
    const components = {};
    
    for (const file of files) {
      const componentName = file.replace('.js', '');
      components[componentName] = {
        file: file,
        category: "auto_generated",
        description: `Auto-generated artifact component for ${workflowName}`
      };
    }
    
    const manifest = {
      version: "1.0.0",
      lastUpdated: new Date().toISOString(),
      workflow: workflowName,
      components
    };
    
    // Write to filesystem
    await this.writeManifest(`workflows/${workflowName}/Components/Artifacts/components.json`, manifest);
  }
}
