function ChatMessageComponent({ message, message_from, agentName }) {
  console.log('💬 ChatMessageComponent render:', { message: message?.substring(0, 50) + '...', message_from, agentName, hasMessage: !!message });
 
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
export default ChatMessageComponent;
