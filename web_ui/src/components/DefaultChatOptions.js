import React from "react";
import { Turtle, ShieldAlert, Thermometer, MailWarning } from "lucide-react";
import "./ChatOptions.css";

const ChatOption = ({ icon: Icon, text, onClick }) => (
  <button className="chat-option" onClick={onClick}>
    <Icon className="chat-option-icon" />
    <span className="chat-option-text">{text}</span>
  </button>
);

const DefaultChatOptions = ({ onOptionSelect }) => {
  const options = [
    {
      icon: Turtle,
      text: "Why is my PC running slow?",
      handler: () => onOptionSelect("Why is my PC running slow?"),
    },
    {
      icon: ShieldAlert,
      text: "How can I tell if my computer has a virus?",
      handler: () =>
        onOptionSelect("How can I tell if my computer has a virus?"),
    },
    {
      icon: Thermometer,
      text: "Why is my PC overheating",
      handler: () => onOptionSelect("Why is my PC overheating"),
    },
    {
      icon: MailWarning,
      text: "How to recognize phishing attempts?",
      handler: () =>
        onOptionSelect("How can I recognize and avoid phishing attempts?"),
    },
  ];

  return (
    <div className="default-chat-options">
      {options.map((option, index) => (
        <ChatOption
          key={index}
          icon={option.icon}
          text={option.text}
          onClick={option.handler}
        />
      ))}
    </div>
  );
};

export default DefaultChatOptions;
