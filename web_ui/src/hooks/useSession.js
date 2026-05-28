import { useState, useEffect, useRef, useCallback } from "react";
import axios from "axios";
import KJUR from "jsrsasign";
import { getCurrentUser } from "@aws-amplify/auth";

export const useSession = (apiBaseUrl, isTestMode = false) => {
  const [userId, setUserId] = useState(null);
  const [sessionToken, setSessionToken] = useState(null);
  const [isFullyInitialized, setIsFullyInitialized] = useState(isTestMode); // Start initialized in test mode
  const sessionInitiated = useRef(false);
  const SECRET_KEY =
    process.env.REACT_APP_SESSION_SIGNING_SECRET ||
    "replace-with-example-session-secret";

  // In test mode, immediately set as fully initialized
  useEffect(() => {
    if (isTestMode && sessionToken) {
      console.log("🧪 TEST MODE: Setting session as fully initialized");
      setIsFullyInitialized(true);
    }
  }, [isTestMode, sessionToken]);

  // Initialize test mode immediately on mount
  useEffect(() => {
    if (isTestMode && !sessionToken) {
      console.log("🧪 TEST MODE: Auto-initializing session");
      const mockToken = `mock-session-token-${Date.now()}`;
      setSessionToken(mockToken);
      sessionInitiated.current = true;
      setIsFullyInitialized(true);
    }
  }, [isTestMode, sessionToken]);

  const initiateSession = useCallback(async (cognitoUserId) => {
    if (sessionInitiated.current) return; // Prevent multiple initiations

    // Handle test mode
    if (isTestMode) {
      console.log("🧪 TEST MODE: Mocking session initiation");
      const mockSessionToken = `mock-session-token-${Date.now()}`;
      setSessionToken(mockSessionToken);
      localStorage.setItem("sessionToken", mockSessionToken);
      sessionInitiated.current = true;
      setIsFullyInitialized(true);
      console.log("🧪 TEST MODE: Mock session initiated successfully");
      return;
    }

    // Skip if apiBaseUrl is null or invalid
    if (!apiBaseUrl || apiBaseUrl === 'null') {
      console.warn("Invalid apiBaseUrl, cannot initiate session");
      return;
    }

    try {
      console.log("🔗 Initiating session on:", apiBaseUrl);
      
      // Create a JWT payload
      const payload = {
        userId: cognitoUserId,
        exp: Math.floor(Date.now() / 1000) + 60 * 60, // 1 hour from now
      };

      // Sign the JWT
      const header = { alg: "HS256", typ: "JWT" };
      const sHeader = JSON.stringify(header);
      const sPayload = JSON.stringify(payload);
      const encryptedUserId = KJUR.jws.JWS.sign(
        "HS256",
        sHeader,
        sPayload,
        SECRET_KEY
      );

      const response = await axios.post(
        `${apiBaseUrl}/initiate_session`,
        null,
        {
          headers: {
            "Content-Type": "application/json",
            "Encrypted-UUID": encryptedUserId,
          },
        }
      );

      const { sessionToken } = response.data;
      setSessionToken(sessionToken);
      localStorage.setItem("sessionToken", sessionToken);
      sessionInitiated.current = true;
      
      // Set as fully initialized after successful session initiation
      setIsFullyInitialized(true);
      console.log("✅ Session initiated successfully and fully initialized");
    } catch (error) {
      console.error("❌ Failed to initiate session:", error);
      // Don't set as initialized if session initiation failed
      setIsFullyInitialized(false);
    }
  }, [apiBaseUrl, isTestMode]);

  useEffect(() => {
    const fetchCurrentUserAndInitiateSession = async () => {
      if (!userId) {
        if (process.env.REACT_APP_ENABLE_AUTH === "false") {
          const exampleUserId = "example-user";
          setUserId(exampleUserId);
          await initiateSession(exampleUserId);
          return;
        }

        try {
          const currentUser = await getCurrentUser();
          const fetchedUserId = currentUser.userId;
          setUserId(fetchedUserId);

          const storedToken = localStorage.getItem("sessionToken");
          if (storedToken) {
            setSessionToken(storedToken);
            sessionInitiated.current = true;
            // In test mode, immediately set as initialized
            if (isTestMode) {
              setIsFullyInitialized(true);
            }
          } else {
            await initiateSession(fetchedUserId);
          }
        } catch (error) {
          console.error("Error fetching current user: ", error);
        }
      }
    };

    fetchCurrentUserAndInitiateSession();
  }, [userId, apiBaseUrl, initiateSession, isTestMode]);
  useEffect(() => {
    // Reset session when apiBaseUrl changes (machine switching)
    if (apiBaseUrl && sessionInitiated.current) {
      console.log('🔄 API Base URL changed, resetting session state');
      sessionInitiated.current = false;
      setIsFullyInitialized(false);
      
      // If we have a userId, initiate new session on new machine
      if (userId) {
        console.log('🔗 Initiating session on new machine:', apiBaseUrl);
        initiateSession(userId).then(() => {
          // In test mode, immediately set as initialized after session initiation
          if (isTestMode) {
            setTimeout(() => {
              console.log('🧪 TEST MODE: Quick initialization after machine switch');
              setIsFullyInitialized(true);
            }, 100);
          }
        });
      }
    }
  }, [apiBaseUrl, userId, initiateSession, isTestMode]);

  // Auto-unlock timeout to prevent permanent locks
  useEffect(() => {
    if (!isFullyInitialized && !isTestMode && sessionToken) {
      console.log("⏰ Starting auto-unlock timeout (30 seconds)");
      const timeoutId = setTimeout(() => {
        if (!isFullyInitialized) {
          console.warn("⚠️ Auto-unlocking input after timeout - session may not be fully initialized");
          setIsFullyInitialized(true);
        }
      }, 30000); // 30 second timeout

      return () => clearTimeout(timeoutId);
    }
  }, [isFullyInitialized, isTestMode, sessionToken]);

  return {
    userId,
    sessionToken,
    initiateSession,
    sessionInitiated,
    isFullyInitialized,
    setIsFullyInitialized,
  };
};
