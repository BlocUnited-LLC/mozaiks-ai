function ChatMessage({ message, message_from, agentName, isTokenMessage, isWarningMessage }) {
  console.log('💬 ChatMessage render:', { message: message?.substring(0, 50) + '...', message_from, agentName, hasMessage: !!message, isTokenMessage, isWarningMessage });
 
  // Special styling for token and warning messages
  const getSystemMessageStyles = () => {
    if (isTokenMessage) {
      return {
        container: "bg-gradient-to-r from-red-500/20 to-orange-500/20 border border-red-400/40",
        text: "text-red-200",
        icon: "💰"
      };
    }
    if (isWarningMessage) {
      return {
        container: "bg-gradient-to-r from-yellow-500/20 to-orange-500/20 border border-yellow-400/40",
        text: "text-yellow-200",
        icon: "⚠️"
      };
    }
    return null;
  };

  const systemStyles = getSystemMessageStyles();

  return (
    <>
      {message_from === "user" ? (
        <div className="flex justify-end mr-3">
          <div
            className="md:rounded-[10px] rounded-[10px] w-3/4 mt-[20px] leading-4 text-white techfont
          px-[15px] py-[10px] design-mission-message-receive"
          >
            <div className="flex flex-col ">
              <div className="text-xs text-cyan-200 mb-1 opacity-75">You</div>
              {message && <div className="sm:w-full flex pr-2 oxanium  md:text-[16px] font-bold text-[10px]  text-white">
                <div className="w-full">{message}</div>
              </div>}
              
            </div>
          </div>
        </div>
      ) : systemStyles ? (
        // Special styling for system messages (token/warning)
        <div className="flex justify-center mr-3">
          <div className={`md:rounded-[10px] rounded-[10px] w-4/5 mt-[20px] leading-4 techfont px-[15px] py-[10px] ${systemStyles.container}`}>
            <div className="flex flex-col">
              <div className={`text-xs mb-1 opacity-75 flex items-center gap-2 ${systemStyles.text}`}>
                <span>{systemStyles.icon}</span>
                <span>System Notice</span>
              </div>
              {message && (
                <div className={`sm:w-full flex pr-2 oxanium md:text-[16px] text-[10px] font-bold ${systemStyles.text}`}>
                  <div className="w-full">{message}</div>
                </div>
              )}
            </div>
          </div>
        </div>
      ) : (
        <div className="flex justify-start mr-3">
          {message && (<div
            className="md:rounded-[10px] rounded-[10px] w-3/4 mt-[20px] leading-4 text-white techfont  
                    px-[15px] py-[10px] design-mission-message-send"
          >
            <div className="flex  flex-col ">
              <div className="text-xs text-purple-200 mb-1 opacity-75">{agentName || 'Agent'}</div>
              <div className="w-full flex pr-2 oxanium  md:text-[16px] text-[10px] font-bold text-white">
                <div className="w-full">{message}</div>
              </div>
            </div>
          </div>)}
          
        </div>
      )}
    </>
  );
}
export default ChatMessage;
