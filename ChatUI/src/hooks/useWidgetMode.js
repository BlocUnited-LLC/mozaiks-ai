import { useEffect } from 'react';
import { useChatUI } from '../context/ChatUIContext';

/**
 * Hook to enable widget mode for any page outside of ChatPage.
 *
 * Widget mode shows the chat interface as a floating persistent widget
 * and allows users to return to their active workflow via the 🧠 brain toggle.
 *
 * Usage:
 * ```javascript
 * function MyNewPage() {
 *   useWidgetMode();
 *   return <div>My page content</div>;
 * }
 * ```
 *
 * When the user is in Ask mode and clicks the 🧠 brain icon:
 * - Navigates back to /chat
 * - Fetches the oldest IN_PROGRESS workflow
 * - Switches to workflow mode
 * - Resumes the workflow conversation
 */
export function useWidgetMode() {
  const {
    isInWidgetMode,
    setIsInWidgetMode,
    layoutMode,
    setPreviousLayoutMode
  } = useChatUI();

  useEffect(() => {
    // Enter widget mode when component mounts
    if (!isInWidgetMode) {
      console.log('🔍 [WIDGET_MODE] Entering widget mode (persistent chat on non-ChatPage route)');
      setPreviousLayoutMode(layoutMode);
      setIsInWidgetMode(true);
    }

    // DO NOT exit widget mode on unmount - this would clear the flag during navigation
    // ChatPage will handle clearing isInWidgetMode after it processes the return from widget mode
    // return () => {
    //   console.log('🔍 [WIDGET_MODE] Exiting widget mode');
    //   setIsInWidgetMode(false);
    // };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  // Note: Empty deps intentional - only run on mount

  return { isInWidgetMode };
}
