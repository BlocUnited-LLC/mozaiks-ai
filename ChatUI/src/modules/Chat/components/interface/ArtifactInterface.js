import React from 'react';

const ArtifactInterface = ({ onClose }) => {
  return (
    <div className="flex flex-col w-full md:w-1/2 px-4 transition-all duration-500 ease-in-out">
      <div className="flex flex-col h-full rounded-2xl border border-cyan-400/30 overflow-hidden shadow-2xl bg-gradient-to-br from-white/5 to-cyan-500/5 backdrop-blur-sm cosmic-ui-module animate-in slide-in-from-right">
        {/* Artifact Header */}
        <div className="flex-shrink-0 px-4 py-3 border-b border-cyan-400/20 bg-gradient-to-r from-cyan-500/5 to-purple-500/5 backdrop-blur-xl shadow-lg rounded-2xl mx-2 mt-2 mb-1">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="w-2 h-2 bg-cyan-400 rounded-full animate-pulse"></div>
              <h3 className="text-cyan-100 font-bold oxanium text-xl tracking-wide">
                🎨 Artifact Canvas
              </h3>
              <div className="px-2 py-1 bg-cyan-500/20 border border-cyan-400/30 rounded-full">
                <span className="text-cyan-300 text-xs font-semibold oxanium">ACTIVE</span>
              </div>
            </div>
            <button 
              onClick={onClose}
              className="text-cyan-400 hover:text-cyan-300 transition-colors duration-200 p-2 rounded-lg hover:bg-cyan-400/10 group"
            >
              <svg className="w-5 h-5 group-hover:rotate-90 transition-transform duration-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          
          {/* Artifact Type Indicator */}
          <div className="mt-2 flex items-center space-x-2">
            <span className="text-cyan-400/70 text-sm oxanium">Ready for:</span>
            <div className="flex space-x-2">
              <span className="px-2 py-1 bg-purple-500/20 border border-purple-400/30 rounded text-purple-300 text-xs oxanium">Code</span>
              <span className="px-2 py-1 bg-fuchsia-500/20 border border-fuchsia-400/30 rounded text-fuchsia-300 text-xs oxanium">Data</span>
              <span className="px-2 py-1 bg-green-500/20 border border-green-400/30 rounded text-green-300 text-xs oxanium">Forms</span>
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
              <div className="w-16 h-16 mx-auto bg-gradient-to-br from-cyan-500/20 to-purple-500/20 rounded-full flex items-center justify-center border border-cyan-400/30">
                <svg className="w-8 h-8 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              </div>
              
              <div className="space-y-2">
                <h4 className="text-cyan-100 font-semibold text-lg oxanium">Dynamic Artifact Space</h4>
                <p className="text-cyan-300/70 text-sm max-w-sm mx-auto">
                  AI-generated content will appear here. Send a message to activate dynamic artifacts.
                </p>
              </div>
              
              {/* Feature Grid */}
              <div className="grid grid-cols-2 gap-4 mt-8 max-w-md mx-auto">
                <div className="p-4 bg-gradient-to-br from-cyan-500/10 to-blue-500/10 border border-cyan-400/20 rounded-lg">
                  <div className="w-8 h-8 mx-auto mb-2 text-cyan-400">
                    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
                    </svg>
                  </div>
                  <p className="text-cyan-300 text-xs oxanium font-semibold">Code Editor</p>
                </div>
                
                <div className="p-4 bg-gradient-to-br from-purple-500/10 to-fuchsia-500/10 border border-purple-400/20 rounded-lg">
                  <div className="w-8 h-8 mx-auto mb-2 text-purple-400">
                    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                    </svg>
                  </div>
                  <p className="text-purple-300 text-xs oxanium font-semibold">Data Viz</p>
                </div>
                
                <div className="p-4 bg-gradient-to-br from-green-500/10 to-emerald-500/10 border border-green-400/20 rounded-lg">
                  <div className="w-8 h-8 mx-auto mb-2 text-green-400">
                    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                  </div>
                  <p className="text-green-300 text-xs oxanium font-semibold">Forms</p>
                </div>
                
                <div className="p-4 bg-gradient-to-br from-orange-500/10 to-red-500/10 border border-orange-400/20 rounded-lg">
                  <div className="w-8 h-8 mx-auto mb-2 text-orange-400">
                    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2H5a2 2 0 00-2-2z" />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 5a2 2 0 012-2h4a2 2 0 012 2v2H8V5z" />
                    </svg>
                  </div>
                  <p className="text-orange-300 text-xs oxanium font-semibold">Tools</p>
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
