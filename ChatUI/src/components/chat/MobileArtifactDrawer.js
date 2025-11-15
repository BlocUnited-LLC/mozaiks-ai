import React from 'react';

const MobileArtifactDrawer = ({
  state = 'hidden',
  onStateChange = () => {},
  onClose = () => {},
  artifactContent = null,
  hasArtifact = false,
  hasUnseenChat = false,
  hasUnseenArtifact = false
}) => {
  const isExpanded = state === 'expanded';
  const isHidden = state === 'hidden';
  const isPeek = !isExpanded && !isHidden;
  const heightClass = isExpanded ? 'h-[85vh]' : isHidden ? 'h-0' : 'h-20';

  const baseContainerClasses = 'relative w-full bg-[rgba(3,6,15,0.96)] backdrop-blur-2xl border border-[rgba(var(--color-primary-light-rgb),0.45)] shadow-[0_-12px_40px_rgba(2,6,23,0.65)] overflow-hidden transition-all duration-300 pointer-events-auto flex flex-col';
  const expandedShapeClasses = 'w-full rounded-none rounded-t-3xl';
  const peekShapeClasses = 'w-full rounded-[2rem] shadow-[0_22px_55px_rgba(2,6,23,0.7)] border-[rgba(var(--color-primary-light-rgb),0.6)]';
  const containerClasses = `${heightClass} ${baseContainerClasses} ${isExpanded ? expandedShapeClasses : ''} ${isPeek ? peekShapeClasses : ''}`;

  const handleToggle = () => {
    if (isExpanded) {
      onStateChange('peek');
    } else {
      onStateChange('expanded');
    }
  };

  const contentVisibilityClasses = state === 'expanded'
    ? 'opacity-100 pointer-events-auto'
    : state === 'hidden'
      ? 'opacity-0 pointer-events-none'
      : 'opacity-100 pointer-events-none';

  return (
    <div className="absolute inset-x-0 bottom-0 z-40 pointer-events-none">
      <div className={`${containerClasses}`}>
        <div className="absolute inset-x-0 bottom-0 h-[2px] bg-[var(--color-primary-light)]/60 blur-[1px] pointer-events-none"></div>
        <button
          type="button"
          onClick={handleToggle}
          className="flex items-center justify-between px-5 py-4 bg-transparent text-left"
        >
          <div className="flex items-center gap-3">
            <div className="w-11 h-11 rounded-2xl bg-gradient-to-br from-[var(--color-primary)] to-[var(--color-secondary)] flex items-center justify-center shadow-lg p-2">
              <img 
                src="/mozaik_logo.svg" 
                alt="Mozaiks" 
                className="w-full h-full object-contain"
                onError={(e) => {
                  e.currentTarget.onerror = null;
                  e.currentTarget.src = '/mozaik.png';
                }}
              />
            </div>
            <div>
              <p className="text-sm font-semibold text-white tracking-wide">Artifact Workspace</p>
              <p className="text-[11px] uppercase tracking-[0.2em] text-[rgba(255,255,255,0.55)]">
                {isExpanded ? 'Swipe down for chat' : 'Tap to expand'}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {hasUnseenChat && (
              <span className="px-3 py-1 rounded-full text-[11px] font-semibold bg-[rgba(var(--color-error-rgb),0.15)] text-[var(--color-error)] border border-[rgba(var(--color-error-rgb),0.4)]">
                Chat updated
              </span>
            )}
            {hasUnseenArtifact && !isExpanded && (
              <span className="w-2.5 h-2.5 rounded-full bg-[var(--color-secondary)] shadow-[0_0_12px_rgba(var(--color-secondary-rgb),0.8)]" />
            )}
            <span className={`inline-flex items-center justify-center rounded-full border border-white/15 text-white/80 text-sm w-10 h-10 transition-transform ${isExpanded ? 'rotate-180' : ''}`}>
              <svg
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={2.5}
                stroke="currentColor"
                className="w-5 h-5"
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
              </svg>
            </span>
          </div>
        </button>

        <div className={`flex-1 overflow-hidden transition-opacity duration-200 ${contentVisibilityClasses}`}>
          <div className="flex items-center justify-end px-5">
            <button
              type="button"
              onClick={onClose}
              className="text-xs uppercase tracking-[0.25em] text-white/60 hover:text-white transition-colors"
            >
              Close
            </button>
          </div>
          <div className="h-full overflow-y-auto px-2 sm:px-4 pb-6">
            {hasArtifact && artifactContent ? (
              <div className="h-full">{artifactContent}</div>
            ) : (
              <div className="h-full flex items-center justify-center text-center text-white/60 text-sm">
                Waiting for the agent to deliver an artifact…
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default MobileArtifactDrawer;
