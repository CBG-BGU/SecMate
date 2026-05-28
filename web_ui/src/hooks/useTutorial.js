import { useState } from "react";

export const useTutorial = (setIsUserMenuOpen) => {
  const [showTutorial, setShowTutorial] = useState(false);
  const [tutorialStep, setTutorialStep] = useState(0);

  const tutorialSteps = [
    {
      title: "Welcome to SecMate",
      content:
        "SecMate is your intelligent cybersecurity assistant. It uses advanced AI to help diagnose and solve computer issues, enhance your system's security, and provide personalized tech support.",
    },
    {
      title: "How SecMate Works",
      content:
        "SecMate can use context from a locally running Clue Collector service. The collector gathers relevant system information so the agent can provide more accurate and tailored assistance.",
    },
    {
      selector: ".user-info",
      title: "Your Account",
      content:
        "Access your account information here. You'll find your unique ID, which you'll need when using Clue Collector.",
    },
    {
      selector: ".id-item",
      title: "Your Unique ID",
      content:
        "This is your unique ID. Use it to link the locally running Clue Collector session to your SecMate account.",
    },
    {
      title: "Using Clue Collector",
      content:
        "Run Clue Collector locally and connect it with your unique ID. This links the collected data to your SecMate account, enabling personalized support.",
    },
    {
      selector: ".chat-input-area",
      title: "Interacting with SecMate",
      content:
        "Once set up, you can start chatting with SecMate here. Ask questions, describe issues, or request advice about your computer and cybersecurity.",
    },
  ];

  const handleTutorialStepChange = (step) => {
    setTutorialStep(step);
    const targetStep = tutorialSteps[step];

    // Explicitly open user menu when reaching the ID or account steps
    if (
      targetStep?.selector === ".id-item" ||
      targetStep?.selector === ".user-info"
    ) {
      setIsUserMenuOpen(true);
    } else {
      setIsUserMenuOpen(false);
    }
  };

  const handleTutorialComplete = () => {
    setShowTutorial(false);
    setTutorialStep(0);
    setIsUserMenuOpen(false);
  };

  return {
    showTutorial,
    setShowTutorial,
    tutorialStep,
    tutorialSteps,
    handleTutorialStepChange,
    handleTutorialComplete,
  };
};
