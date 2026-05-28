import React, { useRef, useEffect } from "react";
import fileIcon from "../../assets/attachFile.png";
import sendBtn from "../../assets/send.svg";
import LoadingDots from "../LoadingDots";

const ChatInput = ({
  input,
  setInput,
  isLoading,
  onSend,
  onUpload,
  onEnter,
  isSessionLoading,
  isTestMode,
}) => {
  const textareaRef = useRef(null);

  // Auto-resize textarea based on content
  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px'; // Max height of 120px
    }
  }, [input]);

  const handleKeyDown = (e) => {
    if (e.key === "Enter") {
      if (e.shiftKey) {
        // Allow Shift+Enter for new line
        return;
      } else {
        // Prevent default Enter behavior and send message
        e.preventDefault();
        if (!isLoading && input.trim()) {
          onSend();
        }
      }
    }
  };

  return (
    <div className="chat-input-area">
      <div className="inp" style={{ minHeight: "50px" }}>
        <label htmlFor="fileInput">
          <img src={fileIcon} alt="file" className="fileAdd" />
          <input
            type="file"
            multiple
            id="fileInput"
            style={{ display: "none" }}
            onChange={onUpload}
            disabled={isLoading || isSessionLoading}
          />
        </label>
        <div
          className="input-wrapper"
          style={{
            position: "relative",
            width: "100%",
            minHeight: "40px",
          }}
        >
          <textarea
            ref={textareaRef}
            placeholder={
              isSessionLoading
                ? isTestMode 
                  ? "🧪 Switching test configurations..."
                  : "Please wait while we're connecting to the server..."
                : isLoading
                ? isTestMode
                  ? "🧪 Generating mock response..."
                  : "Please wait for the response..."
                : isTestMode
                ? "🧪 Send a test message (Shift+Enter for new line)"
                : "Send a message (Shift+Enter for new line)"
            }
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isSessionLoading}
            style={{
              opacity: isSessionLoading ? 0.5 : 1,
              width: "100%",
              minHeight: "40px",
              maxHeight: "120px",
              paddingLeft: "15px",
              paddingRight: "15px",
              paddingTop: "10px",
              paddingBottom: "10px",
              border: "none",
              outline: "none",
              resize: "none",
              fontFamily: "inherit",
              fontSize: "14px",
              lineHeight: "1.4",
              backgroundColor: "transparent",
              color: "inherit",
              overflow: "hidden",
              wordWrap: "break-word"
            }}
          />
          {isSessionLoading && (
            <div
              style={{
                position: "absolute",
                top: "50%",
                left: "50%",
                transform: "translate(-50%, -50%)",
                zIndex: 2,
                height: "20px",
                display: "flex",
                alignItems: "center",
              }}
            >
              <LoadingDots />
            </div>
          )}
        </div>
        <button
          className="send"
          onClick={onSend}
          disabled={input.trim() === "" || isLoading || isSessionLoading}
        >
          <img src={sendBtn} alt="send" />
        </button>
      </div>
    </div>
  );
};

export default ChatInput;
