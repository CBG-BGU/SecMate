import { useState, useRef, useEffect } from "react";
import { Amplify } from "aws-amplify";
import axios from "axios";
import { ThemeProvider, createTheme } from "@aws-amplify/ui-react";
import { Authenticator } from "@aws-amplify/ui-react";
import awsExports from "./aws-exports";
import { Bell, HelpCircle } from "lucide-react";
import cbgLogo from "./assets/cbg.png";
import addBtn from "./assets/add-30.png";
import collapseIcon from "./assets/collapse-icon.png";
import expandIcon from "./assets/expand-icon.png";
import UserMenu from "./components/UserMenu";
import "@aws-amplify/ui-react/styles.css";
import "./App.css";
import "./custom-auth.css";
import TutorialBubble from "./components/TutorialBubble";
import { useAuth } from "./hooks/useAuth";
import { useSession } from "./hooks/useSession";
import { useChat } from "./hooks/useChat";
import { useTutorial } from "./hooks/useTutorial";
import { useRecommendations } from "./hooks/useRecommendations";
import { useExperiment } from "./hooks/useExperiment";
import ChatMessage from "./components/Chat/ChatMessage";
import ChatInput from "./components/Chat/ChatInput";
import LoadingIndicator from "./components/Chat/LoadingIndicator";
import { formatRecommendation } from "./utils/responseParser";

//fonts
import "@fontsource/roboto";
import "@fontsource/open-sans";
import "@fontsource/montserrat";
import "@fontsource/inter";

const ENABLE_AUTH = process.env.REACT_APP_ENABLE_AUTH !== "false";

if (ENABLE_AUTH) {
  Amplify.configure(awsExports);
}

function App( ) {
  
  const [isSendingMessage, setIsSendingMessage] = useState(false);
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false);
  const [currentFont, setCurrentFont] = useState("Arial, sans-serif");
  // const [currentFontSize, setCurrentFontSize] = useState("1rem"); // default size
  const [fontSizeClass, setFontSizeClass] = useState("font-size-normal"); // Default class
  const {
    experimentPhase,
    currentConfig,
    apiBaseUrl,
    beginExperiment,
    selectFirstExperimentConfig, // Add this
    selectNextConfig,
    isBaseline,
    canBeginExperiment,
    getCurrentMachineInfo,
    
    // Enhanced experiment features
    beginExperimentSafely,
    selectFirstExperimentConfigSafely,
    selectNextConfigSafely,
    incrementBaselineMessages,
    resetCurrentChatMessages,
    baselineMessageCount,
    currentChatMessageCount,
    isTransitioning,
    connectionStatus,
    transitionError,
    clearTransitionError,
    getExperimentProgress,
    canStartNewChat,
    
    // Test mode features
    isTestMode,
    toggleTestMode,
    generateMockResponse,
    testModeConnectionLog,
    
    // Reconnection features
    reconnectToCurrentConfig,
    isReconnecting,
    currentMachineIndex,
  } = useExperiment();
  const currentApiBaseUrl = apiBaseUrl;
  const { userName, userEmail, handleLogout, sendUserDataToApi } =
  useAuth(currentApiBaseUrl);
  const {
    userId,
    sessionToken,
    initiateSession,
    sessionInitiated,
    isFullyInitialized,
    setIsFullyInitialized,
  } = useSession(currentApiBaseUrl, isTestMode);
  const {
    messages,
    setMessages,
    input,
    setInput,
    isLoading,
    showDefaultOptions,
    setShowDefaultOptions,
    diagnosis,
    actionSteps,
    showNextButton,
    currentStepIndex,
    files,
    setFiles,
    currentLoadingPrompt,
    techLevels,
    setTechLevels,
    handleSendMsg,
    handleDefaultOption,
    sendMsgToOpenAI,
    msgEnd,
  } = useChat(sessionToken, currentApiBaseUrl, initiateSession, userId, incrementBaselineMessages, {
    isTestMode,
    generateMockResponse,
    currentConfig
  });

  const {
    showTutorial,
    setShowTutorial,
    tutorialStep,
    tutorialSteps,
    handleTutorialStepChange,
    handleTutorialComplete,
  } = useTutorial(setIsUserMenuOpen);

  const {
    recommendation,
    fetchRecommendation,
    checkConnectivity,
  } = useRecommendations(sessionToken, currentApiBaseUrl, isSendingMessage, isTestMode); //isloading?

  const handleFontChange = (newFont) => {
    setCurrentFont(newFont);
    document.body.style.fontFamily = newFont;
  };

  const handleFontSizeChange = (size) => {
      const sizeMap = {
          small: 'font-size-small',
          normal: 'font-size-normal',
          large: 'font-size-large',
      };
      setFontSizeClass(sizeMap[size] || 'font-size-normal');
  };

  useEffect(() => {
      document.body.classList.remove(
        "font-size-small",
        "font-size-normal",
        "font-size-large"
      );
      document.body.classList.add(fontSizeClass);
  }, [fontSizeClass]); // This effect runs whenever fontSizeClass changes

  const [currentStepIndices, setCurrentStepIndices] = useState({});
  const handleNextStep = (messageIndex) => {
    setCurrentStepIndices((prevIndices) => ({
      ...prevIndices,
      [messageIndex]: (prevIndices[messageIndex] || 0) + 1,
    }));
  };

  const handleFeedback = async (messageId, isPositive) => {
    if (!sessionToken) {
      console.error("No session token available");
      return;
    }

    // Skip API calls in test mode
    if (isTestMode) {
      console.log(`🧪 TEST MODE: Mock feedback submitted - ${isPositive ? 'Positive' : 'Negative'} for message ${messageId}`);
      return;
    }

    // Skip if apiBaseUrl is null or invalid
    if (!currentApiBaseUrl || currentApiBaseUrl === 'null') {
      console.warn("Invalid apiBaseUrl, skipping feedback submission");
      return;
    }

    try {
      await axios.post(
        `${currentApiBaseUrl}/submit_feedback`,
        { message_id: messageId, is_positive: isPositive },
        {
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${sessionToken}`,
          },
        }
      );
      console.log("Feedback submitted successfully");
    } catch (error) {
      console.error("Failed to submit feedback:", error);
      if (error.response && error.response.status === 401) {
        await initiateSession(userId);
      }
    }
  };

  // Handle recommendation detection from chat messages
  const handleRecommendationDetected = (recommendation) => {
    if (recommendation && recommendation.trim() !== '') {
      // Only update if it's a different recommendation to prevent flicker
      if (currentRecommendation !== recommendation) {
        setCurrentRecommendation(recommendation);
        setShowRecommendationNotification(true);
        
        console.log('💡 New recommendation detected:', recommendation);
      }
    }
  };



  const [hoveredMessageIndex, setHoveredMessageIndex] = useState(null);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const [isErrorModalOpen, setIsErrorModalOpen] = useState(false);
  const [associatedCid, setAssociatedCid] = useState(null);
  const [currentRecommendation, setCurrentRecommendation] = useState(null);
  const [showRecommendationNotification, setShowRecommendationNotification] = useState(false);
  const [isRecommendationMinimized, setIsRecommendationMinimized] = useState(false);
  const chatMessagesRef = useRef(null);
  const checkAssociatedCid = async () => {
    try {
      // Skip API calls in test mode
      if (isTestMode) {
        console.log("🧪 TEST MODE: Skipping CID check");
        setAssociatedCid("mock-cc-id-test");
        return;
      }

      // Skip if apiBaseUrl is null or invalid
      if (!currentApiBaseUrl || currentApiBaseUrl === 'null') {
        console.warn("Invalid apiBaseUrl, skipping CID check");
        setAssociatedCid(null);
        return;
      }

      const response = await axios.get(`${currentApiBaseUrl}/get_associated_cid`, {
        headers: {
          Authorization: `Bearer ${sessionToken}`,
          "Content-Type": "application/json",
        },
      });
      const ccId = response.data.message.cc_id;
      setAssociatedCid(ccId);
    } catch (error) {
      console.error("Failed to check associated CID:", error);
      setAssociatedCid(null);
    }
  };

  useEffect(() => {
    const sendData = async () => {
      if (userEmail && sessionToken && userId) {
        // Skip API calls in test mode
        if (isTestMode) {
          console.log("🧪 TEST MODE: Skipping user data API call");
          return;
        }

        try {
          await sendUserDataToApi(userEmail, sessionToken, userId);
        } catch (error) {
          if (error.response?.status === 401) {
            await initiateSession(userId);
            await sendUserDataToApi(userEmail, sessionToken, userId);
          }
        }
      }
    };

    sendData();
  }, [userEmail, sessionToken, userId, isTestMode]);

  useEffect(() => {
    if (sessionToken) {
      checkAssociatedCid();
    }
  }, [sessionToken, currentApiBaseUrl]);

  /**
   * Sends a message to the OpenAI API and returns the response.
   * @param {string} msg - The message to send to the OpenAI API.
   * @returns {Promise<string>} - The response from the OpenAI API.
   */

  useEffect(() => {
    msgEnd.current.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleEnter = async (e) => {
    if (e.key === "Enter") await handleSendMsg();
  };

  useEffect(() => {
    const clearConversationHistory = async () => {
      if (!sessionToken || !sessionInitiated.current) return;

      // Skip API calls in test mode
      if (isTestMode) {
        console.log("🧪 TEST MODE: Skipping conversation history clear");
        setIsFullyInitialized(true);
        return;
      }

      // Skip if apiBaseUrl is null or invalid
      if (!currentApiBaseUrl || currentApiBaseUrl === 'null') {
        console.warn("Invalid apiBaseUrl, skipping conversation history clear");
        setIsFullyInitialized(true); // Set as initialized anyway in test scenarios
        return;
      }

      try {
        console.log("🗑️ Clearing conversation history on:", currentApiBaseUrl);
        const response = await axios.post(
          `${currentApiBaseUrl}/clear_history_gen`,
          {},
          {
            headers: {
              "Content-Type": "application/json",
              Authorization: `Bearer ${sessionToken}`,
            },
            timeout: 10000 // 10 second timeout
          }
        );
        console.log("✅ Conversation history cleared", response.data);
        setIsFullyInitialized(true);
      } catch (error) {
        console.error("❌ Failed to clear conversation history:", error);
        
        if (error.response && error.response.status === 401) {
          console.error("🔐 Authentication failed. Attempting to refresh session...");
          sessionInitiated.current = false;
          setIsFullyInitialized(false);
          try {
            await initiateSession(userId);
          } catch (sessionError) {
            console.error("❌ Session refresh also failed, force unlocking input");
            setIsFullyInitialized(true); // Force unlock to prevent permanent lock
          }
        } else {
          // For other errors, still unlock the input after a delay
          console.warn("⚠️ Unlocking input despite history clear failure");
          setTimeout(() => {
            setIsFullyInitialized(true);
          }, 2000);
        }
      }
    };

    if (sessionToken && sessionInitiated.current) {
      clearConversationHistory();
    }
  }, [sessionToken, userId, currentApiBaseUrl, isTestMode, initiateSession, setIsFullyInitialized]);

  const CustomHeader = () => (
    <div>
      <img
        src={cbgLogo}
        alt="Security Advisor"
        className="security-advisor-image"
      />
    </div>
  );

  const AuthGate = ({ children }) => {
    if (!ENABLE_AUTH) {
      return children({
        signOut: handleLogout,
        user: { username: userName || "example-user" },
      });
    }

    return (
      <Authenticator components={{ Header: CustomHeader }}>
        {children}
      </Authenticator>
    );
  };

  // Sidebar collapse
  const toggleSidebar = () => {
    setIsSidebarCollapsed(!isSidebarCollapsed);
  };

  const theme = createTheme({
    name: "custom-theme",
    tokens: {
      colors: {
        background: { primary: { value: "#2a2727" } },
        font: { primary: { value: "#ffffff" } },
      },
      components: {
        button: {
          fontWeight: { value: "600" },
          borderRadius: { value: "4px" },
        },
      },
      fonts: {
        default: {
          variable: { value: currentFont },
        },
      },
    },
  });

  // Handles sending a query from quick query buttons
  const handleQuery = async (e) => {
    const text = e.target.value;
    setInput("");
    setMessages([...messages, { text: text, isBot: false }]);
    const res = await sendMsgToOpenAI(text);
    setMessages([
      ...messages,
      { text: text, isBot: false },
      { text: res, isBot: true },
    ]);
  };

  // Handles file upload
  function handleUpload(e) {
    const file = e.target.files;
    const file_arr = [...files];
    if (file.length > 0) {
      const fd = new FormData();
      for (let i = 0; i < file.length; i++) {
        fd.append(`file${i + 1}`, file[i]);
        file_arr.push(file[i].name);
      }
      axios
        .post(`${currentApiBaseUrl}/upload`, fd)
        .then((res) => {
          console.log(res);
          setUploadError(""); // Reset error message on successful upload
          setIsErrorModalOpen(false);
          setFiles(file_arr);
        })
        .catch((err) => {
          console.error(err);
          setUploadError(
            "An error occurred during file upload. Please try again."
          );
          setIsErrorModalOpen(true);
        });
    }
  }



  // Enhanced handler functions with better error handling and connection testing
  const handleBeginExperiment = async () => {
    try {
      console.log('🚀 Beginning experiment...');
      
      // Clear any previous errors
      clearTransitionError();
      
      // Step 1: Safely transition to experiment phase
      const phaseSuccess = await beginExperimentSafely();
      if (!phaseSuccess) {
        return; // Error message already set by beginExperimentSafely
      }
      
      // Step 2: Select first random config with connection testing
      const firstConfig = await selectFirstExperimentConfigSafely();
      if (!firstConfig) {
        return; // Error message already set by selectFirstExperimentConfigSafely
      }
      
      console.log('🎯 Selected first experiment config:', firstConfig);
      
      // Step 3: Reset session state to force new session on new machine
      sessionInitiated.current = false;
      setIsFullyInitialized(false);
      
      // Step 4: Initiate new session on the selected machine with retry logic
      if (userId && firstConfig.needsNewSession) {
        console.log('🔗 Initiating session on new machine:', firstConfig.machine.id);
        
        // Add delay to ensure machine is ready
        await new Promise(resolve => setTimeout(resolve, 1000));
        
        try {
          await initiateSession(userId);
          console.log('✅ Session initiated successfully');
        } catch (sessionError) {
          console.error('❌ Session initiation failed:', sessionError);
          alert('Failed to establish connection with the experiment server. Please try again.');
          return;
        }
      }
      
      // Step 5: Clear messages in UI for fresh start
      setMessages([{
        text: "Hi there! How can I help you?",
        isBot: true,
        diagnosis: null,
        actionSteps: [],
        parsedContent: null,
      }]);
      
      // Clear recommendation notification AFTER setting messages to prevent re-detection
      setShowRecommendationNotification(false);
      setCurrentRecommendation(null);
      
      console.log('✅ Experiment started successfully - switched to machine:', firstConfig.machine.id);
      
    } catch (error) {
      console.error('❌ Error beginning experiment:', error);
      alert('An unexpected error occurred while starting the experiment. Please try again.');
    }
  };

  const handleNewChat = async () => {
    try {
      if (isBaseline) {
        // In baseline phase, just clear chat but stay on same machine
        resetCurrentChatMessages();
        
        setMessages([{
          text: "Hi there! How can I help you?",
          isBot: true,
          diagnosis: null,
          actionSteps: [],
          parsedContent: null,
        }]);
        
        // Clear recommendation notification AFTER setting messages to prevent re-detection
        setShowRecommendationNotification(false);
        setCurrentRecommendation(null);
        
        return;
      }
      
      // In experiment phase, switch to next config with enhanced safety
      console.log('🔄 Switching to next configuration...');
      
      // Clear any previous errors
      clearTransitionError();
      
      const nextConfig = await selectNextConfigSafely();
      
      if (!nextConfig) {
        // Error message already set by selectNextConfigSafely
        return;
      }
      
      if (nextConfig.experimentCompleted) {
        const progress = getExperimentProgress();
        alert(`🎉 Experiment completed! Thank you for participating.\n\nYou tested ${progress.completed} out of ${progress.totalConfigs} configurations.`);
        return;
      }
      
      // Reset session state
      sessionInitiated.current = false;
      setIsFullyInitialized(false);
      
      // Initiate new session on new machine with enhanced error handling
      if (nextConfig.needsNewSession && userId) {
        console.log('🔗 Initiating session on new machine:', nextConfig.machine.id);
        
        // Add delay to ensure machine is ready
        await new Promise(resolve => setTimeout(resolve, 1500));
        
        try {
          await initiateSession(userId);
          console.log('✅ Session initiated successfully on new machine');
          
          // Additional delay to ensure session is fully established
          await new Promise(resolve => setTimeout(resolve, 500));
          
        } catch (sessionError) {
          console.error('❌ Session initiation failed:', sessionError);
          alert('Failed to establish connection with the next experiment server. Please try again.');
          return;
        }
      }
      
      // Reset current chat message count and clear messages in UI for fresh start
      resetCurrentChatMessages();
      setMessages([{
        text: "Hi there! How can I help you?",
        isBot: true,
        diagnosis: null,
        actionSteps: [],
        parsedContent: null,
      }]);
      
      // Clear recommendation notification AFTER setting messages to prevent re-detection
      setShowRecommendationNotification(false);
      setCurrentRecommendation(null);
      
      console.log('✅ Successfully switched to config:', nextConfig.config);
      
    } catch (error) {
      console.error('❌ Error in new chat:', error);
      alert('An unexpected error occurred while switching configurations. Please try again.');
    }
  };

  // Handle reconnection to alternate server for current config
  const handleReconnect = async () => {
    try {
      console.log('🔄 Attempting to reconnect to current config with alternate server...');
      
      // Clear any previous errors
      clearTransitionError();
      
      const reconnectResult = await reconnectToCurrentConfig();
      
      if (!reconnectResult.success) {
        // Error message already set by reconnectToCurrentConfig
        return;
      }
      
      console.log('🎯 Reconnection successful:', reconnectResult);
      
      // Reset session state to force new session on alternate machine
      sessionInitiated.current = false;
      setIsFullyInitialized(false);
      
      // Initiate new session on the alternate machine
      if (userId && reconnectResult.needsNewSession) {
        console.log('🔗 Initiating session on alternate machine:', reconnectResult.machine.id);
        
        // Add delay to ensure machine is ready
        await new Promise(resolve => setTimeout(resolve, 1000));
        
        try {
          await initiateSession(userId);
          console.log('✅ Session initiated successfully on alternate machine');
          
          // Additional delay to ensure session is fully established
          await new Promise(resolve => setTimeout(resolve, 500));
          
          // Show success message
          alert(`✅ ${reconnectResult.message}\n\nConnection successfully switched to alternate server.`);
          
        } catch (sessionError) {
          console.error('❌ Session initiation failed on alternate machine:', sessionError);
          alert('Reconnected to alternate server but failed to initialize session. Please try reconnecting again.');
          return;
        }
      }
      
      // Clear messages in UI for fresh start
      setMessages([{
        text: "Hi there! How can I help you?",
        isBot: true,
        diagnosis: null,
        actionSteps: [],
        parsedContent: null,
      }]);
      
      // Clear recommendation notification AFTER setting messages to prevent re-detection
      setShowRecommendationNotification(false);
      setCurrentRecommendation(null);
      
      console.log('✅ Successfully reconnected to alternate server');
      
    } catch (error) {
      console.error('❌ Error in reconnection:', error);
      alert('An unexpected error occurred during reconnection. Please try again.');
    }
  };

  /* cluecollector */

  /**
   * ErrorModal component displays an error message in a modal dialog.
   *
   * @component
   * @param {Object} props - The component props.
   * @param {boolean} props.isOpen - Determines whether the modal is open or not.
   * @param {function} props.onClose - The function to be called when the modal is closed.
   * @param {string} props.errorMessage - The error message to be displayed.
   * @returns {JSX.Element|null} The ErrorModal component.
   */
  function ErrorModal({ isOpen, onClose, errorMessage }) {
    if (!isOpen) return null;

    return (
      <div
        style={{
          position: "fixed",
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: "rgba(0, 0, 0, 0.5)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <div
          style={{
            backgroundColor: "rgba(28, 30, 58, 1)",
            padding: "20px",
            borderRadius: "5px",
            textAlign: "center",
          }}
        >
          <p
            style={{
              color: "white",
              fontSize: "1.5rem",
              paddingBottom: "10px",
            }}
          >
            {errorMessage}
          </p>{" "}
          {/* Adjusted text color for better readability */}
          <button
            onClick={onClose}
            style={{
              backgroundColor: "#4CAF50", // A green color for the button
              color: "white", // White text color for the button
              padding: "10px 20px", // Adjusted padding for better look
              margin: "10px 0", // Added some margin to top for spacing
              border: "none", // Remove the default border
              borderRadius: "4px", // Rounded corners for the button
              cursor: "pointer", // Cursor to pointer to indicate it's clickable
              transition: "background-color 0.3s", // Smooth transition for hover effect
            }}
            onMouseOver={(e) =>
              (e.currentTarget.style.backgroundColor = "#45a049")
            } // Darker green on hover
            onMouseOut={(e) =>
              (e.currentTarget.style.backgroundColor = "#4CAF50")
            } // Original green when not hovered
          >
            Close
          </button>
        </div>
      </div>
    );
  }

  return (
    <ThemeProvider theme={theme}>
      <AuthGate>
        {({ signOut, user }) => (
          <div
            className="App"
            style={{ fontFamily: currentFont }}
          >
            <div className={`sidebar ${isSidebarCollapsed ? "collapsed" : ""}`}>
              <button className="sidebar-toggle" onClick={toggleSidebar}>
                <img
                  src={isSidebarCollapsed ? expandIcon : collapseIcon}
                  alt={isSidebarCollapsed ? "Expand" : "Collapse"}
                  width="20"
                  height="20"
                />
              </button>
              <div className="upperSide">
                  <div className="upperSideTop">
                    <span className="secmate-title">SecMate</span>
                  </div>
                  
                  {/* === TEST MODE SECTION === */}
                  <div style={{ 
                    marginBottom: '16px', 
                    padding: '12px', 
                    backgroundColor: 'rgba(255,165,0,0.08)', 
                    borderRadius: '8px', 
                    border: '1px solid rgba(255,165,0,0.2)' 
                  }}>
                    <div style={{ 
                      fontSize: '0.85em', 
                      fontWeight: 'bold', 
                      color: '#ffa500', 
                      marginBottom: '8px',
                      textAlign: 'center' 
                    }}>
                      🧪 TESTING MODE
                    </div>
                    <button
                      onClick={toggleTestMode}
                      style={{
                        width: '100%',
                        padding: '8px 12px',
                        backgroundColor: isTestMode ? '#ff6b6b' : '#4CAF50',
                        color: 'white',
                        border: 'none',
                        borderRadius: '6px',
                        cursor: 'pointer',
                        fontSize: '0.9em',
                        fontWeight: 'bold',
                        transition: 'all 0.2s ease'
                      }}
                    >
                      {isTestMode ? '🔴 Test Mode ON' : '🟢 Live Mode'}
                    </button>
                    {isTestMode && (
                      <div style={{ 
                        marginTop: '8px', 
                        color: '#ffa500', 
                        fontSize: '0.75em', 
                        textAlign: 'center',
                        fontStyle: 'italic'
                      }}>
                        Connections are mocked for testing
                      </div>
                    )}
                    
                    {/* Connection Log */}
                    {isTestMode && testModeConnectionLog.length > 0 && (
                      <div style={{ 
                        marginTop: '12px', 
                        maxHeight: '120px', 
                        overflowY: 'auto',
                        backgroundColor: 'rgba(0,0,0,0.2)',
                        borderRadius: '4px',
                        padding: '6px'
                      }}>
                        <div style={{ 
                          color: '#ffa500', 
                          fontSize: '0.75em', 
                          marginBottom: '6px',
                          fontWeight: 'bold'
                        }}>
                          📡 Connection Log:
                        </div>
                        {testModeConnectionLog.slice(-3).map((log, index) => (
                          <div key={index} style={{ 
                            fontSize: '0.7em', 
                            color: '#ddd', 
                            marginBottom: '3px',
                            padding: '3px 6px',
                            backgroundColor: 'rgba(255,255,255,0.05)',
                            borderRadius: '3px',
                            borderLeft: '2px solid #ffa500'
                          }}>
                            {`${log.target} -> Config ${log.config.toUpperCase()}`}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                  
                  {/* === EXPERIMENT STATUS SECTION === */}
                  {isBaseline && (
                    <div style={{ 
                      marginBottom: '16px', 
                      padding: '12px', 
                      backgroundColor: 'rgba(76, 175, 80, 0.1)', 
                      borderRadius: '8px',
                      border: '1px solid rgba(76, 175, 80, 0.3)'
                    }}>
                      <div style={{ 
                        color: '#4CAF50', 
                        marginBottom: '12px', 
                        fontWeight: 'bold',
                        fontSize: '0.9em',
                        textAlign: 'center'
                      }}>
                        📊 BASELINE PHASE
                      </div>
                      
                      <div style={{ 
                        display: 'flex', 
                        justifyContent: 'space-between', 
                        marginBottom: '8px',
                        fontSize: '0.85em'
                      }}>
                        <span style={{ color: '#ccc' }}>Total Messages:</span>
                        <span style={{ color: '#4CAF50', fontWeight: 'bold' }}>{baselineMessageCount}</span>
                      </div>
                      
                      <div style={{ 
                        display: 'flex', 
                        justifyContent: 'space-between', 
                        marginBottom: '12px',
                        fontSize: '0.85em'
                      }}>
                        <span style={{ color: '#ccc' }}>Current Chat:</span>
                        <span style={{ color: '#4CAF50', fontWeight: 'bold' }}>{currentChatMessageCount}</span>
                      </div>
                      
                      {baselineMessageCount === 0 && (
                        <div style={{ 
                          color: '#ffa500', 
                          fontSize: '0.8em', 
                          marginBottom: '12px',
                          padding: '8px',
                          backgroundColor: 'rgba(255, 165, 0, 0.1)',
                          borderRadius: '4px',
                          textAlign: 'center',
                          border: '1px dashed rgba(255, 165, 0, 0.4)'
                        }}>
                          💬 Send a message to unlock experiment
                        </div>
                      )}
                      
                      {canBeginExperiment && (
                        <button
                          className="midBtn experiment-btn"
                          onClick={handleBeginExperiment}
                          disabled={isTransitioning}
                          style={{ 
                            backgroundColor: isTransitioning ? '#666' : '#4CAF50', 
                            border: '2px solid #45a049',
                            width: '100%',
                            fontSize: '0.9em',
                            fontWeight: 'bold',
                            padding: '10px',
                            transition: 'all 0.2s ease'
                          }}
                        >
                          {isTransitioning ? '🔄 Starting...' : '🚀 Begin Experiment'}
                        </button>
                      )}
                    </div>
                  )}
                  
                  {/* === EXPERIMENT PROGRESS SECTION === */}
                  {!isBaseline && (
                    <div style={{ 
                      marginBottom: '16px', 
                      padding: '12px', 
                      backgroundColor: 'rgba(76, 175, 80, 0.1)', 
                      borderRadius: '8px',
                      border: '1px solid rgba(76, 175, 80, 0.3)'
                    }}>
                      <div style={{ 
                        color: '#4CAF50', 
                        marginBottom: '12px', 
                        fontWeight: 'bold',
                        fontSize: '0.9em',
                        textAlign: 'center'
                      }}>
                        🧪 EXPERIMENT ACTIVE
                      </div>
                      
                      {(() => {
                        const progress = getExperimentProgress();
                        return (
                          <>
                            <div style={{ 
                              display: 'flex', 
                              justifyContent: 'space-between', 
                              marginBottom: '8px',
                              fontSize: '0.85em'
                            }}>
                              <span style={{ color: '#ccc' }}>Progress:</span>
                              <span style={{ color: '#4CAF50', fontWeight: 'bold' }}>
                                {progress.completed}/{progress.totalConfigs} configs
                              </span>
                            </div>
                          
                            <div style={{ 
                              backgroundColor: 'rgba(255,255,255,0.1)', 
                              height: '6px', 
                              borderRadius: '3px',
                              marginBottom: '8px',
                              overflow: 'hidden'
                            }}>
                              <div style={{ 
                                backgroundColor: '#4CAF50', 
                                height: '6px', 
                                borderRadius: '3px',
                                width: `${progress.progress}%`,
                                transition: 'width 0.3s ease'
                              }}></div>
                            </div>
                            
                            <div style={{ 
                              fontSize: '0.75em', 
                              color: '#999', 
                              textAlign: 'center'
                            }}>
                              {progress.remaining} configurations remaining
                            </div>
                          </>
                        );
                      })()}
                    </div>
                  )}
                  
                  {/* === CURRENT MACHINE INFO === */}
                  {getCurrentMachineInfo() && !isTransitioning && !isReconnecting && (
                    <div style={{ 
                      fontSize: '0.8em', 
                      color: '#ccc', 
                      marginBottom: '16px',
                      padding: '10px',
                      backgroundColor: 'rgba(255, 255, 255, 0.03)',
                      borderRadius: '6px',
                      border: '1px solid rgba(255, 255, 255, 0.08)'
                    }}>
                      <div style={{ 
                        color: '#4CAF50', 
                        fontWeight: 'bold', 
                        marginBottom: '8px',
                        fontSize: '0.9em',
                        textAlign: 'center'
                      }}>
                        🖥️ CURRENT SERVER
                      </div>
                      {(() => {
                        const machineInfo = getCurrentMachineInfo();
                        return (
                          <div style={{ fontSize: '0.85em' }}>
                            <div style={{ marginBottom: '4px' }}>
                              <strong>Machine:</strong> <span style={{ color: '#4CAF50' }}>{machineInfo.machineId}</span>
                            </div>
                            <div style={{ marginBottom: '4px' }}>
                              <strong>Server:</strong> <span style={{ color: '#4CAF50' }}>{currentMachineIndex + 1}/2</span>
                            </div>
                            {isTestMode && (
                              <div style={{ color: '#ffa500', fontSize: '0.8em' }}>
                                <strong>Target IP:</strong> {machineInfo.machineIp}
                              </div>
                            )}
                          </div>
                        );
                      })()}
                    </div>
                  )}
                  
                  {/* === ACTION BUTTONS SECTION === */}
                  <div style={{ marginBottom: '16px' }}>
                    <button
                      className="midBtn"
                      onClick={handleNewChat}
                      disabled={isTransitioning || isReconnecting || !canStartNewChat}
                      style={{ 
                        opacity: (isTransitioning || isReconnecting || !canStartNewChat) ? 0.6 : 1,
                        backgroundColor: (isTransitioning || isReconnecting || !canStartNewChat) ? '#555' : '#007BFF',
                        border: '2px solid #0056b3',
                        width: '100%',
                        marginBottom: '8px',
                        fontSize: '0.9em',
                        fontWeight: 'bold',
                        transition: 'all 0.2s ease'
                      }}
                    >
                      <img className="addBtn" alt="new chat" src={addBtn} />
                      {isTransitioning ? '🔄 Switching...' : isReconnecting ? '🔄 Reconnecting...' : 'New Chat'}
                    </button>
                    
                    {/* Reconnect Button */}
                    {currentConfig && getCurrentMachineInfo() && !isTransitioning && (
                      <button
                        className="midBtn"
                        onClick={handleReconnect}
                        disabled={isReconnecting}
                        style={{ 
                          opacity: isReconnecting ? 0.6 : 1,
                          backgroundColor: isReconnecting ? '#666' : '#ff9800',
                          border: '2px solid #f57c00',
                          width: '100%',
                          fontSize: '0.85em',
                          fontWeight: 'bold',
                          transition: 'all 0.2s ease'
                        }}
                      >
                        {isReconnecting ? '🔄 Reconnecting...' : '🔁 Try Alternate Server'}
                      </button>
                    )}
                  </div>
                  
                  {/* === STATUS MESSAGES === */}
                  {!canStartNewChat && !isTransitioning && !isReconnecting && (
                    <div style={{ 
                      fontSize: '0.8em', 
                      color: '#ffa500', 
                      textAlign: 'center',
                      padding: '8px 10px',
                      backgroundColor: 'rgba(255, 165, 0, 0.08)',
                      borderRadius: '6px',
                      border: '1px dashed rgba(255, 165, 0, 0.3)',
                      marginBottom: '8px'
                    }}>
                      💬 Send a message to enable New Chat
                    </div>
                  )}
                </div>
              
              <div className="lowerSide">
                <UserMenu
                  isOpen={isUserMenuOpen}
                  setIsOpen={setIsUserMenuOpen}
                  onClose={() => setIsUserMenuOpen(false)}
                  userEmail={userEmail}
                  onLogout={handleLogout}
                  onFontChange={handleFontChange}
                  onFontSizeChange={handleFontSizeChange}
                  associatedCid={associatedCid}
                  hasRecommendation={recommendation !== null}
                  recommendationContent={recommendation}
                />
              </div>
            </div>
            <div className="main">
              <div className="chat-container">
                <div className="chat-messages" ref={chatMessagesRef}>
                  {/* Error Display */}
                  {transitionError && (
                    <div style={{
                      backgroundColor: 'rgba(244, 67, 54, 0.1)',
                      border: '1px solid #f44336',
                      borderRadius: '8px',
                      padding: '12px',
                      margin: '10px 0',
                      color: '#f44336',
                      fontSize: '0.9em',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center'
                    }}>
                      <div>
                        <strong>⚠️ Connection Error:</strong><br />
                        {transitionError}
                      </div>
                      <button
                        onClick={clearTransitionError}
                        style={{
                          background: 'none',
                          border: 'none',
                          color: '#f44336',
                          cursor: 'pointer',
                          fontSize: '1.2em',
                          padding: '0 5px'
                        }}
                      >
                        ×
                      </button>
                    </div>
                  )}

                  {/* Test Mode Information */}
                  {isTestMode && !isTransitioning && (
                    <div style={{
                      backgroundColor: 'rgba(255, 87, 51, 0.1)',
                      border: '1px solid #ff5733',
                      borderRadius: '8px',
                      padding: '12px',
                      margin: '10px 0',
                      color: '#ff5733',
                      fontSize: '0.9em',
                      textAlign: 'center'
                    }}>
                      🧪 <strong>TEST MODE ACTIVE</strong><br />
                      Current Config: <strong>{currentConfig?.toUpperCase()}</strong><br />
                      {(() => {
                        const machineInfo = getCurrentMachineInfo();
                        return machineInfo ? `Target IP: ${machineInfo.machineIp}` : 'Baseline Mode';
                      })()}
                    </div>
                  )}

                  {/* Connection Status */}
                  {isTransitioning && (
                    <div style={{
                      backgroundColor: 'rgba(255, 193, 7, 0.1)',
                      border: '1px solid #ffc107',
                      borderRadius: '8px',
                      padding: '12px',
                      margin: '10px 0',
                      color: '#ffc107',
                      fontSize: '0.9em',
                      textAlign: 'center'
                    }}>
                      🔄 {isTestMode ? 'Simulating connection...' : 
                           connectionStatus === 'unknown' ? 'Testing connection...' : 
                           connectionStatus === 'connected' ? 'Connected! Initializing session...' :
                           'Trying alternate servers...'}
                    </div>
                  )}

                  {/* Reconnection Status */}
                  {isReconnecting && (
                    <div style={{
                      backgroundColor: 'rgba(255, 152, 0, 0.1)',
                      border: '1px solid #ff9800',
                      borderRadius: '8px',
                      padding: '12px',
                      margin: '10px 0',
                      color: '#ff9800',
                      fontSize: '0.9em',
                      textAlign: 'center'
                    }}>
                      🔁 {isTestMode ? 'Simulating reconnection to alternate server...' : 
                           'Reconnecting to alternate server...'}
                      <br />
                      <small>Switching to backup server for current configuration</small>
                    </div>
                  )}

                  {!showTutorial && (
                    <button
                      className="tutorial-icon"
                      onClick={() => setShowTutorial(true)}
                      aria-label="Start Tutorial"
                    >
                      <HelpCircle size={24} />
                    </button>
                  )}

                  {showTutorial && (
                    <TutorialBubble
                      steps={tutorialSteps}
                      onComplete={handleTutorialComplete}
                      onStepChange={handleTutorialStepChange}
                    />
                  )}

                  {/* {showDefaultOptions && (
                    <DefaultChatOptions onOptionSelect={handleDefaultOption} />
                  )} */}
                  {messages.map((message, index) => (
                    <ChatMessage
                      key={index}
                      message={message}
                      index={index}
                      currentStepIndices={currentStepIndices}
                      onHover={setHoveredMessageIndex}
                      onLeaveHover={() => setHoveredMessageIndex(null)}
                      onNextStep={handleNextStep}
                      onFeedback={handleFeedback}
                      onRecommendationDetected={handleRecommendationDetected}
                    />
                  ))}
                  <LoadingIndicator
                    isLoading={isLoading}
                    loadingPrompt={currentLoadingPrompt}
                  />
                  <div ref={msgEnd}></div>
                </div>
                <ChatInput
                  input={input}
                  setInput={setInput}
                  isLoading={isLoading}
                  onSend={handleSendMsg}
                  onUpload={handleUpload}
                  onEnter={handleEnter}
                  isSessionLoading={isTestMode ? isTransitioning : (!isFullyInitialized || isTransitioning)}
                  isTestMode={isTestMode}
                />
              </div>
            </div>
            
            {/* Recommendation Notification */}
            {showRecommendationNotification && currentRecommendation && (
              <div className={`recommendation-notification ${isRecommendationMinimized ? 'minimized' : ''} ${fontSizeClass}`}>
                <div className="recommendation-notification-header">
                  <div className="recommendation-notification-title">
                    <Bell size={20} />
                    <span>Product Recommendation</span>
                  </div>
                  <button 
                    className="recommendation-minimize-btn" 
                    onClick={() => setIsRecommendationMinimized(!isRecommendationMinimized)}
                  >
                    {isRecommendationMinimized ? '+' : '-'}
                  </button>
                </div>
                
                {/* This entire content block will be hidden when minimized */}
                {!isRecommendationMinimized && (
                  <div className="recommendation-notification-content">
                    <div className="recommendation-notification-body">
                      {(() => {
                        const formatted = formatRecommendation(currentRecommendation);
                        return (
                          <div>
                            {formatted?.productName && (
                              <div className="recommendation-product-name">
                                <strong>{formatted.productName}</strong>
                              </div>
                            )}
                            <div className="recommendation-description">
                              {formatted?.description || currentRecommendation}
                            </div>
                          </div>
                        );
                      })()}
                    </div>
                  </div>
                )}
              </div>
            )}
            
            <ErrorModal
              isOpen={isErrorModalOpen}
              onClose={() => setIsErrorModalOpen(false)}
              errorMessage={uploadError}
            />
          </div>
        )}
      </AuthGate>
    </ThemeProvider>
  );
}

export default App;
