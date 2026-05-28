import React, { useState, useEffect, useRef } from 'react';
import './TutorialBubble.css';

const TutorialBubble = ({ steps, onComplete, onStepChange }) => {
  const [currentStep, setCurrentStep] = useState(0);
  const [position, setPosition] = useState({ top: 0, right: 0 });
  const bubbleRef = useRef(null);


  useEffect(() => {
    if (currentStep < steps.length && steps[currentStep].selector) {
      const element = document.querySelector(steps[currentStep].selector);
      if (element && bubbleRef.current) {
        const rect = element.getBoundingClientRect();
        const bubbleRect = bubbleRef.current.getBoundingClientRect();
        
        let top = rect.bottom + window.scrollY + 10;
        let left = rect.left + window.scrollX + (rect.width / 2) - (bubbleRect.width / 2);

        if (top + bubbleRect.height > window.innerHeight) {
          top = rect.top + window.scrollY - bubbleRect.height + 50;
        }
        if (top + bubbleRect.height > window.innerHeight) {
          top = rect.top + window.scrollY - bubbleRect.height - 40;
        }
        if (left + bubbleRect.width > window.innerWidth) {
          left = window.innerWidth - bubbleRect.width - 10;
        }

        if (left < 0) {
          left = 295;
        }

        setPosition({ top, left });
      }
    } else {
      // Center the bubble for steps without a selector
      setPosition({
        top: '50%',
        left: '50%',
        transform: 'translate(-50%, -50%)'
      });
    }
    onStepChange(currentStep);
  }, [currentStep, steps, onStepChange]);

  const handleNext = () => {
    if (currentStep < steps.length - 1) {
      setCurrentStep(currentStep + 1);
    } else {
      onComplete();
    }
  };

  const handlePrevious = () => {
    if (currentStep > 0) {
      setCurrentStep(currentStep - 1);
    }
  };

  const handleClose = () => {
    onComplete();
  };

  return (
    <div 
    ref={bubbleRef}
    className="tutorial-bubble"
    style={{ top: position.top, left: position.left }}
  >
      <div className="tutorial-bubble-content">
        <button onClick={handleClose} className="close-button">×</button>
        <h3 className="tutorial-title">{steps[currentStep].title}</h3>
        <p className="tutorial-content">{steps[currentStep].content}</p>
        <div className="button-container">
          {currentStep > 0 && (
            <button onClick={handlePrevious} className="previous-button">Previous</button>
          )}
          <button onClick={handleNext} className="next-button">
            {currentStep === steps.length - 1 ? 'Finish' : 'Next'}
          </button>
        </div>
      </div>
      <div className="tutorial-bubble-arrow"></div>
    </div>
  );
};

export default TutorialBubble;