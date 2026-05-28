import React, { useState, useRef, useEffect } from "react";
import {
  User,
  ChevronDown,
  ChevronUp,
  Type,
  LogOut,
  Fingerprint,
  Bell,
  X,
  TextSelect,
} from "lucide-react";
import CopyableIdBox from "./CopyableIdBox";

const UserMenu = ({
  userEmail,
  onLogout,
  onFontChange,
  onFontSizeChange,
  associatedCid,
  hasRecommendation,
  recommendationContent,
  isOpen,
  setIsOpen,
}) => {
  const [isFontMenuOpen, setIsFontMenuOpen] = useState(false);
  const [isFontSizeMenuOpen, setIsFontSizeMenuOpen] = useState(false);
  const [isRecommendationOpen, setIsRecommendationOpen] = useState(false);
  const menuRef = useRef(null);
  const recommendationRef = useRef(null);
  const [showPopupNotification, setShowPopupNotification] = useState(false);
  const previousRecommendation = useRef(null);
  const [isSoundPlaying, setIsSoundPlaying] = useState(false);
  const previousNotificationId = useRef(null);

  const playNotificationSound = () => {
    const audioContext = new (window.AudioContext ||
      window.webkitAudioContext)();
    const oscillator = audioContext.createOscillator();
    const gainNode = audioContext.createGain();

    oscillator.connect(gainNode);
    gainNode.connect(audioContext.destination);

    oscillator.frequency.setValueAtTime(800, audioContext.currentTime);
    oscillator.frequency.exponentialRampToValueAtTime(
      300,
      audioContext.currentTime + 0.1
    );
    gainNode.gain.setValueAtTime(0.1, audioContext.currentTime);
    gainNode.gain.exponentialRampToValueAtTime(
      0.01,
      audioContext.currentTime + 0.1
    );

    oscillator.start();
    oscillator.stop(audioContext.currentTime + 0.2);
  };

  useEffect(() => {
    if (
      recommendationContent &&
      recommendationContent.id !== previousNotificationId.current
    ) {
      setShowPopupNotification(true);
      playNotificationSound();

      setTimeout(() => {
        setShowPopupNotification(false);
      }, 2000);

      previousNotificationId.current = recommendationContent.id;
    }
  }, [recommendationContent]);

  const toggleUserMenu = () => {
    setIsOpen(!isOpen);
    setIsFontMenuOpen(false);
    setIsFontSizeMenuOpen(false); // Close font size menu when closing user menu
  };

  const toggleFontMenu = (e) => {
    e.stopPropagation();
    setIsFontMenuOpen(!isFontMenuOpen);
    setIsFontSizeMenuOpen(false); // Close font size menu when opening font menu
  };

  const toggleFontSizeMenu = (e) => {
    e.stopPropagation();
    setIsFontSizeMenuOpen(!isFontSizeMenuOpen);
    setIsFontMenuOpen(false); // Close font menu when opening font size menu
  };

  const toggleRecommendation = (e) => {
    e.stopPropagation();
    if (hasRecommendation) {
      setIsRecommendationOpen(!isRecommendationOpen);
    }
  };

  const closeRecommendation = () => {
    setIsRecommendationOpen(false);
  };

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        if (!event.target.closest(".tutorial-bubble")) {
          setIsOpen(false);
        }
      }
      if (
        recommendationRef.current &&
        !recommendationRef.current.contains(event.target)
      ) {
        setIsRecommendationOpen(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [setIsOpen]);

  const truncateEmail = (email) => {
    const [username] = email.split("@");
    return username;
  };

  return (
    <div className="user-section" ref={menuRef}>
      
      {showPopupNotification && recommendationContent && (
        <div className="facebook-style-notification">
          <div className="notification-content">
            <strong>{recommendationContent.product_name}</strong>
            <p>{recommendationContent.notification}</p>
          </div>
        </div>
      )}
      <div className="user-info" onClick={toggleUserMenu}>
        <div className="user-avatar">
          <User size={20} />
        </div>
        <span className="userEmail">{truncateEmail(userEmail)}</span>
        <div className="notification-icon" onClick={toggleRecommendation}>
          <Bell size={16} />
          {hasRecommendation && <span className="notification-dot"></span>}
        </div>
        {isOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
      </div>

      {isRecommendationOpen && recommendationContent && (
        <div className="recommendation-popup-wrapper">
          <div className="recommendation-popup" ref={recommendationRef}>
            <button
              className="close-recommendation"
              onClick={closeRecommendation}
            >
              <X size={16} />
            </button>
            <h4>Notifications</h4>
            <p>
              <strong>{recommendationContent.product_name}</strong>:{" "}
              {recommendationContent.notification}
            </p>
          </div>
        </div>
      )}
      <div className={`user-menu upward ${isOpen ? "open" : ""}`}>
        <div className="menu-header">
          <div className="user-avatar large">
            <User size={30} />
          </div>
          <div className="user-details">
            <span className="user-email">{userEmail}</span>
          </div>
        </div>
        <div className="menu-items">
          <div className="menu-item" onClick={toggleFontMenu}>
            <Type size={16} />
            <span>Font</span>
            {isFontMenuOpen ? (
              <ChevronUp size={16} />
            ) : (
              <ChevronDown size={16} />
            )}
          </div>
          <div className={`submenu ${isFontMenuOpen ? "open" : ""}`}>
            <div
              className="menu-item"
              onClick={() => onFontChange("Arial, sans-serif")}
            >
              <Type size={16} />
              <span>Arial (Default)</span>
            </div>
            <div
              className="menu-item"
              onClick={() => onFontChange("'Inter', sans-serif")}
            >
              <Type size={16} />
              <span>Inter</span>
            </div>
            <div
              className="menu-item"
              onClick={() => onFontChange("'Roboto', sans-serif")}
            >
              <Type size={16} />
              <span>Roboto</span>
            </div>
            <div
              className="menu-item"
              onClick={() => onFontChange("'Open Sans', sans-serif")}
            >
              <Type size={16} />
              <span>Open Sans</span>
            </div>
            <div
              className="menu-item"
              onClick={() => onFontChange("'Montserrat', sans-serif")}
            >
              <Type size={16} />
              <span>Montserrat</span>
            </div>
          </div>

          {/* Font Size Menu */}
          <div className="menu-item" onClick={toggleFontSizeMenu}>
            <TextSelect size={16} />
            <span>Font Size</span>
            {isFontSizeMenuOpen ? (
              <ChevronUp size={16} />
            ) : (
              <ChevronDown size={16} />
            )}
          </div>
          <div className={`submenu ${isFontSizeMenuOpen ? "open" : ""}`}>
            <div
              className="menu-item"
              onClick={() => onFontSizeChange("small")}
            >
              <TextSelect size={14} />
              <span style={{ fontSize: "0.875rem" }}>Small</span>
            </div>
            <div
              className="menu-item"
              onClick={() => onFontSizeChange("normal")}
            >
              <TextSelect size={16} />
              <span>Normal</span>
            </div>
            <div
              className="menu-item"
              onClick={() => onFontSizeChange("large")}
            >
              <TextSelect size={18} />
              <span style={{ fontSize: "1.125rem" }}>Large</span>
            </div>
          </div>

          <div className="menu-item id-item">
            <span>
              <Fingerprint
                size={16}
                style={{ marginRight: "11px", verticalAlign: "middle" }}
              />
              Your ID:
            </span>
            <CopyableIdBox id={associatedCid} maxLength={12} />
          </div>
          <div className="menu-item" onClick={onLogout}>
            <LogOut size={16} />
            <span>Log Out</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default UserMenu;
