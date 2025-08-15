import React, { useState, useRef, useEffect } from "react";
import "./header-styles.css";

const Header = ({ 
  user = null, 
  workflowName = null,
  onNotificationClick = () => {},
  onMyAppsClick = () => {},
  onDiscoverClick = () => {}
}) => {
  // Default user if none provided (for standalone mode)
  const defaultUser = {
    id: "56132",
    firstName: "John Doe",
    userPhoto: null
  };

  const currentUser = user || defaultUser;
  const [isProfileDropdownOpen, setIsProfileDropdownOpen] = useState(false);
  const [isNotificationDropdownOpen, setIsNotificationDropdownOpen] = useState(false);
  const [notificationCount, setNotificationCount] = useState(3); // TODO: Mock notification count
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [isScrolled, setIsScrolled] = useState(false);
  const dropdownRef = useRef(null);

  // Handle scroll effect for dynamic blur
  useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 10);
    };
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  // Mock notification count updates (can be replaced with real notification system)
  useEffect(() => {
    const interval = setInterval(() => {
      // Simulate notification count changes based on activity
      setNotificationCount(prev => Math.max(0, prev + Math.floor(Math.random() * 3) - 1));
    }, 30000); // Update every 30 seconds
    
    return () => clearInterval(interval);
  }, []);

  // Close dropdowns when clicking outside or pressing Escape
  useEffect(() => {
    const handleGlobalPointer = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        if (isProfileDropdownOpen) setIsProfileDropdownOpen(false);
      }
    };
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        if (isProfileDropdownOpen) setIsProfileDropdownOpen(false);
        if (isNotificationDropdownOpen) setIsNotificationDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleGlobalPointer);
    document.addEventListener('touchstart', handleGlobalPointer, { passive: true });
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handleGlobalPointer);
      document.removeEventListener('touchstart', handleGlobalPointer);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isProfileDropdownOpen, isNotificationDropdownOpen]);

  const toggleProfileDropdown = () => {
    setIsProfileDropdownOpen(!isProfileDropdownOpen);
    if (isNotificationDropdownOpen) {
      setIsNotificationDropdownOpen(false);
    }
  };

  const toggleNotificationDropdown = () => {
    setIsNotificationDropdownOpen(!isNotificationDropdownOpen);
    if (isProfileDropdownOpen) {
      setIsProfileDropdownOpen(false);
    }
    onNotificationClick();
  };

  const handleMyAppsClick = () => {
    onMyAppsClick();
  };

  const handleDiscoverClick = () => {
    onDiscoverClick();
  };

  const toggleMobileMenu = () => setMobileMenuOpen(v => !v);

  return (
    <header className={`
      fixed top-0 left-0 right-0 z-50 transition-all duration-300 
      ${isScrolled ? 'backdrop-blur-xl bg-black/30' : 'backdrop-blur-lg bg-black/20'}
      border-b border-cyan-500/15 shadow-lg shadow-cyan-500/5
    `}>
      {/* Enhanced geometric overlay */}
      <div className="absolute inset-0 bg-gradient-to-r from-black/40 via-blue-900/10 to-black/40"></div>
      <div className="absolute inset-0 bg-gradient-to-b from-transparent via-cyan-900/5 to-transparent"></div>
      
      {/* Subtle scan line effect */}
      <div 
        className="absolute top-0 left-0 w-full h-px bg-gradient-to-r from-transparent via-cyan-400/30 to-transparent"
        style={{ animation: 'geometric-scan 4s ease-in-out infinite' }}
      ></div>
      
      {/* Main header content */}
      <div className="relative h-16 flex items-center justify-between px-6 lg:px-8">
        
        {/* LEFT SECTION - Mission Control Branding */}
  <div className="flex flex-col items-start space-y-1">
          {/* Top Row: Logo + Brand */}
          <div className="flex items-center space-x-3">
            <a 
              href="https://mozaiks.ai"
              target="_blank"
              rel="noopener noreferrer"
              className="relative flex items-center space-x-2 group"
            >
              <img 
                src="/mozaik_logo.svg" 
                className="h-7 w-7 transition-transform duration-300 group-hover:scale-110" 
                alt="Mozaiks logo" 
              />
              <img 
                src="/mozaik.png" 
                className="h-7" 
                alt="Mozaiks brand" 
              />
              <div className="absolute inset-0 bg-cyan-400/10 rounded-lg blur-lg opacity-0 group-hover:opacity-100 transition-opacity duration-300 -z-10"></div>
            </a>
          </div>
          
          {/* Bottom Row: Mission Breadcrumbs */}
          <div className="hidden md:flex items-center space-x-2 text-xs text-cyan-400/70 mt-1 ml-2">
            <button 
              onClick={handleMyAppsClick}
              className="flex items-center space-x-1 hover:text-cyan-300 transition-colors duration-200 group"
            >
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
              <span className="oxanium">My Workflows</span>
            </button>
            
            <svg className="w-3 h-3 text-cyan-500/50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
            
            <span className="oxanium text-cyan-200 font-medium">
              {workflowName ? workflowName.charAt(0).toUpperCase() + workflowName.slice(1) : 'Command Center Interface'}
            </span>
          </div>
        </div>

        {/* CENTER SECTION - Removed phase status (now handled in chat interface) */}
        <div className="hidden lg:flex items-center justify-center">
          {/* Center space reserved for future features */}
        </div>

  {/* RIGHT SECTION - Command Console Cluster */}
  <div className="flex items-center space-x-1">
          
          {/* Command Cluster Container */}
          <div className="flex items-center bg-white/5 border border-cyan-400/30 rounded-2xl backdrop-blur-md p-1 space-x-2">
            {/* User Identity Pod - moved to left */}
            <div className="relative" ref={dropdownRef}>
              <button
                onClick={toggleProfileDropdown}
                className="group flex items-center space-x-2 p-2 rounded-xl hover:bg-cyan-400/10 transition-all duration-300"
                title="Command Profile"
              >
                <div className="relative">
                  <div className="w-7 h-7 rounded-full overflow-hidden border border-cyan-400/40 group-hover:border-cyan-400/70 transition-colors duration-300">
                    {currentUser.userPhoto ? (
                      <img src={currentUser.userPhoto} alt="User" className="w-full h-full object-cover" />
                    ) : (
                      <img src="/profile.png" alt="profileicon" className="w-full h-full object-cover" />
                    )}
                  </div>
                  <div className="absolute -bottom-0.5 -right-0.5 w-3 h-3 bg-green-400 rounded-full border border-slate-900 shadow-sm"></div>
                </div>
                <div className="hidden lg:block text-left">
                  <div className="text-cyan-200 text-xs font-medium oxanium">
                    {currentUser.firstName || 'Commander'}
                  </div>
                </div>
                <svg className="w-3 h-3 text-cyan-400/60 group-hover:text-cyan-300 transition-colors duration-300" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                </svg>
                <div className="absolute inset-0 bg-cyan-400/20 rounded-xl blur opacity-0 group-hover:opacity-100 transition-opacity duration-300 -z-10"></div>
              </button>
              {/* Enhanced Command Profile Dropdown */}
              {isProfileDropdownOpen && (
                <div className="absolute right-0 top-full mt-2 w-64 bg-slate-900/95 border border-cyan-400/50 rounded-2xl backdrop-blur-xl shadow-2xl shadow-cyan-500/20 overflow-hidden z-50">
                  <div className="absolute inset-0 bg-gradient-to-br from-cyan-900/20 to-blue-900/15"></div>
                  {/* Profile Header */}
                  <div className="relative p-4 border-b border-cyan-400/20">
                    <div className="flex items-center space-x-3">
                      <div className="relative">
                        <div className="w-12 h-12 rounded-full overflow-hidden border-2 border-cyan-400/50">
                          {currentUser.userPhoto ? (
                            <img src={currentUser.userPhoto} alt="User" className="w-full h-full object-cover" />
                          ) : (
                            <img src="/profile.png" alt="profileicon" className="w-full h-full object-cover" />
                          )}
                        </div>
                        <div className="absolute -bottom-1 -right-1 w-4 h-4 bg-green-400 rounded-full border-2 border-slate-900"></div>
                      </div>
                      <div>
                        <div className="text-cyan-100 font-semibold oxanium">{currentUser.firstName || 'Commander'}</div>
                        <div className="text-cyan-400/70 text-xs oxanium">Mission Control</div>
                      </div>
                    </div>
                  </div>
                  {/* Menu Items */}
                  <div className="relative p-2">
                    <button
                      className="w-full px-3 py-2.5 text-left text-cyan-100 hover:bg-cyan-400/10 rounded-xl transition-colors duration-200 flex items-center space-x-3 group"
                      onClick={() => console.log('Navigate to profile')}
                    >
                      <svg className="w-4 h-4 text-cyan-400 group-hover:text-cyan-300" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                      </svg>
                      <span className="oxanium text-sm">Profile Settings</span>
                    </button>
                    <button
                      className="w-full px-3 py-2.5 text-left text-cyan-100 hover:bg-cyan-400/10 rounded-xl transition-colors duration-200 flex items-center space-x-3 group"
                      onClick={() => console.log('Navigate to preferences')}
                    >
                      <svg className="w-4 h-4 text-cyan-400 group-hover:text-cyan-300" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                        <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                      </svg>
                      <span className="oxanium text-sm">Preferences</span>
                    </button>
                    <div className="border-t border-cyan-400/20 mt-2 pt-2">
                      <button
                        onClick={() => console.log('Logout')}
                        className="w-full px-3 py-2.5 text-left text-red-400 hover:bg-red-500/10 rounded-xl transition-colors duration-200 flex items-center space-x-3 group"
                      >
                        <svg className="w-4 h-4 group-hover:text-red-300" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                        </svg>
                        <span className="oxanium text-sm">Sign Out</span>
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
            
            {/* Notifications Pod */}
            <button
              onClick={toggleNotificationDropdown}
              className="group relative p-2.5 rounded-xl hover:bg-cyan-400/10 transition-all duration-300"
              title="Mission Alerts"
            >
              <svg
                className="w-6 h-6 text-cyan-400 group-hover:text-cyan-200 transition-colors duration-300"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
                strokeWidth={1.8}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0" />
              </svg>
              {/* Alert Indicator */}
              {notificationCount > 0 && (
                <div className="absolute -top-0.5 -right-0.5">
                  <div className="w-4 h-4 bg-gradient-to-br from-red-400 to-pink-500 rounded-full flex items-center justify-center border border-slate-900/60 shadow-lg">
                    <span className="text-white text-[10px] font-bold oxanium">{notificationCount}</span>
                  </div>
                  <div className="absolute inset-0 w-4 h-4 bg-red-500/40 rounded-full animate-ping"></div>
                </div>
              )}
              <div className="absolute inset-0 bg-cyan-400/20 rounded-xl blur opacity-0 group-hover:opacity-100 transition-opacity duration-300 -z-10"></div>
            </button>
            {/* Discovery Pod - toned down for visual harmony */}
            <button
              onClick={handleDiscoverClick}
              className="hidden md:flex items-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-r from-slate-900/80 via-cyan-900/60 to-slate-900/80 border border-cyan-400/40 text-cyan-100 font-semibold oxanium hover:bg-cyan-400/10 hover:border-cyan-300/80 transition-all duration-200 text-base tracking-wide shadow focus:outline-none focus:ring-2 focus:ring-cyan-300"
              style={{ boxShadow: '0 2px 12px 0 rgba(0,255,255,0.10)' }}
              title="Discover New Features"
            >
              <svg className="w-5 h-5 text-cyan-300 mr-1 drop-shadow-[0_0_4px_rgba(34,211,238,0.5)]" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v2m0 14v2m9-9h-2M5 12H3m15.364-6.364l-1.414 1.414M6.343 17.657l-1.414 1.414m12.728 0l-1.414-1.414M6.343 6.343L4.929 4.929" />
                <circle cx="12" cy="12" r="5" stroke="currentColor" strokeWidth="2" />
              </svg>
              <span className="font-semibold text-cyan-100 drop-shadow-[0_0_4px_rgba(34,211,238,0.3)]">Discover</span>
            </button>
            {/* Mobile discover icon inside the same rounded cluster */}
            <button
              onClick={handleDiscoverClick}
              className="md:hidden p-2 rounded-xl bg-white/5 border border-cyan-400/30 text-cyan-100 hover:bg-cyan-400/10 transition-all duration-200"
              title="Discover"
            >
              <svg className="w-5 h-5 text-cyan-300" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v2m0 14v2m9-9h-2M5 12H3m15.364-6.364l-1.414 1.414M6.343 17.657l-1.414 1.414m12.728 0l-1.414-1.414M6.343 6.343L4.929 4.929" />
                <circle cx="12" cy="12" r="5" stroke="currentColor" strokeWidth="2" />
              </svg>
            </button>
          </div>
        </div>
        
      </div>

      {/* Mobile Command Interface */}
      {/* Show only on small screens to avoid duplication with desktop breadcrumbs */}
      <div className="md:hidden px-4 pb-3">
        <div className="flex items-center justify-between gap-2">
          {/* Mobile Breadcrumb: My Workflows > {Workflow} */}
          <div className="flex items-center space-x-2 text-xs text-cyan-400/70">
            <button 
              onClick={handleMyAppsClick}
              className="flex items-center space-x-1 hover:text-cyan-300 transition-colors duration-200"
            >
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
              <span className="oxanium">My Workflows</span>
            </button>

            <svg className="w-3 h-3 text-cyan-500/50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>

            <span className="oxanium text-cyan-200 font-medium">
              {workflowName ? workflowName.charAt(0).toUpperCase() + workflowName.slice(1) : 'Command Center Interface'}
            </span>
          </div>
        </div>
        {mobileMenuOpen && (
          <div className="mt-2 rounded-2xl border border-cyan-400/30 bg-white/5 backdrop-blur-md p-2 space-y-2">
            <button
              onClick={() => { handleDiscoverClick(); setMobileMenuOpen(false); }}
              className="w-full flex items-center gap-2 px-3 py-2 rounded-xl bg-gradient-to-r from-slate-900/80 via-cyan-900/60 to-slate-900/80 border border-cyan-400/40 text-cyan-100 font-semibold oxanium hover:bg-cyan-400/10 hover:border-cyan-300/80 transition-all duration-200 text-sm"
            >
              <svg className="w-5 h-5 text-cyan-300" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v2m0 14v2m9-9h-2M5 12H3m15.364-6.364l-1.414 1.414M6.343 17.657l-1.414 1.414m12.728 0l-1.414-1.414M6.343 6.343L4.929 4.929" />
                <circle cx="12" cy="12" r="5" stroke="currentColor" strokeWidth="2" />
              </svg>
              Discover
            </button>
            <button
              onClick={() => { toggleNotificationDropdown(); setMobileMenuOpen(false); }}
              className="w-full flex items-center gap-2 px-3 py-2 rounded-xl border border-cyan-400/30 text-cyan-100 hover:bg-cyan-400/10 transition-all duration-200 text-sm"
            >
              <svg
                className="w-5 h-5 text-cyan-300"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
                strokeWidth={1.8}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0" />
              </svg>
              Notifications
              {notificationCount > 0 && (
                <span className="ml-auto text-[10px] px-1.5 py-0.5 rounded-full bg-red-500/80">{notificationCount}</span>
              )}
            </button>
          </div>
        )}
      </div>
    </header>
  );
};

export default Header;
