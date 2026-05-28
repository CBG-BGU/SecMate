import { useState, useRef, useEffect } from "react";
import axios from "axios";
import { parseAIResponse } from "../utils/responseParser";

export const useChat = (sessionToken, apiBaseUrl, initiateSession, userId, incrementBaselineMessages, testModeOptions = {}) => {
  const [messages, setMessages] = useState([
    {
      text: "Hi there! How can I help you?",
      isBot: true,
      diagnosis: null,
      actionSteps: [],
      parsedContent: null,
    },
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isSendingMessage, setIsSendingMessage] = useState(false);
  const [showDefaultOptions, setShowDefaultOptions] = useState(true);
  const [diagnosis, setDiagnosis] = useState("");
  const [actionSteps, setActionSteps] = useState([]);
  const [showNextButton, setShowNextButton] = useState(false);
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [files, setFiles] = useState([]);
  const [currentLoadingPrompt, setCurrentLoadingPrompt] = useState("");
  const [loadingPromptInterval, setLoadingPromptInterval] = useState(null);
  const [techLevels, setTechLevels] = useState({});
  const isProgrammaticChange = useRef(false);
  const msgEnd = useRef(null);

  const mainLoadingPrompts = [
    "Analyzing query and context",
    "Accessing knowledge base",
    "Processing relevant information",
    "Synthesizing response",
    "Optimizing output for user comprehension",
    "Finalizing response",
  ];

  const sendMsgToOpenAI = async (msg) => {
    setIsSendingMessage(true);
    
    // Extract test mode options
    const { isTestMode, generateMockResponse, currentConfig } = testModeOptions;
    
    // Handle test mode
    if (isTestMode && generateMockResponse && currentConfig) {
      console.log(`🧪 TEST MODE: Generating mock response for config ${currentConfig}`);
      setIsLoading(true);
      cycleLoadingPrompts();
      
      // Simulate API delay
      await new Promise(resolve => setTimeout(resolve, 2000));
      
      const mockResponse = generateMockResponse(msg, currentConfig);
      
      stopLoadingPrompts();
      setIsLoading(false);
      setIsSendingMessage(false);
      
      console.log(`🧪 TEST MODE: Mock response generated for "${msg}" using config ${currentConfig.toUpperCase()}`);
      
      // Skip parsing for config 'e' (Raw GPT)
      if (currentConfig === 'e') {
        return {
          text: mockResponse,
          diagnosis: null,
          actionSteps: [],
          parsedContent: null,
        };
      }
      
      // Parse the mock response for other configs
      const parsedContent = parseAIResponse(mockResponse);
      
      return {
        text: mockResponse,
        diagnosis: parsedContent.diagnosis,
        actionSteps: parsedContent.steps.map(step => step.text),
        parsedContent: parsedContent,
      };
    }

    if (!sessionToken) {
      console.error("No session token available");
      return {
        text: "I'm sorry, but there seems to be an issue with your session. Please try logging out and back in.",
        diagnosis: null,
        actionSteps: [],
        parsedContent: null,
      };
    }

    setIsLoading(true);
    cycleLoadingPrompts(); // Start cycling through loading prompts

    const maxRetries = 3;
    const baseDelay = 1000;

    for (let attempt = 0; attempt < maxRetries; attempt++) {
      try {
        const response = await axios.post(
          `${apiBaseUrl}/send_message_to_genai`,
          { message: msg },
          {
            headers: {
              "Content-Type": "application/json",
              Authorization: `Bearer ${sessionToken}`,
            },
          }
        );
        const data = response.data;
        isProgrammaticChange.current = true;
        setTechLevels(data.tech_level);

        let responseText = data.response;
        let parsedResponse = {
          text: responseText,
          diagnosis: null,
          actionSteps: [],
          parsedContent: null,
        };

        // Try to parse JSON response first (backwards compatibility)
        try {
          const jsonResponse = JSON.parse(responseText);
          responseText = jsonResponse.response || responseText;
          parsedResponse.diagnosis = jsonResponse.diagnosis || null;
          parsedResponse.actionSteps = jsonResponse.action_steps || [];
        } catch (parseError) {
          console.log("Response is not JSON, parsing as plain text");
        }

        // Special handling for config 'e' (Raw GPT) - parse recommendations only
        if (currentConfig === 'e') {
          console.log("🤖 Config E: Parsing recommendations only, skipping steps and diagnosis");
          
          // Parse the response to extract only the recommendation
          const parsedContent = parseAIResponse(responseText);
          
          // Remove recommendation from the response text so it doesn't appear twice
          let cleanedResponseText = responseText;
          if (parsedContent.recommendation) {
            cleanedResponseText = responseText.replace(/\*\*Especially for you:\*\*[\s\S]*?---/i, '').trim();
          }
          
          // Create a custom parsed content that only includes recommendation
          const configEParsedContent = {
            recommendation: parsedContent.recommendation, // Keep recommendation if present
            diagnosis: null, // Skip diagnosis
            steps: [], // Skip steps
            otherContent: cleanedResponseText, // Use cleaned text without recommendation
            hasStructuredContent: !!parsedContent.recommendation // Only true if there's a recommendation
          };
          
          parsedResponse.text = cleanedResponseText; // Show cleaned text without recommendation
          parsedResponse.parsedContent = configEParsedContent;
          // Keep diagnosis and actionSteps as null/empty since we're not parsing them
          parsedResponse.diagnosis = null;
          parsedResponse.actionSteps = [];
        } else {
          // Parse the response text using our new parser for other configs
          const parsedContent = parseAIResponse(responseText);
          
          // Merge parsed content with any existing structured data
          parsedResponse.parsedContent = parsedContent;
          parsedResponse.text = responseText;
          
          // If we have parsed diagnosis/steps, prefer those over JSON ones
          if (parsedContent.diagnosis) {
            parsedResponse.diagnosis = parsedContent.diagnosis;
          }
          if (parsedContent.steps.length > 0) {
            parsedResponse.actionSteps = parsedContent.steps.map(step => step.text);
          }
        }

        stopLoadingPrompts(); // Stop cycling through loading prompts
        setIsLoading(false);

        // Update state based on parsed response
        setDiagnosis(parsedResponse.diagnosis);
        setActionSteps(parsedResponse.actionSteps);
        setShowNextButton(parsedResponse.actionSteps.length > 0);
        setCurrentStepIndex(0);

        return parsedResponse;
      } catch (error) {
        console.error(`Attempt ${attempt + 1} failed:`, error);
        if (attempt === maxRetries - 1) {
          stopLoadingPrompts();
          setIsLoading(false);
          setIsSendingMessage(false);
          throw error;
        }
        await new Promise(resolve => setTimeout(resolve, baseDelay * Math.pow(2, attempt)));
      }
    }
  };

  const handleSendMsg = async () => {
    const text = input.trim();
    if (text === "" || isLoading) return;

    setInput("");
    setShowDefaultOptions(false);
    setIsLoading(true);
    setMessages((prevMessages) => [
      ...prevMessages,
      { text, isBot: false, diagnosis: null, actionSteps: [], parsedContent: null },
    ]);

    try {
      const res = await sendMsgToOpenAI(text);
      setMessages((prevMessages) => [
        ...prevMessages,
        {
          text: res.text,
          isBot: true,
          diagnosis: res.diagnosis,
          actionSteps: res.actionSteps,
          parsedContent: res.parsedContent,
        },
      ]);
      
      // Track baseline messages for experiment eligibility
      if (incrementBaselineMessages && typeof incrementBaselineMessages === 'function') {
        incrementBaselineMessages();
      }
      
    } catch (error) {
      console.error("Failed to send message:", error);
      setMessages((prevMessages) => [
        ...prevMessages,
        {
          text: "I'm sorry, but I'm having trouble responding right now. Please try again in a moment.",
          isBot: true,
          diagnosis: null,
          actionSteps: [],
          parsedContent: null,
        },
      ]);
    } finally {
      setIsLoading(false);
      stopLoadingPrompts();
    }

    setFiles([]);
  };

  const handleDefaultOption = async (option) => {
    setInput("");
    setShowDefaultOptions(false);

    const userMessage = {
      text: option,
      isBot: false,
      diagnosis: null,
      actionSteps: [],
      parsedContent: null,
    };

    setMessages((prevMessages) => [...prevMessages, userMessage]);

    try {
      setIsLoading(true);
      const response = await sendMsgToOpenAI(option);
      setIsLoading(false);

      const botMessage = {
        text: response.text,
        isBot: true,
        diagnosis: response.diagnosis,
        actionSteps: response.actionSteps,
        parsedContent: response.parsedContent,
      };

      setMessages((prevMessages) => [...prevMessages, botMessage]);
      
      // Track baseline messages for experiment eligibility
      if (incrementBaselineMessages && typeof incrementBaselineMessages === 'function') {
        incrementBaselineMessages();
      }
      
    } catch (error) {
      console.error("Error fetching chat response:", error);
      setIsLoading(false);
      setMessages((prevMessages) => [
        ...prevMessages,
        {
          text: "Sorry, I couldn't process that request. Please try again.",
          isBot: true,
          diagnosis: null,
          actionSteps: [],
          parsedContent: null,
        },
      ]);
    }
  };

  const cycleLoadingPrompts = () => {
    let currentIndex = 0;
    setCurrentLoadingPrompt(mainLoadingPrompts[currentIndex]);

    const interval = setInterval(() => {
      currentIndex++;
      if (currentIndex < mainLoadingPrompts.length) {
        setCurrentLoadingPrompt(mainLoadingPrompts[currentIndex]);
      } else {
        // Keep the last prompt for a moment before stopping
        setTimeout(() => {
          if (loadingPromptInterval) {
            clearInterval(loadingPromptInterval);
            setLoadingPromptInterval(null);
          }
        }, 1000); // Show the last prompt for 1 second
        clearInterval(interval);
      }
    }, 5000); // Change prompt

    setLoadingPromptInterval(interval);
  };

  const stopLoadingPrompts = () => {
    if (loadingPromptInterval) {
      clearInterval(loadingPromptInterval);
      setLoadingPromptInterval(null);
    }
    setCurrentLoadingPrompt("");
  };

  return {
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
  };
};
