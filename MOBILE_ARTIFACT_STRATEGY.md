# Mobile Artifact Handling Strategy

## Problem Statement
On mobile devices, the split-screen layout (50% chat / 50% artifact) is unusable. When agents automatically render artifacts during a conversation, the current system forces a split view that doesn't work on small screens.

## Current State Analysis

### Desktop Flow (Works Well)
1. Agent sends `tool_call` event with `display: 'artifact'`
2. `simple_transport.py` identifies artifact via `display_type`
3. Frontend auto-opens split view (50/50)
4. User can toggle between full chat, split, and minimized

### Mobile Flow (Broken)
1. Same backend event triggers split view
2. Split view renders two tiny panels (unusable)
3. `forceOverlay` mode exists but shows full-screen modal (loses chat context)
4. User loses conversational flow when viewing artifact

## Proposed Solution: Mobile-First Artifact Tabs

### Design Concept
Instead of split-screen on mobile, use a **tabbed interface** that allows quick switching between chat and artifact views while maintaining context.

```
┌─────────────────────┐
│  [Chat] [Artifact]  │  ← Tab bar
├─────────────────────┤
│                     │
│   Active View       │  ← Either chat or artifact (full width)
│   (Chat/Artifact)   │
│                     │
└─────────────────────┘
```

### Implementation Strategy

#### 1. Detection Layer (Backend - No Changes Needed)
- `simple_transport.py` already identifies artifacts correctly
- Events with `display: 'artifact'` or `display_type: 'artifact'` work as-is
- Auto-tool handler already emits proper event structure

#### 2. Response Layer (Frontend - New Mobile Layout)

**New State in ChatPage.js:**
```javascript
const [mobileArtifactTab, setMobileArtifactTab] = useState('chat'); // 'chat' | 'artifact'
const [isMobileView, setIsMobileView] = useState(false);
```

**Mobile Detection:**
```javascript
useEffect(() => {
  const compute = () => {
    const isMobile = window.innerWidth < 768; // md breakpoint
    setIsMobileView(isMobile);
    
    // On mobile, force tab mode instead of split/overlay
    if (isMobile && layoutMode === 'split') {
      setLayoutMode('full'); // Use full layout with tabs
    }
  };
  compute();
  window.addEventListener('resize', compute);
  return () => window.removeEventListener('resize', compute);
}, []);
```

**Artifact Event Handler (Modified):**
```javascript
// In ChatPage.js message handler
if (displayMode === 'artifact') {
  if (isMobileView) {
    // On mobile: switch to artifact tab + show notification badge
    setMobileArtifactTab('artifact');
    setIsSidePanelOpen(true);
  } else {
    // Desktop: open split view as usual
    setLayoutMode('split');
    setIsSidePanelOpen(true);
  }
}
```

#### 3. UI Components

**MobileArtifactTabs.js (New Component):**
```javascript
const MobileArtifactTabs = ({ 
  activeTab, 
  onTabChange, 
  hasArtifact, 
  chatContent, 
  artifactContent,
  hasUnseenArtifact = false 
}) => {
  return (
    <div className="flex flex-col h-full">
      {/* Tab Bar */}
      <div className="flex border-b border-gray-700 bg-gray-900/50 backdrop-blur-sm">
        <button
          onClick={() => onTabChange('chat')}
          className={`flex-1 px-4 py-3 text-sm font-medium transition-all ${
            activeTab === 'chat'
              ? 'text-white border-b-2 border-[var(--color-primary)]'
              : 'text-gray-400 hover:text-gray-300'
          }`}
        >
          Chat
        </button>
        
        <button
          onClick={() => onTabChange('artifact')}
          disabled={!hasArtifact}
          className={`relative flex-1 px-4 py-3 text-sm font-medium transition-all ${
            activeTab === 'artifact'
              ? 'text-white border-b-2 border-[var(--color-primary)]'
              : hasArtifact
              ? 'text-gray-400 hover:text-gray-300'
              : 'text-gray-600 cursor-not-allowed'
          }`}
        >
          Artifact
          {hasUnseenArtifact && (
            <span className="absolute top-2 right-2 w-2 h-2 bg-[var(--color-error)] rounded-full animate-pulse" />
          )}
        </button>
      </div>
      
      {/* Content Area */}
      <div className="flex-1 min-h-0 overflow-hidden">
        {activeTab === 'chat' ? chatContent : artifactContent}
      </div>
    </div>
  );
};
```

**Integration in ChatPage.js:**
```javascript
return (
  <div className="flex flex-col h-screen overflow-hidden relative">
    <Header {...headerProps} />
    
    <div className="flex-1 flex flex-col min-h-0 overflow-hidden pt-16 sm:pt-20 md:pt-16">
      {workflowCompleted ? (
        <WorkflowCompletion {...completionProps} />
      ) : (
        <>
          {/* Desktop: Use existing FluidChatLayout */}
          {!isMobileView && (
            <FluidChatLayout
              layoutMode={layoutMode}
              onLayoutChange={setLayoutMode}
              chatContent={chatInterface}
              artifactContent={<ArtifactPanel {...artifactProps} />}
              {...layoutProps}
            />
          )}
          
          {/* Mobile: Use tabbed interface */}
          {isMobileView && (
            <MobileArtifactTabs
              activeTab={mobileArtifactTab}
              onTabChange={setMobileArtifactTab}
              hasArtifact={isSidePanelOpen}
              chatContent={chatInterface}
              artifactContent={<ArtifactPanel {...artifactProps} />}
              hasUnseenArtifact={lastArtifactEventRef.current !== null && mobileArtifactTab === 'chat'}
            />
          )}
        </>
      )}
    </div>
  </div>
);
```

### User Experience Flow

#### Scenario: Agent Generates Artifact During Chat (Mobile)

1. **User sends message**: "Create a dashboard"
2. **Agent responds**: "Creating your dashboard..."
3. **Backend emits**: `tool_call` event with `display: 'artifact'`
4. **Frontend detects**: Mobile view + artifact event
5. **UI switches**: Automatically switches to "Artifact" tab
6. **User sees**: Full-screen artifact (form, preview, etc.)
7. **Badge appears**: Red dot on "Chat" tab (conversation continued)
8. **User taps**: "Chat" tab to see agent's follow-up message
9. **Seamless switching**: Can toggle between chat and artifact as needed

### Advantages

✅ **Full Context**: Both chat and artifact available at full width
✅ **Automatic Handling**: Backend logic unchanged - frontend adapts
✅ **Clear State**: User knows exactly where they are (chat vs artifact)
✅ **No Lost Messages**: Chat tab shows badge when agent adds messages
✅ **Native Feel**: Tabs are familiar mobile UX pattern
✅ **Performance**: Only one view rendered at a time (better mobile performance)

### Edge Cases Handled

1. **Multiple Artifacts**: Most recent artifact shown; older ones in chat history
2. **Artifact Closes**: When artifact completes, user auto-returns to chat tab
3. **No Artifact Yet**: Artifact tab disabled/grayed out until first artifact appears
4. **Orientation Change**: Tabs work in both portrait and landscape
5. **Resume Session**: Restored artifact opens artifact tab automatically

### Backend Compatibility

**No changes required** to:
- `simple_transport.py` event emission
- `auto_tool_handler.py` tool invocation
- Event structure or payload format

**Frontend receives same events**, just renders differently based on screen size.

### Implementation Priority

1. **Phase 1** (MVP): Basic tab switching with artifact detection
2. **Phase 2**: Badge notifications for unseen content
3. **Phase 3**: Swipe gestures between tabs
4. **Phase 4**: Tab history (access previous artifacts)

### Alternative Approach: Bottom Sheet

If tabs don't feel right, an alternative is a **bottom sheet** (like Google Maps):

```
┌─────────────────────┐
│                     │
│   Chat Interface    │
│                     │
├─────────────────────┤
│  ↕ [Artifact]       │  ← Draggable handle
│  Preview content... │
└─────────────────────┘
```

- Artifact starts minimized at bottom
- User drags up to expand
- Maintains chat visibility at top
- More complex to implement but potentially more elegant

### Recommendation

**Start with tabs** - simpler, more predictable, easier to implement. Can add bottom sheet in v2 if user feedback requests it.

## Next Steps

1. Create `MobileArtifactTabs.js` component
2. Add mobile detection state to `ChatPage.js`
3. Update artifact event handler with mobile branching
4. Test with Generator workflow (creates artifacts automatically)
5. Add badge notification for unseen tab content
6. Test orientation changes and edge cases
