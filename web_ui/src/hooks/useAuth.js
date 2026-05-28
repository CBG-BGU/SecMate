import { useState, useEffect } from "react";
import { getCurrentUser, signOut } from "aws-amplify/auth";
import axios from "axios";

export const useAuth = (apiBaseUrl) => {
  const [userName, setUserName] = useState("");
  const [userEmail, setUserEmail] = useState("");

  const sendUserDataToApi = async (email, sessionToken, userId) => {
    // Skip if apiBaseUrl is null or invalid
    if (!apiBaseUrl || apiBaseUrl === 'null') {
      console.warn("Invalid apiBaseUrl, skipping user data save");
      return { success: false, reason: "Invalid API URL" };
    }

    try {
      const response = await axios.post(
        `${apiBaseUrl}/save_user_data`,
        {
          email: email,
          user_id: userId,
        },
        {
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${sessionToken}`,
          },
        }
      );
      return response.data;
    } catch (error) {
      throw error;
    }
  };

  const fetchUserInfo = async () => {
    if (process.env.REACT_APP_ENABLE_AUTH === "false") {
      setUserName("example-user");
      setUserEmail("example@example.edu");
      return;
    }

    try {
      const { username, signInDetails } = await getCurrentUser();
      setUserName(username);
      if (signInDetails && signInDetails.loginId) {
        setUserEmail(signInDetails.loginId);
      }
    } catch (error) {
      console.error("Error fetching user info: ", error);
    }
  };

  const handleLogout = async () => {
    try {
      await signOut();
    } catch (error) {
      console.error("Error signing out:", error);
    }
  };

  useEffect(() => {
    fetchUserInfo();
  }, []);

  return {
    userName,
    userEmail,
    handleLogout,
    fetchUserInfo,
    sendUserDataToApi,
  };
};
