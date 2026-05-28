import { useState, useEffect, useRef, useCallback } from "react";
import axios from "axios";

export const useRecommendations = (
  sessionToken,
  apiBaseUrl,
  isSendingMessage,
  isTestMode = false
) => {
  const [recommendation, setRecommendation] = useState(null);
  const [isConnected, setIsConnected] = useState(false);
  const previousRecommendationId = useRef(null);

  // Wrap fetchRecommendation in useCallback
  const fetchRecommendation = useCallback(async () => {
    if (isSendingMessage || !sessionToken) {
      console.log("Message being sent, skipping rec check");
      return;
    }

    // Skip API calls in test mode
    if (isTestMode) {
      console.log("🧪 TEST MODE: Skipping recommendation fetch");
      setRecommendation(null);
      return;
    }

    // Skip if apiBaseUrl is null or invalid
    if (!apiBaseUrl || apiBaseUrl === 'null') {
      console.warn("Invalid apiBaseUrl, skipping recommendation fetch");
      setRecommendation(null);
      return;
    }

    try {
      const response = await axios.get(`${apiBaseUrl}/get_recommendation`, {
        headers: {
          Authorization: `Bearer ${sessionToken}`,
          "Content-Type": "application/json",
        },
      });
      const data = response.data;
      if (data.rec === true && data.rec_content) {
        if (data.rec_content.id !== previousRecommendationId.current) {
          previousRecommendationId.current = data.rec_content.id;
          setRecommendation(data.rec_content);
        }
      } else {
        setRecommendation(null);
      }
    } catch (error) {
      console.error("Failed to fetch recommendation:", error);
      setRecommendation(null);
      if (error.response && error.response.status === 401) {
        console.error("Session expired during recommendation fetch");
      }
    }
  }, [apiBaseUrl, sessionToken, isSendingMessage, isTestMode]);

  // Wrap checkConnectivity in useCallback
  const checkConnectivity = useCallback(async () => {
    if (isSendingMessage) {
      console.log("Message being sent, skipping connectivity check");
      return;
    }

    // Skip API calls in test mode
    if (isTestMode) {
      console.log("🧪 TEST MODE: Skipping connectivity check");
      setIsConnected(true); // Always show as connected in test mode
      return;
    }

    // Skip if apiBaseUrl is null or invalid
    if (!apiBaseUrl || apiBaseUrl === 'null') {
      console.warn("Invalid apiBaseUrl, skipping connectivity check");
      setIsConnected(false);
      return;
    }

    try {
      const response = await axios.get(
        `${apiBaseUrl}/check_agent_connectivity`,
        {
          headers: {
            Authorization: `Bearer ${sessionToken}`,
            "Content-Type": "application/json",
          },
        }
      );
      setIsConnected(response.data.connected);
    } catch (error) {
      console.error("Failed to check agent connectivity:", error);
      setIsConnected(false);
    }
  }, [apiBaseUrl, sessionToken, isSendingMessage, isTestMode]);

  useEffect(() => {
    if (sessionToken) {
      const pollInterval = setInterval(() => {
        if (!isSendingMessage) {
          checkConnectivity();
          fetchRecommendation();
        }
      }, 10000);

      return () => clearInterval(pollInterval);
    }
  }, [sessionToken, isSendingMessage, checkConnectivity, fetchRecommendation]);

  return {
    recommendation,
    isConnected,
    fetchRecommendation,
    checkConnectivity,
  };
};
