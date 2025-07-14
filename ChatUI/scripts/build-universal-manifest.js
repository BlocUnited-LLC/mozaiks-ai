#!/usr/bin/env node

// Simple Plugin Discovery
const fs = require('fs');
const path = require('path');

const MANIFEST_FILE = path.join(__dirname, '../src/plugins.json');

function scanPlugins() {
  const components = scanDir(path.join(__dirname, '../src/agents/components'));
  const agents = scanDir(path.join(__dirname, '../src/agents/instances'));
  const pages = scanDir(path.join(__dirname, '../src/modules/Chat/pages'));
  
  const manifest = {
    components: components.map(f => f.replace('.js', '')),
    agents: agents.map(f => f.replace('.js', '')),
    pages: pages.map(f => f.replace('.js', '')),
    generated: new Date().toISOString()
  };
  
  fs.writeFileSync(MANIFEST_FILE, JSON.stringify(manifest, null, 2));
  console.log(`✅ Found ${components.length + agents.length + pages.length} plugins`);
  
  return manifest;
}

function scanDir(dir) {
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir)
    .filter(f => f.endsWith('.js') && f !== 'index.js');
}

if (require.main === module) {
  scanPlugins();
}
