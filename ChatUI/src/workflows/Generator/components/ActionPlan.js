// ============================================================================
// FILE: ChatUI/src/workflows/Generator/components/ActionPlan.js
// REWRITE: Accordion-based Action Plan artifact (schema: { workflow:{...}, agent_message })
// PURPOSE: Present hierarchical workflow (phases -> agents -> tools) with robust, defensive parsing.
// ============================================================================

import React, { useState, useEffect, useRef } from 'react';
import { ChevronDown, ChevronRight, Layers, Plug, UserCheck, Bot, Sparkles, Zap, Activity, GitBranch, Cpu } from 'lucide-react';
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
  cron_schedule: { label: 'Scheduled', desc: 'Time-based trigger', color: 'violet' },
  webhook: { label: 'Webhook', desc: 'External HTTP POST', color: 'amber' },
  database_condition: { label: 'Database', desc: 'Database state trigger', color: 'blue' },
};

const INTERACTION_MODE = {
  autonomous: { label: 'Autonomous', desc: 'Fully automated execution', color: 'violet' },
  checkpoint_approval: { label: 'Checkpoint Approval', desc: 'Approval gates at specific agents', color: 'amber' },
  conversational: { label: 'Conversational', desc: 'Multi-turn dialogue with user', color: 'cyan' },
};

const SemanticChip = ({ value, mapping, icon: Icon = Sparkles, prefix }) => {
  const normalized = String(value || '').toLowerCase();
  const meta = mapping[normalized] || { label: 'Unknown', desc: 'Not specified', color: 'neutral' };
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

const ModelChip = ({ model }) => {
  const modelName = String(model || 'gpt-4o-mini');
  return (
    <span className={components.badge.neutral}>
      <Cpu className="h-3.5 w-3.5" /> Model: {modelName}
    </span>
  );
};

const ToolPill = ({ tool, idx, type = 'integration' }) => {
  const rawName = typeof tool === 'string' ? tool : tool?.name;
  const rawPurpose = typeof tool === 'string' ? null : tool?.purpose;
  const name = String(rawName || `Tool ${idx + 1}`);
  const purpose = rawPurpose && String(rawPurpose).trim() ? String(rawPurpose).trim() : null;

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

const normalizeStringList = (value) => (
  Array.isArray(value)
    ? value
        .filter((item) => typeof item === 'string' && item.trim().length > 0)
        .map((item) => item.trim())
    : []
);

const mapToolStrings = (items, purpose) =>
  items.map((name) => ({ name, purpose }));

const AgentAccordionRow = ({ agent, index, isOpen, onToggle }) => {
  const integrationNames = normalizeStringList(agent?.integrations);
  const operationNames = normalizeStringList(agent?.operations);
  const integrationTools = mapToolStrings(integrationNames, '');
  const operationTools = mapToolStrings(operationNames, '');
  const hasStructuredTools = integrationTools.length > 0 || operationTools.length > 0;
  const displayedToolCount = hasStructuredTools
    ? integrationTools.length + operationTools.length
    : 0;
  const hasTools = displayedToolCount > 0;
  
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
      badgeText: 'COLLECTS INPUT'
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
        className="flex w-full items-center gap-4 p-5 text-left transition-colors hover:bg-slate-750"
      >
        <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${isOpen ? 'bg-[var(--color-primary)]' : 'bg-slate-700'}`}>
          {isOpen ? (
            <ChevronDown className="h-5 w-5 text-white" />
          ) : (
            <ChevronRight className="h-5 w-5 text-slate-300" />
          )}
        </div>
        <div className="flex items-center gap-3">
          <div className={`rounded-lg p-2.5 ${config.bgClass}`}>
            <Icon className={`h-5 w-5 ${config.iconColor}`} />
          </div>
          <span className="text-lg font-bold text-white">
            {String(agent?.name || `Agent ${index + 1}`)}
          </span>
        </div>
        {interactionType !== 'none' && (
          <span className={`ml-auto rounded-lg px-4 py-2 text-sm font-bold ${config.badgeClass}`}>
            {config.badgeText}
          </span>
        )}
      </button>
      {isOpen && (
        <div className="space-y-5 border-t-2 border-[rgba(var(--color-primary-light-rgb),0.3)] bg-slate-900/80 p-6">
          <div className="rounded-lg bg-slate-800/50 p-4 border-l-4 border-[var(--color-primary-light)]">
            <p className="text-sm leading-relaxed text-slate-200">
              {String(agent?.description || 'No description provided.')}
            </p>
          </div>
          <div className="space-y-4">
            {operationTools.length > 0 && (
              <ToolSection title="Operations" icon={Activity} items={operationTools} type="operation" />
            )}
            {integrationTools.length > 0 && (
              <ToolSection title="Integrations" icon={Plug} items={integrationTools} type="integration" />
            )}
            {!hasTools && (
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

const PhaseAccordion = ({ phase, index, open, onToggle }) => {
  const agents = Array.isArray(phase?.agents) ? phase.agents : [];
  const [openAgents, setOpenAgents] = useState({});
  const toggleAgent = (i) => setOpenAgents(prev => ({ ...prev, [i]: !prev[i] }));
  
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
              {contextCount} Input {contextCount === 1 ? 'Point' : 'Points'}
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
              agents.map((agent, aIdx) => (
                <AgentAccordionRow
                  key={aIdx}
                  agent={agent}
                  index={aIdx}
                  isOpen={!!openAgents[aIdx]}
                  onToggle={() => toggleAgent(aIdx)}
                />
              ))
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
const MermaidPreview = ({ chart, pendingMessage }) => {
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
      </div>
      <div ref={ref} className="min-h-[400px] overflow-auto bg-slate-850 p-8" />
    </div>
  );
};

const ActionPlan = ({ payload = {}, onResponse, ui_tool_id, eventId, workflowName, componentId = 'ActionPlan' }) => {
  // CRITICAL: All hooks MUST be called before any conditional returns (React rules of hooks)
  // Initialize state first
  const [pending, setPending] = useState(false);
  const [openPhases, setOpenPhases] = useState({ 0: true });
  
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
      triggerType: typeof workflow?.trigger
    });
  } catch (e) {
    console.error('🎨 [ActionPlan] Error logging resolved workflow:', e);
  }

  const safeWorkflow = (workflow && typeof workflow === 'object' && !Array.isArray(workflow)) ? workflow : {};
  const phases = Array.isArray(safeWorkflow?.phases) ? safeWorkflow.phases : [];

  // agent_message intentionally ignored inside artifact to avoid duplicate display in chat; previously parsed here.
  // (If future logic needs it for analytics, reintroduce as const agentMessage = String(payload?.agent_message || '') and use.)

  // Derived counts (computed; not part of schema)
  const agentCount = phases.reduce((acc, p) => acc + (Array.isArray(p?.agents) ? p.agents.length : 0), 0);
  
  // Tool count: deduplicate integrations across all agents (same integration used multiple times = 1 tool)
  const uniqueIntegrations = new Set();
  phases.forEach(phase => {
    if (Array.isArray(phase?.agents)) {
      phase.agents.forEach(agent => {
        const integrations = normalizeStringList(agent?.integrations);
        integrations.forEach(integration => uniqueIntegrations.add(integration));
      });
    }
  });
  const toolCount = uniqueIntegrations.size;

  const normalizeDiagram = (value) => (typeof value === 'string' ? value.trim() : '');
  const legacyDiagram = normalizeDiagram(payload?.legacy_mermaid_flow);
  const workflowDiagram = normalizeDiagram(safeWorkflow?.mermaid_flow);
  const mermaidChart = legacyDiagram || workflowDiagram;
  const mermaidMessage = legacyDiagram
    ? 'Legacy diagram supplied by the planner. A refreshed sequence diagram will be generated after approval.'
    : 'Approve the plan to generate a Mermaid sequence diagram.';

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

  return (
    <div className={`min-h-screen space-y-8 rounded-2xl ${components.card.primary}`} data-agent-message-id={agentMessageId || undefined}>
      {/* Header Section */}
        <header className="space-y-6 rounded-2xl border-3 border-[var(--color-primary)] bg-gradient-to-br from-slate-900 to-slate-800 p-8 shadow-2xl [box-shadow:0_0_0_rgba(var(--color-primary-rgb),0.3)]">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3 text-sm font-black uppercase tracking-[0.3em] text-[var(--color-primary-light)]">
          <Sparkles className="h-5 w-5" />
          Workflow Blueprint
            </div>
            <div className="flex flex-col items-end gap-2 text-right">
          <button
            onClick={approve}
            disabled={pending}
            className={`${components.button.primary} text-sm shadow-lg [box-shadow:0_0_0_rgba(var(--color-primary-rgb),0.3)]`}
          >
            Approve Plan
          </button>
            </div>
          </div>
          
          <div className="space-y-5">
            <h1 className={`${typography.display.xl} ${colors.text.primary} drop-shadow-lg break-words max-w-full leading-tight overflow-hidden`}>
          {String(safeWorkflow?.name || 'Generated Workflow')}
            </h1>
            <div className="flex flex-wrap items-center gap-4">
          <SemanticChip value={safeWorkflow?.initiated_by} mapping={INITIATED_BY} prefix="Initiated By" />
          <SemanticChip value={safeWorkflow?.trigger_type} mapping={TRIGGER_TYPE} prefix="Trigger" />
          <SemanticChip value={safeWorkflow?.interaction_mode} mapping={INTERACTION_MODE} prefix="Mode" />
          <ModelChip model={safeWorkflow?.model} />
          <div className="flex items-center gap-3 rounded-lg border-2 border-slate-600 bg-slate-800 px-5 py-3 text-base font-bold text-white">
            <span className="text-2xl text-[var(--color-primary-light)]">{phases.length}</span> 
            <span className="text-slate-300">{phases.length === 1 ? 'Phase' : 'Phases'}</span>
            <span className="h-2 w-2 rounded-full bg-slate-500" />
            <span className="text-2xl text-[var(--color-primary-light)]">{agentCount}</span> 
            <span className="text-slate-300">{agentCount === 1 ? 'Agent' : 'Agents'}</span>
            <span className="h-2 w-2 rounded-full bg-slate-500" />
            <span className="text-2xl text-[var(--color-primary-light)]">{toolCount}</span> 
            <span className="text-slate-300">{toolCount === 1 ? 'Tool' : 'Tools'}</span>
          </div>
            </div>
            {safeWorkflow?.description && (
          <div className="rounded-lg bg-slate-800/70 p-5 border-l-4 border-[var(--color-primary-light)]">
            <p className="text-base leading-relaxed text-slate-200">{String(safeWorkflow.description)}</p>
          </div>
            )}
          </div>
        </header>

          {/* Flowchart Section - Full Width */}
    <MermaidPreview chart={mermaidChart} pendingMessage={mermaidMessage} />

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
            />
          ))}
        </div>
      </div>
    </div>
  );
};

ActionPlan.displayName = 'ActionPlan';
export default ActionPlan;
