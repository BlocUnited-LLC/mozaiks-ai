// ============================================================================
// FILE: ChatUI/src/workflows/Generator/components/ActionPlan.js
// REWRITE: Accordion-based Action Plan artifact (schema: { workflow:{...}, agent_message })
// PURPOSE: Present hierarchical workflow (phases -> agents -> tools) with robust, defensive parsing.
// ============================================================================

import React, { useState, useEffect, useRef } from 'react';
import { ChevronDown, ChevronRight, Layers, Plug, UserCheck, Bot, Sparkles, Zap, Activity, GitBranch, Clock, Settings, Database, MousePointerClick, Compass, MessageSquare } from 'lucide-react';
import { createToolsLogger } from '../../../core/toolsLogger';
// Use centralized design system tokens (incremental migration)
import { typography, components, colors } from '../../../styles/artifactDesignSystem';

// Semantic model field mappings (3 orthogonal dimensions)
const INITIATED_BY = {
  user: { label: 'User', desc: 'Human explicitly starts workflow', color: 'cyan' },
  system: { label: 'System', desc: 'Platform automatically starts workflow', color: 'violet' },
  external_event: { label: 'External Event', desc: 'External service triggers workflow', color: 'amber' },
};

const TRIGGER_TYPE = {
  form_submit: { label: 'Form Submit', desc: 'User submits web form', color: 'emerald' },
  chat_start: { label: 'Chat-Based', desc: 'User initiates conversation', color: 'cyan' },
  chatstart: { label: 'Chat-Based', desc: 'User initiates conversation', color: 'cyan' },
  cron_schedule: { label: 'Scheduled', desc: 'Time-based trigger', color: 'violet' },
  webhook: { label: 'Webhook', desc: 'External HTTP POST', color: 'amber' },
  database_condition: { label: 'Database', desc: 'Database state trigger', color: 'blue' },
};

const PATTERN_META = {
  pipeline: { label: 'Pipeline', desc: 'Sequential handoffs across phases', color: 'violet' },
  hierarchical: { label: 'Hierarchical', desc: 'Lead agent delegates work to specialists', color: 'cyan' },
  star: { label: 'Star', desc: 'Central coordinator distributes and gathers work', color: 'emerald' },
  redundant: { label: 'Redundant', desc: 'Parallel agents produce overlapping outputs', color: 'amber' },
  feedbackloop: { label: 'Feedback Loop', desc: 'Iterative refinement until acceptance', color: 'blue' },
  escalation: { label: 'Escalation', desc: 'Progressively engages higher-tier experts', color: 'violet' },
  contextawarerouting: { label: 'Context-Aware Routing', desc: 'Dynamically routes tasks based on context variables', color: 'cyan' },
  organic: { label: 'Organic', desc: 'Free-form collaboration among agents', color: 'emerald' },
  triagewithtasks: { label: 'Triage with Tasks', desc: 'Intake triage followed by targeted execution tasks', color: 'amber' },
};

const LIFECYCLE_TRIGGER_META = {
  before_chat: { label: 'Before Chat', desc: 'Runs before the first agent turn', color: 'violet' },
  after_chat: { label: 'After Chat', desc: 'Runs after the workflow concludes', color: 'violet' },
  before_agent: { label: 'Before Agent', desc: 'Runs immediately before the target agent starts', color: 'cyan' },
  after_agent: { label: 'After Agent', desc: 'Runs immediately after the target agent finishes', color: 'emerald' },
};

const toTitle = (text) => text.replace(/_/g, ' ').replace(/\b\w/g, char => char.toUpperCase());

const SemanticChip = ({ value, mapping, icon: Icon = Sparkles, prefix }) => {
  const raw = String(value || '').trim();
  const normalized = raw.toLowerCase();
  const canonical = normalized.replace(/[^a-z0-9]/g, '');
  const meta = mapping[normalized] || mapping[canonical] || {
    label: raw ? toTitle(raw) : 'Unknown',
    desc: raw ? toTitle(raw) : 'Not specified',
    color: 'neutral',
  };
  const badgeClasses = {
    cyan: components.badge.primary,
    emerald: components.badge.success,
    violet: components.badge.secondary,
    amber: components.badge.warning,
    blue: components.badge.info || components.badge.primary,
    neutral: components.badge.neutral,
  };

  return (
    <span className={`${badgeClasses[meta.color] || components.badge.neutral}`} title={meta.desc}>
      <Icon className="h-3.5 w-3.5" /> {prefix}: {meta.label}
    </span>
  );
};

const ToolPill = ({ tool, idx, type = 'integration' }) => {
  const rawName = typeof tool === 'string' ? tool : tool?.name;
  const rawPurpose = typeof tool === 'string' ? null : tool?.purpose;
  const name = String(rawName || `Tool ${idx + 1}`);
  const purpose = rawPurpose && String(rawPurpose).trim() ? String(rawPurpose).trim() : null;
  const integration = tool && typeof tool === 'object' && typeof tool.integration === 'string'
    ? tool.integration
    : null;
  const trigger = tool && typeof tool === 'object' && typeof tool.trigger === 'string'
    ? tool.trigger
    : null;

  // Different colors for operations vs integrations
  const colorScheme = type === 'operation' 
    ? {
        border: 'border-[rgba(var(--color-primary-rgb),0.5)]',
        borderHover: 'hover:border-[var(--color-primary-light)]',
        bg: 'bg-[rgba(var(--color-primary-rgb),0.2)]',
        ring: 'ring-[rgba(var(--color-primary-light-rgb),0.5)]',
        iconColor: 'text-[var(--color-primary-light)]'
      }
    : {
        border: 'border-[rgba(var(--color-secondary-rgb),0.5)]',
        borderHover: 'hover:border-[var(--color-secondary-light)]',
        bg: 'bg-[rgba(var(--color-secondary-rgb),0.2)]',
        ring: 'ring-[rgba(var(--color-secondary-light-rgb),0.5)]',
        iconColor: 'text-[var(--color-secondary-light)]'
      };

  return (
    <div className={`group relative overflow-hidden rounded-lg border-2 ${colorScheme.border} bg-slate-800 p-4 transition-all ${colorScheme.borderHover} hover:bg-slate-750 hover:shadow-xl hover:[box-shadow:0_0_0_rgba(var(--color-secondary-rgb),0.2)]`}>
      <div className="flex items-start gap-3">
        <div className={`rounded-lg ${colorScheme.bg} p-2.5 ring-2 ${colorScheme.ring}`}>
          <Plug className={`h-5 w-5 ${colorScheme.iconColor}`} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-bold text-white text-sm">{name}</p>
          {purpose && <p className="mt-1.5 text-xs text-slate-300">{purpose}</p>}
          {type === 'integration' && integration && (
            <p className="mt-1 text-[0.65rem] uppercase tracking-wider text-slate-400">
              Integration: <span className="text-slate-200">{integration}</span>
            </p>
          )}
          {type === 'operation' && trigger && (
            <p className="mt-1 text-[0.65rem] uppercase tracking-wider text-slate-400">
              Trigger: <span className="text-slate-200">{trigger}</span>
            </p>
          )}
        </div>
      </div>
    </div>
  );
};

const ToolSection = ({ title, icon: Icon = Zap, items, type = 'integration' }) => {
  if (!Array.isArray(items) || items.length === 0) return null;

  // Different colors for section headers
  const headerColor = type === 'operation' 
    ? 'text-[var(--color-primary-light)]' 
    : 'text-[var(--color-secondary-light)]';

  return (
    <div className="space-y-3">
      <div className={`flex items-center gap-2 text-xs font-black uppercase tracking-wider ${headerColor}`}>
        <Icon className="h-4 w-4" />
        {title}
      </div>
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        {items.map((tool, tIdx) => {
          const key = typeof tool === 'string'
            ? `${title}-${tool}-${tIdx}`
            : `${title}-${tool?.name || tIdx}-${tIdx}`;
          return <ToolPill key={key} tool={tool} idx={tIdx} type={type} />;
        })}
      </div>
    </div>
  );
};

const ComponentCard = ({ component, idx }) => {
  if (!component || typeof component !== 'object') return null;
  const label = String(component?.label || component?.tool || `component ${idx + 1}`);
  const phaseName = String(component?.phase_name || 'Phase');
  const agentName = String(component?.agent || 'Agent');
  const toolName = String(component?.tool || '').trim();
  const componentName = String(component?.component || '').trim();
  const display = String(component?.display || 'inline').trim();
  const interactionPattern = String(component?.interaction_pattern || 'single_step').trim();
  const summary = component?.summary ? String(component.summary) : '';

  // Color code by display type
  const isInline = display === 'inline';
  const borderColor = isInline ? 'border-blue-500/40' : 'border-purple-500/40';
  const bgColor = isInline ? 'bg-blue-500/5' : 'bg-purple-500/5';
  const iconBg = isInline ? 'bg-blue-500/20' : 'bg-purple-500/20';
  const iconRing = isInline ? 'ring-blue-400/40' : 'ring-purple-400/40';
  const iconColor = isInline ? 'text-blue-400' : 'text-purple-400';

  return (
    <div className={`rounded-xl border-2 ${borderColor} ${bgColor} p-4`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <div className={`rounded-lg ${iconBg} p-2 ring-2 ${iconRing}`}>
            <MousePointerClick className={`h-4 w-4 ${iconColor}`} />
          </div>
          <span className="font-bold text-white">{label}</span>
        </div>
        <span className="rounded-full bg-slate-700 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-slate-200">
          {interactionPattern.replace(/_/g, ' ')}
        </span>
      </div>
      <div className="mt-3 space-y-1 text-xs text-slate-300">
        <div>
          <span className="font-semibold text-white">Phase:</span> {phaseName}
        </div>
        <div>
          <span className="font-semibold text-white">Agent:</span> {agentName}
        </div>
        {toolName && (
          <div>
            <span className="font-semibold text-white">Tool:</span> {toolName}
          </div>
        )}
        {componentName && (
          <div>
            <span className="font-semibold text-white">Component:</span> {componentName}
          </div>
        )}
      </div>
      {summary && (
        <p className="mt-3 text-sm leading-relaxed text-slate-200">{summary}</p>
      )}
    </div>
  );
};

const normalizeStringList = (value) => (
  Array.isArray(value)
    ? value
        .filter((item) => typeof item === 'string' && item.trim().length > 0)
        .map((item) => item.trim())
    : []
);

const mapToolStrings = (items, purpose) =>
  items.map((name) => ({ name, purpose }));

const normalizeLifecycleOperations = (value) => {
  const items = [];
  if (Array.isArray(value)) {
    items.push(...value);
  } else if (value && typeof value === 'object') {
    items.push(value);
  }

  return items
    .filter((item) => item && typeof item === 'object')
    .map((item, idx) => {
      const triggerCandidate = item.trigger ?? item.trigger_type ?? item.lifecycle_trigger;
      const trigger = String(triggerCandidate || '').trim().toLowerCase();
      const targetCandidate =
        item.target ?? item.agent ?? item.agent_name ?? item.source_agent ?? null;
      const descriptionSource =
        item.description ?? item.purpose ?? item.summary ?? '';

      return {
        name: String(item.name || `Lifecycle ${idx + 1}`),
        trigger,
        target:
          targetCandidate === undefined || targetCandidate === null || String(targetCandidate).trim() === ''
            ? null
            : String(targetCandidate).trim(),
        description:
          descriptionSource !== undefined && descriptionSource !== null
            ? String(descriptionSource)
            : '',
      };
    })
    .filter((op) => op.trigger);
};

const mergeLifecycleCollections = (...collections) => {
  const merged = [];
  const seen = new Set();

  collections.forEach((collection) => {
    if (!Array.isArray(collection)) return;
    collection.forEach((op) => {
      if (!op || typeof op !== 'object') return;
      const trigger = String(op.trigger || '').toLowerCase();
      const target = op.target ? String(op.target).toLowerCase() : '';
      const name = String(op.name || '').toLowerCase();
      const key = `${trigger}::${target}::${name}`;
      if (seen.has(key)) return;
      seen.add(key);
      merged.push(op);
    });
  });

  return merged;
};

// Lifecycle operation card component (reusable)
const LifecycleCard = ({ operation, idx, compact = false }) => {
  const triggerKey = String(operation.trigger || '').toLowerCase();

  return (
    <div className={`rounded-xl border-2 border-[rgba(var(--color-accent-rgb),0.5)] bg-gradient-to-br from-slate-800/80 to-slate-900/80 ${compact ? 'p-3' : 'p-4'}`}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <div className="rounded-lg bg-[rgba(var(--color-accent-rgb),0.2)] p-2 ring-2 ring-[rgba(var(--color-accent-light-rgb),0.5)]">
            <Activity className="h-4 w-4 text-[var(--color-accent-light)]" />
          </div>
          <span className={`${compact ? 'text-sm' : 'text-base'} font-bold text-white`}>
            {operation.name || `Lifecycle ${idx + 1}`}
          </span>
        </div>
        <SemanticChip
          value={triggerKey}
          mapping={LIFECYCLE_TRIGGER_META}
          prefix=""
          icon={Clock}
        />
      </div>
      {operation.target && (
        <div className="mt-2 text-xs text-slate-300">
          Target Agent: <span className="font-semibold text-white">{operation.target}</span>
        </div>
      )}
      {operation.description && !compact && (
        <p className="mt-2 text-sm leading-relaxed text-slate-200 whitespace-pre-line">
          {operation.description}
        </p>
      )}
    </div>
  );
};

// Workflow-level lifecycle section (before_chat / after_chat)
const WorkflowLifecycleSection = ({ operations, type }) => {
  if (!Array.isArray(operations) || operations.length === 0) return null;

  const isSetup = type === 'before_chat';
  const title = isSetup ? 'Pre-Workflow Setup' : 'Post-Workflow Cleanup';
  const subtitle = isSetup
    ? 'Operations executed before the first agent runs'
    : 'Operations executed after all agents complete';

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 rounded-lg bg-slate-800 px-6 py-4 border-l-4 border-[var(--color-accent-light)]">
        <Activity className="h-6 w-6 text-[var(--color-accent-light)]" />
        <span className="text-xl font-black uppercase tracking-wider text-white">{title}</span>
      </div>
      <div className="rounded-2xl border-2 border-[rgba(var(--color-accent-rgb),0.5)] bg-slate-900/60 p-6">
        <p className="mb-4 text-sm text-slate-400">{subtitle}</p>
        <div className="grid gap-3">
          {operations.map((op, idx) => (
            <LifecycleCard key={`${type}-${idx}`} operation={op} idx={idx} />
          ))}
        </div>
      </div>
    </div>
  );
};

// Minimal inference helper: derive trigger_type from a raw trigger string when missing.
const inferTriggerTypeFrom = (trigger) => {
  if (!trigger || typeof trigger !== 'string') return undefined;
  const s = trigger.toLowerCase();
  if (s.includes('webhook')) return 'webhook';
  if (s.includes('cron') || s.includes('schedule')) return 'cron_schedule';
  if (s.includes('form') || s.includes('submit')) return 'form_submit';
  if (s.includes('chat') || s.includes('conversation') || s.includes('user_initiated')) return 'chat_start';
  if (s.includes('db') || s.includes('database')) return 'database_condition';
  return undefined;
};

const AgentAccordionRow = ({ agent, index, isOpen, onToggle, agentLifecycleHooks = [] }) => {
  const agentName = String(agent?.agent_name || agent?.name || `Agent ${index + 1}`);
  const rawAgentTools = Array.isArray(agent?.agent_tools) ? agent.agent_tools : [];

  let integrationTools = [];
  let operationTools = [];

  if (rawAgentTools.length > 0) {
    integrationTools = [];
    operationTools = [];
    rawAgentTools.forEach((tool, tIdx) => {
      if (!tool || typeof tool !== 'object') return;
      const toolName = String(tool?.name || `Tool ${tIdx + 1}`);
      const purpose = tool?.purpose ? String(tool.purpose) : '';
      const integration = typeof tool?.integration === 'string' && tool.integration.trim().length
        ? tool.integration.trim()
        : null;
      const entry = {
        name: toolName,
        purpose,
        integration,
      };
      if (integration) {
        integrationTools.push(entry);
      } else {
        operationTools.push(entry);
      }
    });
  } else {
    const integrationNames = normalizeStringList(agent?.integrations);
    const operationNames = normalizeStringList(agent?.operations);
    integrationTools = integrationNames.map(name => ({ name, purpose: '', integration: name }));
    operationTools = mapToolStrings(operationNames, '');
  }

  const displayedToolCount = integrationTools.length + operationTools.length;
  const hasTools = displayedToolCount > 0;

  const lifecycleTools = Array.isArray(agent?.lifecycle_tools) ? agent.lifecycle_tools : [];
  const agentLifecycleTools = lifecycleTools
    .filter(tool => tool && typeof tool === 'object')
    .map((tool, tIdx) => ({
      name: String(tool?.name || `Lifecycle ${tIdx + 1}`),
      trigger: String(tool?.trigger || ''),
      target: agentName,
      description: tool?.purpose ? String(tool.purpose) : '',
      integration: typeof tool?.integration === 'string' && tool.integration.trim().length
        ? tool.integration.trim()
        : null,
    }));

  const combinedLifecycleHooks = [
    ...agentLifecycleHooks,
    ...agentLifecycleTools,
  ];
  const hasLifecycleHooks = combinedLifecycleHooks.length > 0;

  const systemHooks = Array.isArray(agent?.system_hooks)
    ? agent.system_hooks
        .filter(hook => hook && typeof hook === 'object')
        .map((hook, hIdx) => ({
          name: String(hook?.name || `Hook ${hIdx + 1}`),
          purpose: hook?.purpose ? String(hook.purpose) : '',
        }))
    : [];
  const hasSystemHooks = systemHooks.length > 0;

  // Determine interaction type from human_interaction field
  const humanInteraction = String(agent?.human_interaction || 'none').toLowerCase();
  const interactionType = ['none', 'context', 'approval'].includes(humanInteraction) 
    ? humanInteraction 
    : 'none';
  
  // Visual config per interaction type
  const interactionConfig = {
    none: {
      icon: Bot,
      bgClass: 'bg-[rgba(var(--color-primary-rgb),0.2)] ring-2 ring-[rgba(var(--color-primary-light-rgb),0.5)]',
      iconColor: 'text-[var(--color-primary-light)]',
      badgeClass: 'bg-slate-700 text-slate-200',
      badgeText: 'Autonomous'
    },
    context: {
      icon: UserCheck,
      bgClass: 'bg-[rgba(var(--color-secondary-rgb),0.2)] ring-2 ring-[rgba(var(--color-secondary-light-rgb),0.5)]',
      iconColor: 'text-[var(--color-secondary-light)]',
      badgeClass: 'bg-[var(--color-secondary)] text-white shadow-lg [box-shadow:0_0_0_rgba(var(--color-secondary-rgb),0.5)]',
      badgeText: 'Human in the Loop'
    },
    approval: {
      icon: UserCheck,
      bgClass: 'bg-[rgba(var(--color-accent-rgb),0.2)] ring-2 ring-[rgba(var(--color-accent-light-rgb),0.5)]',
      iconColor: 'text-[var(--color-accent-light)]',
      badgeClass: 'bg-[var(--color-accent)] text-white shadow-lg [box-shadow:0_0_0_rgba(var(--color-accent-rgb),0.5)]',
      badgeText: 'REQUIRES APPROVAL'
    }
  };
  
  const config = interactionConfig[interactionType];
  const Icon = config.icon;
  
  return (
    <div className={`overflow-hidden rounded-xl border-2 transition-all ${isOpen ? 'border-[var(--color-primary-light)] bg-slate-800 shadow-xl [box-shadow:0_0_0_rgba(var(--color-primary-rgb),0.2)]' : 'border-slate-600 bg-slate-800/50'}`}>
      <button
        onClick={onToggle}
        className="flex w-full items-center gap-4 p-5 text-left transition-colors hover:bg-slate-700/50 border-l-4 border-transparent hover:border-[var(--color-primary-light)]"
      >
        <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full border-2 transition-all ${isOpen ? 'border-blue-400 bg-blue-500/20 rotate-90' : 'border-blue-500 bg-slate-700/50'}`}>
          <ChevronRight className={`h-4 w-4 transition-transform ${isOpen ? 'text-blue-400' : 'text-blue-500'}`} />
        </div>
        <div className="flex items-center gap-3">
          <div className={`rounded-lg p-2.5 ${config.bgClass}`}>
            <Icon className={`h-5 w-5 ${config.iconColor}`} />
          </div>
          <span className="text-lg font-bold text-white">
            {agentName}
          </span>
        </div>
        <div className="ml-auto flex items-center gap-2">
          {interactionType !== 'none' && (
            <span className={`rounded-lg px-3 py-1 text-xs font-bold ${config.badgeClass}`}>
              {config.badgeText}
            </span>
          )}
        </div>
      </button>
      {isOpen && (
        <div className="space-y-5 border-t-2 border-[rgba(var(--color-primary-light-rgb),0.3)] bg-slate-900 p-6 ml-4">
          <div className="rounded-lg bg-slate-800/70 p-4 border-l-4 border-[var(--color-primary-light)]">
            <p className="text-sm leading-relaxed text-slate-200">
              {String(agent?.description || 'No description provided.')}
            </p>
          </div>

          {hasLifecycleHooks && (
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-xs font-black uppercase tracking-wider text-[var(--color-accent-light)]">
                <Activity className="h-4 w-4" />
                Lifecycle Hooks
              </div>
              <div className="grid gap-3">
                {combinedLifecycleHooks.map((hook, hIdx) => (
                  <LifecycleCard key={`agent-hook-${hIdx}`} operation={hook} idx={hIdx} compact />
                ))}
              </div>
            </div>
          )}

          {hasSystemHooks && (
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-xs font-black uppercase tracking-wider text-[var(--color-secondary-light)]">
                <Settings className="h-4 w-4" />
                System Hooks
              </div>
              <div className="grid gap-3">
                {systemHooks.map((hook, hIdx) => (
                  <div key={`system-hook-${hIdx}`} className="rounded-lg border-2 border-slate-600 bg-slate-800/40 p-4">
                    <p className="text-sm font-semibold text-white">{hook.name}</p>
                    {hook.purpose && (
                      <p className="mt-1 text-xs text-slate-300">{hook.purpose}</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="space-y-4">
            {integrationTools.length > 0 && (
              <ToolSection title="Integrations" icon={Plug} items={integrationTools} type="integration" />
            )}
            {!hasTools && !hasLifecycleHooks && (
              <div className="rounded-lg border-2 border-dashed border-slate-600 bg-slate-800/30 p-6 text-center text-sm font-medium text-slate-400">
                No tools configured for this agent yet
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

const PhaseAccordion = ({ phase, index, open, onToggle, lifecycleOperations = [] }) => {
  const agents = Array.isArray(phase?.agents) ? phase.agents : [];
  const [openAgents, setOpenAgents] = useState({});
  const toggleAgent = (i) => setOpenAgents(prev => ({ ...prev, [i]: !prev[i] }));

  // Helper to get lifecycle hooks for a specific agent
  const getAgentLifecycleHooks = (agentName) => {
    return lifecycleOperations.filter(op => {
      const trigger = String(op.trigger || '').toLowerCase();
      const target = String(op.target || '').trim();
      return (trigger === 'before_agent' || trigger === 'after_agent') && target === agentName;
    });
  };
  
  // Count approval gates
  const approvalCount = agents.filter(a => 
    String(a?.human_interaction || '').toLowerCase() === 'approval'
  ).length;
  
  // Count context collection points
  const contextCount = agents.filter(a => 
    String(a?.human_interaction || '').toLowerCase() === 'context'
  ).length;
  
  return (
    <div className={`overflow-hidden rounded-2xl transition-all ${open ? components.accordionOpen : components.accordionClosed}`}>
      <button
        onClick={onToggle}
        className="flex w-full items-center gap-5 p-6 text-left transition-colors hover:bg-slate-750"
      >
        <div className={`flex h-14 w-14 shrink-0 items-center justify-center rounded-xl ${open ? 'bg-gradient-to-br from-[var(--color-primary)] to-[var(--color-secondary)] shadow-lg [box-shadow:0_0_0_rgba(var(--color-primary-rgb),0.5)]' : 'bg-slate-700'}`}>
          {open ? (
            <ChevronDown className="h-6 w-6 text-white" />
          ) : (
            <ChevronRight className="h-6 w-6 text-slate-300" />
          )}
        </div>
        <div className="flex items-center gap-4">
          <span className="text-xl font-black text-white">
            {String(phase?.name || `Phase ${index + 1}`)}
          </span>
        </div>
        <div className="ml-auto flex items-center gap-4">
          <div className="flex items-center gap-2 rounded-lg bg-slate-700 px-4 py-2.5">
            <Activity className="h-4 w-4 text-[var(--color-primary-light)]" />
            <span className="font-bold text-white">{agents.length}</span>
            <span className="text-sm text-slate-300">{agents.length === 1 ? 'Agent' : 'Agents'}</span>
          </div>
          {contextCount > 0 && (
            <span className="rounded-lg bg-[var(--color-secondary)] px-4 py-2.5 font-bold text-white shadow-lg [box-shadow:0_0_0_rgba(var(--color-secondary-rgb),0.5)]">
              {contextCount} Human In The Loop
            </span>
          )}
          {approvalCount > 0 && (
            <span className="rounded-lg bg-[var(--color-accent)] px-4 py-2.5 font-bold text-white shadow-lg [box-shadow:0_0_0_rgba(var(--color-accent-rgb),0.5)]">
              {approvalCount} Approval {approvalCount === 1 ? 'Gate' : 'Gates'}
            </span>
          )}
        </div>
      </button>
      {open && (
        <div className="space-y-6 border-t-4 border-[rgba(var(--color-primary-light-rgb),0.3)] bg-slate-900 p-6">
          <div className="rounded-lg bg-slate-800/50 p-5 border-l-4 border-[var(--color-primary-light)]">
            <p className="text-base leading-relaxed text-slate-200">
              {String(phase?.description || 'No description provided.')}
            </p>
          </div>
          <div className="space-y-4">
            <div className="flex items-center gap-2 text-sm font-black uppercase tracking-wider text-[var(--color-primary-light)]">
              <Bot className="h-5 w-5" />
              Agents
            </div>
            {agents.length > 0 ? (
              agents.map((agent, aIdx) => {
                const agentName = String(agent?.agent_name || agent?.name || '');
                const agentHooks = getAgentLifecycleHooks(agentName);
                return (
                  <AgentAccordionRow
                    key={aIdx}
                    agent={agent}
                    index={aIdx}
                    isOpen={!!openAgents[aIdx]}
                    onToggle={() => toggleAgent(aIdx)}
                    agentLifecycleHooks={agentHooks}
                  />
                );
              })
            ) : (
              <div className="rounded-lg border-2 border-dashed border-slate-600 bg-slate-800/30 p-8 text-center text-sm font-medium text-slate-400">
                No agents defined in this phase
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

// Mermaid preview with bold styling and multi-diagram support (flowchart + sequence)
const MermaidPreview = ({ chart, pendingMessage, pattern }) => {
  const ref = useRef(null);
  useEffect(() => {
    if (typeof window === 'undefined') return () => {};

    let disposed = false;

    const detectTheme = () => {
      const root = document.documentElement;
      const body = document.body;
      const rootStyle = root ? window.getComputedStyle(root) : null;
      const bodyStyle = body ? window.getComputedStyle(body) : null;

      const hasDarkClass = (root?.classList?.contains('dark') || body?.classList?.contains('dark')) ?? false;
      const dataTheme = (root?.dataset?.theme || root?.getAttribute('data-theme') || body?.dataset?.theme || body?.getAttribute('data-theme') || '').toLowerCase();
      const declaredScheme = (rootStyle?.colorScheme || bodyStyle?.colorScheme || '').toLowerCase();
      const mediaPrefersDark = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)').matches : false;

      const isDark = Boolean(hasDarkClass || dataTheme.includes('dark') || declaredScheme.includes('dark') || mediaPrefersDark);

      const pickVar = (name, fallback) => {
        const val = rootStyle?.getPropertyValue(name) || bodyStyle?.getPropertyValue(name);
        return val && val.trim().length ? val.trim() : fallback;
      };

      const palette = {
        text: pickVar('--color-text-primary', isDark ? '#e2e8f0' : '#1f2937'),
        textSecondary: pickVar('--color-text-secondary', isDark ? '#cbd5f5' : '#4b5563'),
        surface: pickVar('--color-surface', isDark ? '#0f172a' : '#ffffff'),
        surfaceAlt: pickVar('--color-surface-alt', isDark ? '#131d33' : '#f9fafb'),
        note: pickVar('--color-surface-overlay', isDark ? '#1e293b' : '#f3f4f6'),
        border: pickVar('--color-border-subtle', isDark ? '#334155' : '#d1d5db'),
        primary: pickVar('--color-primary', '#3b82f6'),
        primaryLight: pickVar('--color-primary-light', '#60a5fa'),
        secondary: pickVar('--color-secondary', '#8b5cf6'),
        accent: pickVar('--color-accent', '#10b981')
      };

      return { isDark, palette };
    };

    const shouldOverrideFill = (fill, isDark) => {
      if (!fill) return true;
      const normalized = fill.trim().toLowerCase();
      const alwaysOverride = ['none', 'transparent', '#fff', '#ffffff', 'white'];
      if (alwaysOverride.includes(normalized)) return true;
      if (!isDark) return false;
      const softLights = ['#edf2ae', '#fefce8', '#f5f5f5', '#eaeaea', '#f9fafb'];
      if (softLights.includes(normalized)) return true;
      const hexMatch = normalized.match(/^#([0-9a-f]{6})$/i);
      if (hexMatch) {
        const hex = hexMatch[1];
        const r = parseInt(hex.slice(0, 2), 16);
        const g = parseInt(hex.slice(2, 4), 16);
        const b = parseInt(hex.slice(4, 6), 16);
        const brightness = (r * 299 + g * 587 + b * 114) / 1000;
        return brightness > 180; // treat bright colors as needing override in dark mode
      }
      return false;
    };

    const applyFill = (el, fill, stroke) => {
      if (!el) return;
      if (fill) {
        el.setAttribute('fill', fill);
        el.style.fill = fill;
      }
      if (stroke) {
        el.setAttribute('stroke', stroke);
        el.style.stroke = stroke;
      }
    };

    const renderDiagram = async () => {
      if (disposed) return;

      const hasChart = typeof chart === 'string' && chart.trim().length > 0;
      if (!hasChart) {
        if (!ref.current) return;
        const safeMessage = typeof pendingMessage === 'string' && pendingMessage.trim().length > 0
          ? pendingMessage.trim()
          : 'Approve the plan to generate a Mermaid sequence diagram.';
        ref.current.innerHTML = `<div class="flex h-full items-center justify-center p-6 text-center text-sm text-slate-400">${safeMessage}</div>`;
        return;
      }

      let normalized = chart.trim();
      const isSequence = normalized.startsWith('sequenceDiagram');
      if (isSequence) {
        // Guarantee a newline after the header
        normalized = normalized.replace(/^sequenceDiagram(\s*)/i, 'sequenceDiagram\n');
      }
      const normalizeLineEndings = (s) => s.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
      const sanitizeSequence = (s) => {
        // Backend _fix_mermaid_syntax now handles all sanitization including legend stripping
        // Frontend only normalizes line endings for cross-platform compatibility
        return normalizeLineEndings(s);
      };
      if (isSequence) {
        normalized = sanitizeSequence(normalized);
      }
      const isFlowchart = normalized.startsWith('flowchart');

      if (!isSequence && isFlowchart) {
        const isLR = normalized.startsWith('flowchart LR');
        const nodeMatches = normalized.match(/\w+[[(]/g);
        const nodeCount = nodeMatches ? nodeMatches.length : 0;
        console.log('🎨 [MermaidPreview] Analyzing flowchart:', { isLR, nodeCount });
        if (isLR && nodeCount > 5) {
          normalized = normalized.replace('flowchart LR', 'flowchart TD');
          console.log('🎨 [MermaidPreview] Converted LR to TD for better layout (nodeCount:', nodeCount, ')');
        }
      }

      if (!isSequence && !isFlowchart) {
        normalized = 'flowchart TD\n' + normalized;
      }

      const themeState = detectTheme();

      const safeRender = () => {
        try {
          const id = `diag-${Math.random().toString(36).slice(2)}`;
          const { isDark, palette } = themeState;

          const mermaidConfig = {
            startOnLoad: false,
            theme: isDark ? 'dark' : 'neutral',
            flowchart: {
              htmlLabels: true,
              curve: 'basis',
              padding: 20,
              nodeSpacing: 80,
              rankSpacing: 80,
              useMaxWidth: true,
              wrappingWidth: 200
            },
            sequence: {
              diagramMarginX: 20,
              diagramMarginY: 20,
              actorMargin: 80,
              width: 200,
              height: 65,
              boxMargin: 10,
              boxTextMargin: 5,
              noteMargin: 10,
              messageMargin: 50,
              mirrorActors: true,
              useMaxWidth: true,
              wrap: true,
              wrapPadding: 10
            },
            themeVariables: {
              primaryColor: palette.primary,
              primaryTextColor: palette.text,
              primaryBorderColor: palette.primaryLight,
              lineColor: palette.border,
              secondaryColor: palette.secondary,
              tertiaryColor: palette.accent,
              noteBkgColor: palette.note,
              noteTextColor: palette.text,
              noteBorderColor: palette.border,
              activationBkgColor: isDark ? palette.secondary : palette.surfaceAlt,
              activationBorderColor: palette.primaryLight,
              sequenceNumberColor: palette.text,
              fontSize: '16px',
              fontFamily: 'ui-sans-serif, system-ui, sans-serif'
            }
          };

          window.mermaid.initialize(mermaidConfig);

          window.mermaid.render(id, normalized).then(({ svg }) => {
            if (!ref.current || disposed) return;
            ref.current.innerHTML = svg;
            const svgEl = ref.current.querySelector('svg');
            if (!svgEl) return;

            svgEl.style.maxWidth = '100%';
            svgEl.style.height = 'auto';
            svgEl.style.minHeight = isSequence ? '500px' : '400px';
            svgEl.style.colorScheme = isDark ? 'dark' : 'light';
            svgEl.style.background = palette.surfaceAlt;
            ref.current.style.background = palette.surface;

            console.log('🎨 [MermaidPreview] SVG Color Mode:', {
              dark: isDark,
              text: palette.text,
              note: palette.note,
              surface: palette.surface,
              surfaceAlt: palette.surfaceAlt
            });

            const textElements = svgEl.querySelectorAll('text, tspan, .messageText, .labelText, .actor');
            textElements.forEach((el) => applyFill(el, palette.text));

            const noteRects = svgEl.querySelectorAll('rect.note, .noteBox');
            noteRects.forEach((el) => applyFill(el, palette.note, palette.border));

            const actorRects = svgEl.querySelectorAll('rect.actor, .actor-box');
            actorRects.forEach((el) => {
              if (isDark || shouldOverrideFill(el.getAttribute('fill'), isDark)) {
                applyFill(el, palette.surface, palette.border);
              }
            });

            const otherRects = svgEl.querySelectorAll('rect:not(.note):not(.noteBox):not(.actor):not(.actor-box)');
            otherRects.forEach((el) => {
              if (shouldOverrideFill(el.getAttribute('fill'), isDark)) {
                applyFill(el, palette.surfaceAlt, palette.border);
              }
            });
          }).catch((err) => {
            console.error('🎨 [MermaidPreview] Render error:', err);
            if (ref.current && !disposed) {
              ref.current.innerHTML = '<div class="flex items-center justify-center h-full text-sm text-[var(--color-error)]">Diagram render error</div>';
            }
          });
        } catch (err) {
          console.error('🎨 [MermaidPreview] Render exception:', err);
          if (ref.current && !disposed) {
            ref.current.innerHTML = '<div class="flex items-center justify-center h-full text-sm text-[var(--color-error)]">Diagram render error</div>';
          }
        }
      };

      if (!window.mermaid) {
        const script = document.createElement('script');
        script.src = 'https://cdnjs.cloudflare.com/ajax/libs/mermaid/10.6.1/mermaid.min.js';
        script.onload = () => !disposed && safeRender();
        script.onerror = () => {
          console.error('🎨 [MermaidPreview] Failed to load Mermaid.js');
          if (ref.current && !disposed) {
            ref.current.innerHTML = '<div class="flex items-center justify-center h-full text-sm text-[var(--color-error)]">Failed to load diagram library</div>';
          }
        };
        document.head.appendChild(script);
      } else {
        safeRender();
      }
    };

    renderDiagram();

    const handleThemeChange = () => {
      if (!disposed) {
        renderDiagram();
      }
    };

    let mql;
    if (window.matchMedia) {
      mql = window.matchMedia('(prefers-color-scheme: dark)');
      try {
        mql.addEventListener('change', handleThemeChange);
      } catch {
        mql.addListener(handleThemeChange);
      }
    }

    let observer;
    if (window.MutationObserver) {
      observer = new MutationObserver(handleThemeChange);
      try {
        observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class', 'data-theme'] });
        if (document.body) {
          observer.observe(document.body, { attributes: true, attributeFilter: ['class', 'data-theme'] });
        }
      } catch {}
    }

    return () => {
      disposed = true;
      if (mql) {
        try {
          mql.removeEventListener('change', handleThemeChange);
        } catch {
          mql.removeListener(handleThemeChange);
        }
      }
      observer?.disconnect();
    };
  }, [chart, pendingMessage]);
  
  return (
    <div className={`${components.card.primary} overflow-hidden rounded-2xl`}>
      <div className="flex items-center justify-between border-b-3 border-[rgba(var(--color-secondary-rgb),0.5)] bg-gradient-to-r from-[var(--color-secondary-dark)] to-purple-600 px-6 py-4">
        <div className="flex items-center gap-3 text-base font-black uppercase tracking-wider text-white">
          <GitBranch className="h-5 w-5" />
          Workflow Diagram
        </div>
        {pattern && (
          <SemanticChip value={pattern} mapping={PATTERN_META} prefix="Pattern" icon={GitBranch} />
        )}
      </div>
      <div ref={ref} className="min-h-[400px] overflow-auto bg-slate-850 p-8" />
    </div>
  );
};

// Data View - Connection status and context variables
const DataView = ({ workflow, contextVariableDefinitions }) => {
  const definitions = contextVariableDefinitions || {};
  
  // Group variables by source type
  const variablesByType = {
    environment: [],
    static: [],
    database: [],
    derived: []
  };
  
  Object.entries(definitions).forEach(([name, def]) => {
    const type = def?.source?.type || def?.type || 'derived';
    if (variablesByType[type]) {
      variablesByType[type].push({ name, ...def });
    }
  });
  
  // Check for database configuration
  const hasDatabaseVars = variablesByType.database.length > 0;
  const hasRuntimeVars = variablesByType.derived.length > 0;
  const hasSystemVars = variablesByType.environment.length > 0 || variablesByType.static.length > 0;
  
  // Check context-aware status (would come from environment/config)
  const contextAwareEnabled = hasDatabaseVars; // True if any database variables exist
  
  // Extract unique database collections from database variables
  const databaseCollections = new Set();
  variablesByType.database.forEach(variable => {
    const collection = variable?.source?.collection || variable?.collection;
    if (collection && typeof collection === 'string') {
      databaseCollections.add(collection);
    }
  });
  
  return (
    <div className="space-y-6">
      {/* Connection Status Overview */}
      <div className="rounded-xl border-2 border-[rgba(var(--color-primary-rgb),0.5)] bg-gradient-to-br from-slate-800/80 to-slate-900/80 p-6 min-h-[200px] flex flex-col">
        <div className="flex items-start gap-4 mb-6">
          <div className={`rounded-lg p-3 ring-2 ${
            contextAwareEnabled 
              ? 'bg-[rgba(var(--color-success-rgb),0.3)] ring-[rgba(var(--color-success-light-rgb),0.5)]' 
              : 'bg-[rgba(var(--color-warning-rgb),0.3)] ring-[rgba(var(--color-warning-light-rgb),0.5)]'
          }`}>
            <Database className={`h-6 w-6 ${contextAwareEnabled ? 'text-green-400' : 'text-amber-400'}`} />
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-2">
              <h3 className="text-xl font-black text-white">Connection Status</h3>
              <span className={`rounded-full px-3 py-1 text-xs font-bold uppercase tracking-wider ${
                contextAwareEnabled
                  ? 'bg-green-500/20 border-2 border-green-500/50 text-green-300'
                  : 'bg-amber-500/20 border-2 border-amber-500/50 text-amber-300'
              }`}>
                {contextAwareEnabled ? 'Connected' : 'Not Connected'}
              </span>
            </div>
            {!contextAwareEnabled && (
              <p className="text-sm text-slate-400 mt-2">
                Configure your MongoDB URL in settings to enable context-aware features
              </p>
            )}
          </div>
        </div>
        
        {/* Database Schema Info */}
        {contextAwareEnabled && workflow?.database_schema && (
          <div className="mb-4">
            <div className="flex items-center gap-2 mb-3">
              <span className="text-xs font-black uppercase tracking-widest text-slate-400">
                Database: {workflow.database_schema.database_name || 'Unknown'}
              </span>
              <span className="rounded-full bg-blue-500/20 border border-blue-500/50 px-2 py-0.5 text-xs font-bold text-blue-300">
                {workflow.database_schema.total_collections || workflow.database_schema.collections?.length || 0} Collections
              </span>
            </div>
            
            {/* Collections Grid */}
            {workflow.database_schema.collections && workflow.database_schema.collections.length > 0 && (
              <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
                {workflow.database_schema.collections.map((collection, idx) => (
                  <div key={idx} className="rounded-lg border border-blue-500/50 bg-blue-500/5 p-3">
                    <div className="flex items-center justify-between gap-2 mb-2">
                      <span className="text-sm font-bold text-blue-300">{collection.name}</span>
                      {collection.is_enterprise && (
                        <span className="rounded bg-purple-500/20 border border-purple-500/50 px-2 py-0.5 text-xs font-semibold text-purple-300">
                          Enterprise
                        </span>
                      )}
                    </div>
                    
                    {/* Field Types */}
                    {collection.fields && collection.fields.length > 0 && (
                      <div className="space-y-1 mt-2">
                        <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">
                          Fields ({collection.fields.length})
                        </div>
                        <div className="max-h-32 overflow-y-auto space-y-1">
                          {collection.fields.slice(0, 8).map((field, fieldIdx) => (
                            <div key={fieldIdx} className="flex items-center justify-between text-xs">
                              <span className="text-slate-300 font-mono">{field.name}</span>
                              <span className="text-slate-500 font-mono">{field.type}</span>
                            </div>
                          ))}
                          {collection.fields.length > 8 && (
                            <div className="text-xs text-slate-500 italic">
                              +{collection.fields.length - 8} more fields
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                    
                    {/* Sample Data Indicator */}
                    {collection.has_sample_data && (
                      <div className="mt-2 pt-2 border-t border-blue-500/20">
                        <span className="text-xs text-blue-400">
                          ✓ Sample data available
                        </span>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
        
        {/* Legacy: Database Collections from variables (fallback) */}
        {contextAwareEnabled && !workflow?.database_schema && databaseCollections.size > 0 && (
          <div className="mb-4">
            <div className="flex items-center gap-2 mb-3">
              <span className="text-xs font-black uppercase tracking-widest text-slate-400">
                Active Collections
              </span>
              <span className="rounded-full bg-blue-500/20 border border-blue-500/50 px-2 py-0.5 text-xs font-bold text-blue-300">
                {databaseCollections.size}
              </span>
            </div>
            <div className="flex flex-wrap gap-2">
              {Array.from(databaseCollections).map((collection, idx) => (
                <div key={idx} className="rounded-lg border border-blue-500/50 bg-blue-500/10 px-3 py-1.5">
                  <span className="text-sm font-semibold text-blue-300">{collection}</span>
                </div>
              ))}
            </div>
          </div>
        )}
        
        {/* Database Variables Cards */}
        {contextAwareEnabled && hasDatabaseVars && (
          <div className="flex-1">
            <div className="text-xs font-black uppercase tracking-widest text-slate-400 mb-3">
              Database Variables
            </div>
            <div className="space-y-2">
              {variablesByType.database.map((variable, idx) => (
                <div key={idx} className="rounded-lg border border-slate-700 bg-slate-800/70 p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-bold text-[var(--color-primary-light)]">{variable.name}</span>
                        <span className="rounded-full bg-blue-500/20 border border-blue-500/50 px-2 py-0.5 text-xs font-semibold text-blue-300">
                          Database
                        </span>
                      </div>
                      {variable.purpose && (
                        <p className="text-xs text-slate-300 mb-2">{variable.purpose}</p>
                      )}
                      {variable.trigger_hint && (
                        <p className="text-xs text-slate-500">
                          <span className="text-slate-400">Source:</span> {variable.trigger_hint}
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
      
      {/* System Variables Section */}
      {hasSystemVars && (
        <div className="rounded-xl border-2 border-[rgba(var(--color-secondary-rgb),0.4)] bg-slate-800/50 p-6 min-h-[200px] flex flex-col">
          <div className="flex items-center gap-2 mb-4">
            <Settings className="h-5 w-5 text-[var(--color-secondary-light)]" />
            <span className="text-sm font-bold uppercase tracking-wider text-[var(--color-secondary-light)]">
              System Configuration
            </span>
            <span className="rounded-full bg-[var(--color-secondary)] px-2 py-0.5 text-xs font-bold text-white">
              {variablesByType.environment.length + variablesByType.static.length}
            </span>
          </div>
          <p className="text-xs text-slate-400 mb-4">
            Pre-configured values loaded from environment or workflow definition
          </p>
          <div className="grid gap-3 md:grid-cols-2 flex-1">
            {[...variablesByType.environment, ...variablesByType.static].map((variable, idx) => (
              <div key={idx} className="rounded-lg border border-slate-700 bg-slate-800/70 p-3 h-fit">
                <div className="flex items-start justify-between gap-2 mb-2">
                  <span className="font-bold text-white text-sm">{variable.name}</span>
                  <span className="rounded-full bg-green-500/20 border border-green-500/50 px-2 py-0.5 text-xs font-semibold text-green-300">
                    {variable.source?.type === 'environment' ? 'ENV' : 'STATIC'}
                  </span>
                </div>
                {variable.purpose && (
                  <p className="text-xs text-slate-300">{variable.purpose}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
      
      {/* Derived Variables Section */}
      {hasRuntimeVars && (
        <div className="rounded-xl border-2 border-[rgba(var(--color-accent-rgb),0.4)] bg-slate-800/50 p-6 min-h-[200px] flex flex-col">
          <div className="flex items-center gap-2 mb-4">
            <Activity className="h-5 w-5 text-[var(--color-accent-light)]" />
            <span className="text-sm font-bold uppercase tracking-wider text-[var(--color-accent-light)]">
              Derived Variables
            </span>
            <span className="rounded-full bg-[var(--color-accent)] px-2 py-0.5 text-xs font-bold text-white">
              {variablesByType.derived.length}
            </span>
          </div>
          <p className="text-xs text-slate-400 mb-4">
            Variables computed during workflow execution based on agent outputs or user interactions
          </p>
          <div className="space-y-3 flex-1">
            {variablesByType.derived.map((variable, idx) => (
              <div key={idx} className="rounded-lg border border-slate-700 bg-slate-800/70 p-3">
                <div className="flex items-start justify-between gap-3 mb-2">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-white text-sm">{variable.name}</span>
                    <span className="rounded-full bg-amber-500/20 border border-amber-500/50 px-2 py-0.5 text-xs font-semibold text-amber-300">
                      Derived
                    </span>
                  </div>
                </div>
                {variable.purpose && (
                  <p className="text-xs text-slate-300 mb-2">{variable.purpose}</p>
                )}
                {variable.trigger_hint && (
                  <div className="rounded-md bg-slate-900/50 border border-slate-600 p-2 mt-2">
                    <p className="text-xs text-slate-400">
                      <span className="font-semibold text-slate-300">Trigger:</span> {variable.trigger_hint}
                    </p>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
      
      {/* Empty State */}
      {!hasDatabaseVars && !hasSystemVars && !hasRuntimeVars && (
        <div className="rounded-xl border-2 border-slate-700 bg-slate-800/50 p-12 text-center">
          <Database className="h-12 w-12 text-slate-600 mx-auto mb-4" />
          <p className="text-slate-400 text-sm">No context variables defined for this workflow</p>
        </div>
      )}
    </div>
  );
};

const ActionPlan = ({ payload = {}, onResponse, ui_tool_id, eventId, workflowName, componentId = 'ActionPlan' }) => {
  // CRITICAL: All hooks MUST be called before any conditional returns (React rules of hooks)
  // Initialize state first
  const [pending, setPending] = useState(false);
  const [openPhases, setOpenPhases] = useState({ 0: true });
  const [activeTab, setActiveTab] = useState('workflow'); // Tab state: 'workflow' | 'data' | 'interactions' | 'diagram'
  
  // CRITICAL: Early validation to prevent null reference errors on revision (AFTER hooks)
  const isValidPayload = payload && typeof payload === 'object';
  
  if (!isValidPayload) {
    console.error('🎨 [ActionPlan] Invalid payload received:', payload);
    return (
      <div className="min-h-screen space-y-8 rounded-2xl p-8 bg-slate-900 text-white">
        <div className="text-[var(--color-error)]">Error: Invalid workflow data received. Please refresh and try again.</div>
      </div>
    );
  }

  // CRITICAL: Early logging to debug render issues
  try {
    console.log('🎨 [ActionPlan] Component ENTRY - Starting render', {
      payloadKeys: Object.keys(payload),
      ui_tool_id,
      eventId
    });
  } catch (e) {
    console.error('🎨 [ActionPlan] Error in entry logging:', e);
  }
  
  // Resolve root according to the current UI payload contract:
  // Preferred shape from tool: { workflow, agent_message, agent_message_id, ... }
  // Legacy shapes still supported: { ActionPlan: { workflow }, agent_message } OR { action_plan: { workflow }, agent_message }
  const preferredWorkflow = payload?.workflow && typeof payload.workflow === 'object' && !Array.isArray(payload.workflow) ? payload.workflow : null;
  const nestedActionPlan = payload?.ActionPlan && typeof payload.ActionPlan === 'object' && !Array.isArray(payload.ActionPlan) ? payload.ActionPlan : null;
  const nestedActionPlanLC = payload?.action_plan && typeof payload.action_plan === 'object' && !Array.isArray(payload.action_plan) ? payload.action_plan : null;

  const workflow =
    preferredWorkflow ||
    (nestedActionPlan?.workflow && typeof nestedActionPlan.workflow === 'object' && !Array.isArray(nestedActionPlan.workflow) ? nestedActionPlan.workflow : null) ||
    (nestedActionPlanLC?.workflow && typeof nestedActionPlanLC.workflow === 'object' && !Array.isArray(nestedActionPlanLC.workflow) ? nestedActionPlanLC.workflow : null) ||
    {};
  
  try {
    console.log('🎨 [ActionPlan] Resolved workflow:', {
      hasWorkflow: !!workflow,
      workflowType: typeof workflow,
      isArray: Array.isArray(workflow),
      workflowKeys: workflow && typeof workflow === 'object' && !Array.isArray(workflow) ? Object.keys(workflow) : 'not-an-object',
      name: workflow?.name,
      trigger: workflow?.trigger,
      triggerType: typeof workflow?.trigger,
      hasTechnicalBlueprint: !!workflow?.technical_blueprint,
      hasLifecycleOps: !!workflow?.lifecycle_operations
    });
  } catch (e) {
    console.error('🎨 [ActionPlan] Error logging resolved workflow:', e);
  }

  const safeWorkflow = (workflow && typeof workflow === 'object' && !Array.isArray(workflow)) ? workflow : {};
  const phases = Array.isArray(safeWorkflow?.phases) ? safeWorkflow.phases : [];

  const technicalBlueprintCandidates = [
    safeWorkflow?.technical_blueprint,
    payload?.technical_blueprint,
    payload?.TechnicalBlueprint,
    payload?.ActionPlan?.technical_blueprint,
    payload?.ActionPlan?.TechnicalBlueprint,
    payload?.action_plan?.technical_blueprint,
    payload?.action_plan?.TechnicalBlueprint,
    payload?.ActionPlan?.workflow?.technical_blueprint,
    payload?.action_plan?.workflow?.technical_blueprint,
  ];
  const technicalBlueprint = technicalBlueprintCandidates.find(
    (candidate) => candidate && typeof candidate === 'object' && !Array.isArray(candidate),
  ) || null;

  console.log('🎨 [ActionPlan] TechnicalBlueprint resolved:', {
    found: !!technicalBlueprint,
    keys: technicalBlueprint ? Object.keys(technicalBlueprint) : 'null',
    before_chat_lifecycle: technicalBlueprint?.before_chat_lifecycle,
    after_chat_lifecycle: technicalBlueprint?.after_chat_lifecycle,
    global_context_variables_count: Array.isArray(technicalBlueprint?.global_context_variables) ? technicalBlueprint.global_context_variables.length : 0,
    ui_components_count: Array.isArray(technicalBlueprint?.ui_components) ? technicalBlueprint.ui_components.length : 0
  });

  const workflowLifecycleOperations = normalizeLifecycleOperations(safeWorkflow?.lifecycle_operations);
  const blueprintLifecycleOperations = normalizeLifecycleOperations(technicalBlueprint?.lifecycle_operations || null);
  const blueprintBeforeChat = normalizeLifecycleOperations(
    technicalBlueprint?.before_chat_lifecycle
      ? {
          ...technicalBlueprint.before_chat_lifecycle,
          trigger: technicalBlueprint.before_chat_lifecycle.trigger || 'before_chat',
        }
      : null,
  );
  const blueprintAfterChat = normalizeLifecycleOperations(
    technicalBlueprint?.after_chat_lifecycle
      ? {
          ...technicalBlueprint.after_chat_lifecycle,
          trigger: technicalBlueprint.after_chat_lifecycle.trigger || 'after_chat',
        }
      : null,
  );
  const lifecycleOperations = mergeLifecycleCollections(
    workflowLifecycleOperations,
    blueprintLifecycleOperations,
    blueprintBeforeChat,
    blueprintAfterChat
  );

  console.log('🎨 [ActionPlan] Lifecycle operations debug:', {
    workflowCount: workflowLifecycleOperations.length,
    blueprintCount: blueprintLifecycleOperations.length,
    beforeChatCount: blueprintBeforeChat.length,
    afterChatCount: blueprintAfterChat.length,
    mergedCount: lifecycleOperations.length,
    hasTechnicalBlueprint: !!technicalBlueprint,
    blueprintKeys: technicalBlueprint ? Object.keys(technicalBlueprint) : 'null'
  });

  // Separate lifecycle operations by context
  const chatLevelHooks = {
    before_chat: lifecycleOperations.filter(op => String(op.trigger || '').toLowerCase() === 'before_chat'),
    after_chat: lifecycleOperations.filter(op => String(op.trigger || '').toLowerCase() === 'after_chat'),
  };
  if (chatLevelHooks.before_chat.length === 0 && technicalBlueprint?.before_chat_lifecycle) {
    const fallbackBefore = normalizeLifecycleOperations({
      ...technicalBlueprint.before_chat_lifecycle,
      trigger: technicalBlueprint.before_chat_lifecycle.trigger || 'before_chat',
    });
    if (fallbackBefore.length > 0) {
      chatLevelHooks.before_chat = mergeLifecycleCollections(chatLevelHooks.before_chat, fallbackBefore);
    }
  }
  if (chatLevelHooks.after_chat.length === 0 && technicalBlueprint?.after_chat_lifecycle) {
    const fallbackAfter = normalizeLifecycleOperations({
      ...technicalBlueprint.after_chat_lifecycle,
      trigger: technicalBlueprint.after_chat_lifecycle.trigger || 'after_chat',
    });
    if (fallbackAfter.length > 0) {
      chatLevelHooks.after_chat = mergeLifecycleCollections(chatLevelHooks.after_chat, fallbackAfter);
    }
  }

  console.log('🎨 [ActionPlan] Final chat-level hooks:', {
    beforeChatCount: chatLevelHooks.before_chat.length,
    afterChatCount: chatLevelHooks.after_chat.length,
    beforeChat: chatLevelHooks.before_chat,
    afterChat: chatLevelHooks.after_chat
  });

  // Agent-level hooks will be distributed to individual agents within phases

  // agent_message intentionally ignored inside artifact to avoid duplicate display in chat; previously parsed here.
  // (If future logic needs it for analytics, reintroduce as const agentMessage = String(payload?.agent_message || '') and use.)

  // Derived counts (computed; not part of schema)
  const agentCount = phases.reduce((acc, p) => acc + (Array.isArray(p?.agents) ? p.agents.length : 0), 0);
  
  // Tool count: deduplicate integrations across all agents (same integration used multiple times = 1 tool)
  const uniqueToolNames = new Set();
  const uniqueIntegrations = new Set();
  phases.forEach(phase => {
    if (!Array.isArray(phase?.agents)) return;
    phase.agents.forEach(agent => {
      const agentTools = Array.isArray(agent?.agent_tools) ? agent.agent_tools : [];
      if (agentTools.length > 0) {
        agentTools.forEach(tool => {
          if (!tool || typeof tool !== 'object') return;
          const toolName = tool?.name ? String(tool.name).trim() : '';
          if (toolName) uniqueToolNames.add(toolName);
          const integration = typeof tool?.integration === 'string' ? tool.integration.trim() : '';
          if (integration) uniqueIntegrations.add(integration);
        });
      } else {
        normalizeStringList(agent?.operations).forEach(name => {
          if (name) uniqueToolNames.add(name);
        });
        normalizeStringList(agent?.integrations).forEach(integration => {
          if (integration) uniqueIntegrations.add(integration);
        });
      }
    });
  });
  const toolCount = uniqueToolNames.size || uniqueIntegrations.size;

  const normalizeDiagram = (value) => (typeof value === 'string' ? value.trim() : '');
  const legacyDiagram = normalizeDiagram(payload?.legacy_mermaid_flow);
  const workflowDiagram = normalizeDiagram(safeWorkflow?.mermaid_flow);
  const mermaidChart = legacyDiagram || workflowDiagram;
  const mermaidMessage = legacyDiagram
    ? 'Legacy diagram supplied by the planner. A refreshed sequence diagram will be generated after approval.'
    : 'Approve the plan to generate a Mermaid sequence diagram.';

  const uicomponents = Array.isArray(safeWorkflow?.ui_components)
    ? safeWorkflow.ui_components
    : Array.isArray(technicalBlueprint?.ui_components)
      ? technicalBlueprint.ui_components
      : [];

  const UIComponentItems = uicomponents.filter(item => item && typeof item === 'object');
  const UIComponentCount = UIComponentItems.length;

  // Logging / action integration
  const agentMessageId = payload?.agent_message_id || payload?.agentMessageId || null;
  const tlog = createToolsLogger({ tool: ui_tool_id || componentId, eventId, workflowName, agentMessageId });
  const togglePhase = (idx) => setOpenPhases(prev => ({ ...prev, [idx]: !prev[idx] }));

  const emit = async ({ action, planAcceptance = false, agentContextOverrides = {} }) => {
    if (pending) return;
    setPending(true);
    try {
      tlog.event(action, 'start');
      const resp = {
        status: 'success',
        action,
        data: {
          action,
          workflow_name: String(safeWorkflow?.name || 'Generated Workflow'),
          trigger: String(safeWorkflow?.trigger || 'chatbot'),
          phase_count: phases.length,
          agent_count: agentCount,
          tool_count: toolCount,
          ui_tool_id,
          eventId,
          workflowName,
          agent_message_id: agentMessageId,
          plan_acceptance: Boolean(planAcceptance),
        },
        plan_acceptance: Boolean(planAcceptance),
        agentContext: {
          action_completed: true,
          workflow_viewed: true,
          action_type: action,
          plan_acceptance: Boolean(planAcceptance),
          ...agentContextOverrides,
        },
      };
      await onResponse?.(resp);
      tlog.event(action, 'done', { ok: true });
    } catch (e) {
      const msg = e?.message || 'Unknown error';
      tlog.error('action_failed', { error: msg });
      onResponse?.({
        status: 'error',
        action,
        error: msg,
        plan_acceptance: Boolean(planAcceptance),
        agentContext: { action_completed: false, plan_acceptance: Boolean(planAcceptance) },
      });
    } finally {
      setPending(false);
    }
  };

  const approve = () => emit({ action: 'accept_workflow', planAcceptance: true });

  // Tab configuration
  const tabs = [
    { id: 'workflow', label: 'Workflow', icon: Compass },
    { id: 'data', label: 'Data', icon: Database },
    { id: 'interactions', label: 'Interactions', icon: MessageSquare },
    { id: 'diagram', label: 'Diagram', icon: GitBranch },
  ];

  return (
    <div className={`min-h-screen space-y-8 rounded-2xl ${components.card.primary}`} data-agent-message-id={agentMessageId || undefined}>
      {/* Header Section */}
        <header className="space-y-6 rounded-2xl border-3 border-[var(--color-primary)] bg-gradient-to-br from-slate-900 to-slate-800 p-8 shadow-2xl [box-shadow:0_0_0_rgba(var(--color-primary-rgb),0.3)]">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div className="flex items-center gap-3 text-sm font-black uppercase tracking-[0.3em] text-[var(--color-primary-light)]">
              <Sparkles className="h-5 w-5" />
              Workflow Blueprint
            </div>
            <div className="flex flex-col items-start gap-2 text-left md:items-end md:text-right">
              <div className="flex flex-wrap items-center gap-2">
                <button
                  onClick={approve}
                  disabled={pending}
                  className={`${components.button.primary} text-xs md:text-sm shadow-lg [box-shadow:0_0_0_rgba(var(--color-primary-rgb),0.3)]`}
                >
                  Approve Plan
                </button>
              </div>
            </div>
          </div>
          
          <div className="space-y-5">
            <h1 className={`${typography.display.xl} ${colors.text.primary} drop-shadow-lg break-words max-w-full leading-tight overflow-hidden`}>
          {String(safeWorkflow?.name || 'Generated Workflow')}
            </h1>
          </div>
        </header>

      {/* Tab Navigation */}
      <div className="flex items-center gap-2 rounded-xl border-2 border-slate-700 bg-slate-900 p-2">
        {tabs.map(tab => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex flex-1 items-center justify-center gap-2 rounded-lg px-4 py-3 text-sm font-bold transition-all ${
                isActive
                  ? 'bg-gradient-to-r from-[var(--color-primary)] to-[var(--color-secondary)] text-white shadow-lg'
                  : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
              }`}
            >
              <Icon className="h-4 w-4" />
              <span className="hidden sm:inline">{tab.label}</span>
            </button>
          );
        })}
      </div>

      {/* Tab Content */}
      {/* Data Tab - Context variables and database information */}
      {activeTab === 'data' && (
        <DataView
          workflow={safeWorkflow}
          contextVariableDefinitions={safeWorkflow?.context_variable_definitions || {}}
        />
      )}

      {/* Interactions Tab - UI Components */}
      {activeTab === 'interactions' && (
        <div className="space-y-6">
          {/* Initialization Process Section */}
          <div className="rounded-xl border-2 border-slate-700 bg-gradient-to-br from-slate-800/80 to-slate-900/80 overflow-hidden shadow-xl">
            <div className="flex items-center gap-3 bg-gradient-to-r from-blue-900/40 via-purple-900/40 to-blue-900/40 px-6 py-5 border-b-2 border-slate-600">
              <Zap className="h-6 w-6 text-blue-400 animate-pulse" />
              <span className="text-xl font-black uppercase tracking-widest text-white">
                Workflow Initialization
              </span>
            </div>
            <div className="grid grid-cols-2 divide-x-2 divide-slate-600/50">
              <div className="p-6 hover:bg-slate-700/30 transition-colors">
                <div className="text-xs font-black uppercase tracking-widest text-blue-300 mb-3">Initiated By</div>
                <div className="text-2xl font-black text-blue-300 mb-2">
                  {INITIATED_BY[String(safeWorkflow?.initiated_by || '').toLowerCase()]?.label || 'Unknown'}
                </div>
                <div className="text-sm text-slate-300 leading-relaxed">
                  {INITIATED_BY[String(safeWorkflow?.initiated_by || '').toLowerCase()]?.desc || 'Not specified'}
                </div>
              </div>
              <div className="p-6 hover:bg-slate-700/30 transition-colors">
                <div className="text-xs font-black uppercase tracking-widest text-blue-300 mb-3">Trigger Type</div>
                <div className="text-2xl font-black text-blue-300 mb-2">
                  {TRIGGER_TYPE[String(safeWorkflow?.trigger_type || inferTriggerTypeFrom(safeWorkflow?.trigger) || '').toLowerCase().replace(/[^a-z0-9]/g, '')]?.label || toTitle(String(safeWorkflow?.trigger_type || safeWorkflow?.trigger || 'Not specified'))}
                </div>
                <div className="text-sm text-slate-300 leading-relaxed">
                  {TRIGGER_TYPE[String(safeWorkflow?.trigger_type || inferTriggerTypeFrom(safeWorkflow?.trigger) || '').toLowerCase().replace(/[^a-z0-9]/g, '')]?.desc || 'Workflow activation condition'}
                </div>
              </div>
            </div>
          </div>

          {/* UI Components Section */}
          {UIComponentCount > 0 ? (
            <div className="space-y-4">
              <div className="flex items-center gap-3 rounded-lg bg-slate-800 px-6 py-4 border-l-4 border-[var(--color-primary-light)]">
                <MousePointerClick className="h-6 w-6 text-[var(--color-primary-light)]" />
                <span className="text-xl font-black uppercase tracking-wider text-white">UI Components</span>
              </div>
              <div className="grid gap-3 lg:grid-cols-2">
                {UIComponentItems.map((component, idx) => (
                  <ComponentCard key={`component-${idx}`} component={component} idx={idx} />
                ))}
              </div>
              
              {/* Legend */}
              <div className="flex items-center justify-center gap-6 rounded-lg bg-slate-800/50 px-6 py-3 border border-slate-700">
                <div className="flex items-center gap-2">
                  <div className="w-4 h-4 rounded border-2 border-blue-500/60 bg-blue-500/20"></div>
                  <span className="text-sm font-medium text-slate-300">Inline Display</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-4 h-4 rounded border-2 border-purple-500/60 bg-purple-500/20"></div>
                  <span className="text-sm font-medium text-slate-300">Artifact Display</span>
                </div>
              </div>
            </div>
          ) : (
            <div className="rounded-2xl border-2 border-dashed border-slate-600 bg-slate-900/50 p-12 text-center">
              <MousePointerClick className="h-12 w-12 text-slate-600 mx-auto mb-4" />
              <p className="text-base font-medium text-slate-400">No UI interactions defined for this workflow</p>
            </div>
          )}
        </div>
      )}

      {/* Workflow Tab - Lifecycle hooks + Phase details */}
      {activeTab === 'workflow' && (
        <div className="space-y-8">
          {/* Workflow Description */}
          {safeWorkflow?.description && (
            <div className="rounded-lg bg-slate-800/70 p-5 border-l-4 border-[var(--color-primary-light)]">
              <p className="text-base leading-relaxed text-slate-200">{String(safeWorkflow.description)}</p>
            </div>
          )}
          
          {/* Setup Hooks (before_chat) */}
          <WorkflowLifecycleSection operations={chatLevelHooks.before_chat} type="before_chat" />

          {/* Phases Section */}
          <div className="space-y-6">
            <div className="flex items-center gap-3 rounded-lg bg-slate-800 px-6 py-4 border-l-4 border-[var(--color-primary-light)]">
              <Layers className="h-6 w-6 text-[var(--color-primary-light)]" />
              <span className="text-xl font-black uppercase tracking-wider text-white">Execution Phases</span>
            </div>
            
            {phases.length === 0 && (
              <div className="rounded-2xl border-2 border-dashed border-slate-600 bg-slate-900/50 p-12 text-center">
                <p className="text-base font-medium text-slate-400">No phases defined. Ask the ActionPlanArchitect to generate at least one phase.</p>
              </div>
            )}
            
            <div className="space-y-5">
              {phases.map((phase, idx) => (
                <PhaseAccordion
                  key={idx}
                  phase={phase}
                  index={idx}
                  open={!!openPhases[idx]}
                  onToggle={() => togglePhase(idx)}
                  lifecycleOperations={lifecycleOperations}
                />
              ))}
            </div>
          </div>

          {/* Teardown Hooks (after_chat) */}
          <WorkflowLifecycleSection operations={chatLevelHooks.after_chat} type="after_chat" />
        </div>
      )}

      {/* Diagram Tab - Mermaid visualization */}
      {activeTab === 'diagram' && (
        <MermaidPreview chart={mermaidChart} pendingMessage={mermaidMessage} pattern={safeWorkflow?.pattern} />
      )}
    </div>
  );
};

ActionPlan.displayName = 'ActionPlan';
export default ActionPlan;


