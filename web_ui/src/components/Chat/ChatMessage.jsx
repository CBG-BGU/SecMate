import React, { useState, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import { ArrowRight, ArrowLeft, CheckCircle, AlertCircle } from "lucide-react";
import FeedbackButtons from "../FeedbackButtons";
import userIcon from "../../assets/user-icon.png";
import gptImgLogo from "../../assets/Untitled.png";
import { parseAIResponse } from "../../utils/responseParser";
import "../ChatMessage.css";

const ChatMessage = ({
  message,
  index,
  currentStepIndices,
  onHover,
  onLeaveHover,
  onNextStep,
  onFeedback,
  onRecommendationDetected,
}) => {
  const [parsedContent, setParsedContent] = useState(null);
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [completedSteps, setCompletedSteps] = useState(new Set());

  useEffect(() => {
    if (message.isBot && message.text) {
      // Check if we have pre-parsed content (from useChat)
      if (message.parsedContent !== undefined) {
        setParsedContent(message.parsedContent);
        
        // Call recommendation callback if there's a recommendation
        if (message.parsedContent && message.parsedContent.recommendation && onRecommendationDetected) {
          onRecommendationDetected(message.parsedContent.recommendation);
        }
      } else {
        // Fallback: parse the message text directly (for legacy messages)
        const parsed = parseAIResponse(message.text);
        setParsedContent(parsed);
        
        // Call recommendation callback if there's a recommendation
        if (parsed.recommendation && onRecommendationDetected) {
          onRecommendationDetected(parsed.recommendation);
        }
      }
    }
  }, [message.text, message.parsedContent, onRecommendationDetected]);

  const handleNextStep = () => {
    if (parsedContent && currentStepIndex < parsedContent.steps.length - 1) {
      setCurrentStepIndex(currentStepIndex + 1);
    }
  };

  const handlePreviousStep = () => {
    if (currentStepIndex > 0) {
      setCurrentStepIndex(currentStepIndex - 1);
    }
  };

  const handleStepComplete = (stepIndex) => {
    const newCompleted = new Set(completedSteps);
    if (newCompleted.has(stepIndex)) {
      newCompleted.delete(stepIndex);
    } else {
      newCompleted.add(stepIndex);
    }
    setCompletedSteps(newCompleted);
  };

  const renderStepNavigation = () => {
    if (!parsedContent || parsedContent.steps.length === 0) return null;

    const currentStep = parsedContent.steps[currentStepIndex];
    const isLastStep = currentStepIndex === parsedContent.steps.length - 1;
    const hasNextStep = currentStepIndex < parsedContent.steps.length - 1;
    const hasPreviousStep = currentStepIndex > 0;

    return (
      <div className="step-navigation-container">
        <div className="step-header">
          <div className="step-counter">
            Step {currentStepIndex + 1} of {parsedContent.steps.length}
          </div>
          <div className="step-progress-bar">
            <div 
              className="step-progress-fill" 
              style={{ width: `${((currentStepIndex + 1) / parsedContent.steps.length) * 100}%` }}
            />
          </div>
        </div>

        <div className="current-step">
          <div className="step-content">
            <div className="step-text">
              <strong>Step {currentStep.id}:</strong> {currentStep.text}
            </div>
            <button
              className={`step-complete-btn ${completedSteps.has(currentStepIndex) ? 'completed' : ''}`}
              onClick={() => handleStepComplete(currentStepIndex)}
              title={completedSteps.has(currentStepIndex) ? 'Mark as incomplete' : 'Mark as complete'}
            >
              <CheckCircle size={16} />
              {completedSteps.has(currentStepIndex) ? 'Completed' : 'Mark Complete'}
            </button>
          </div>
        </div>

        <div className="step-navigation-buttons">
          <button
            className="step-nav-btn prev"
            onClick={handlePreviousStep}
            disabled={!hasPreviousStep}
          >
            <ArrowLeft size={16} />
            Previous
          </button>
          
          {hasNextStep ? (
            <button
              className="step-nav-btn next"
              onClick={handleNextStep}
            >
              Next
              <ArrowRight size={16} />
            </button>
          ) : (
            <div className="completion-section">
              <div className="steps-completed-message">
                All steps completed! 
              </div>
            </div>
          )}
        </div>

        {/* Steps Overview */}
        <div className="steps-overview">
          {parsedContent.steps.map((step, index) => (
            <div
              key={index}
              className={`step-indicator ${index === currentStepIndex ? 'current' : ''} ${completedSteps.has(index) ? 'completed' : ''}`}
              onClick={() => setCurrentStepIndex(index)}
              title={`Step ${index + 1}: ${step.text.substring(0, 50)}...`}
            >
              {index + 1}
            </div>
          ))}
        </div>
      </div>
    );
  };

  const renderDiagnosis = () => {
    if (!parsedContent || !parsedContent.diagnosis) return null;

    return (
      <div className="diagnosis-section">
        <div className="diagnosis-header">
          <AlertCircle className="diagnosis-icon" />
          <strong>Issue Identified</strong>
        </div>
        <p className="diagnosis-text">{parsedContent.diagnosis}</p>
      </div>
    );
  };

  const renderOtherContent = () => {
    if (!parsedContent || !parsedContent.otherContent) return null;

    return (
      <div className="other-content">
        <ReactMarkdown>{parsedContent.otherContent}</ReactMarkdown>
      </div>
    );
  };

  return (
    <div
      className={`chat ${message.isBot ? "bot" : "user"}`}
      onMouseEnter={() => onHover(index)}
      onMouseLeave={() => onLeaveHover(index)}
    >
      {message.isBot ? (
        <>
          <img src={gptImgLogo} className="chatimg" alt="" />
          <div className="txt">
            <div className="message-content">
              {parsedContent && parsedContent.hasStructuredContent ? (
                <div className="structured-response">
                  {/* Show diagnosis */}
                  {renderDiagnosis()}
                  
                  {/* Show other content */}
                  {renderOtherContent()}
                  
                  {/* Show step navigation if there are steps */}
                  {parsedContent.steps.length > 0 && renderStepNavigation()}
                </div>
              ) : (
                // Fallback to original rendering for non-structured content
                // This includes config 'e' (Raw GPT) which skips parsing and legacy message formats
                <>
                  {message.diagnosis && (
                    <div className="diagnosis-section">
                      <p className="diagnosis">{message.diagnosis}</p>
                      {message.actionSteps && message.actionSteps.length > 0 && (
                        <p className="action-intro">
                          Let's follow{" "}
                          {message.actionSteps.length > 1 ? "these steps" : "this step"}{" "}
                          to address the issue:
                        </p>
                      )}
                    </div>
                  )}
                  {message.actionSteps && message.actionSteps.length > 0 ? (
                    <div className="action-steps-container">
                      {message.actionSteps.length === 1 ? (
                        <p className="action-step">{message.actionSteps[0]}</p>
                      ) : (
                        message.actionSteps
                          .slice(0, currentStepIndices[index] + 1 || 1)
                          .map((step, stepIndex) => (
                            <p key={stepIndex} className="action-step">
                              <strong>Step {stepIndex + 1}:</strong> {step}
                            </p>
                          ))
                      )}
                      {message.actionSteps.length > 1 &&
                        (currentStepIndices[index] + 1 || 1) < message.actionSteps.length && (
                        <button
                          onClick={() => onNextStep(index)}
                          className="next-step-btn"
                        >
                          Next step
                          <ArrowRight size={16} />
                        </button>
                      )}
                    </div>
                  ) : (
                    <ReactMarkdown>{message.text || ""}</ReactMarkdown>
                  )}
                </>
              )}
            </div>
            {index !== 0 && (
              <FeedbackButtons
                messageId={index}
                onFeedback={onFeedback}
                messageText={message.text || ""}
              />
            )}
          </div>
        </>
      ) : (
        <>
          <div className="txt">
            <div className="message-content">
              <ReactMarkdown>{message.text || ""}</ReactMarkdown>
            </div>
          </div>
          <img src={userIcon} className="chatimg" alt="" />
        </>
      )}
    </div>
  );
};

export default ChatMessage;
