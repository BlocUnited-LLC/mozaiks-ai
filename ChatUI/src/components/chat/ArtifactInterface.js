import React from 'react';

const ArtifactInterface = ({ onClose }) => {
  return (
    <div className="flex flex-col w-full md:w-1/2 px-4 transition-all duration-500 ease-in-out">
      <div className="flex flex-col h-full rounded-2xl border border-cyan-400/30 overflow-hidden shadow-2xl bg-gradient-to-br from-white/5 to-cyan-500/5 backdrop-blur-sm cosmic-ui-module animate-in slide-in-from-right">
        {/* Artifact Header */}
        <div className="flex-shrink-0 px-4 py-3 border-b border-cyan-400/20 bg-gradient-to-r from-cyan-500/5 to-purple-500/5 backdrop-blur-xl shadow-lg rounded-2xl mx-2 mt-2 mb-1 min-h-[80px]">
          <div className="flex items-center justify-between h-full">
            <div className="flex-1">
              <div className="cosmic-module-header">
                <span className="text-cyan-300">🎨</span>
                Artifact Canvas
              </div>
            </div>
            <div className="flex flex-col items-end gap-2">
              <button 
                onClick={onClose}
                className="group relative p-3 rounded-lg bg-gradient-to-r from-cyan-500/10 to-purple-500/10 border border-cyan-400/20 hover:border-cyan-400/40 transition-all duration-300 backdrop-blur-sm"
                title="Close Artifact Canvas"
              >
                <svg className="w-5 h-5 group-hover:rotate-90 transition-transform duration-300 text-white group-hover:text-cyan-100" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
                <div className="absolute inset-0 bg-cyan-400/10 rounded-lg blur opacity-0 group-hover:opacity-100 transition-opacity duration-300 -z-10"></div>
              </button>
            </div>
          </div>
        </div>
        
        {/* Artifact Content Area - ONLY THIS SCROLLS */}
        <div className="flex-1 relative overflow-hidden">
          <div 
            className="absolute inset-0 overflow-y-auto p-6 space-y-4 my-scroll1"
          >
            {/* Welcome State */}
            <div className="text-center space-y-6 mt-8">
              <div className="flex items-center justify-center h-full min-h-[400px]">
                <div className="w-32 h-32 bg-gradient-to-br from-cyan-500/10 to-purple-500/10 rounded-2xl border border-cyan-400/30 flex items-center justify-center backdrop-blur-sm shadow-lg">
                  <img 
                    src="/mozaik_logo.svg" 
                    alt="Mozaik Logo" 
                    className="w-16 h-16 opacity-60"
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ArtifactInterface;
