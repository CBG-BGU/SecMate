import React, { useState } from 'react';
import { ThumbsUp, ThumbsDown, Copy, Check, X } from 'lucide-react';
import './FeedbackButtons.css';

const FeedbackButtons = ({ messageId, onFeedback, messageText }) => {
  const [selectedFeedback, setSelectedFeedback] = useState(null);
  const [showNegativeFeedback, setShowNegativeFeedback] = useState(false);
  const [negativeReason, setNegativeReason] = useState('');
  const [additionalFeedback, setAdditionalFeedback] = useState('');
  const [isCopied, setIsCopied] = useState(false);

  const handleFeedback = (isPositive) => {
    setSelectedFeedback(isPositive ? 'positive' : 'negative');
    if (isPositive) {
      onFeedback(messageId, true);
    } else {
      setShowNegativeFeedback(true);
    }
  };

  const submitNegativeFeedback = () => {
    onFeedback(messageId, false, negativeReason, additionalFeedback);
    setShowNegativeFeedback(false);
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(messageText).then(() => {
      setIsCopied(true);
      setTimeout(() => setIsCopied(false), 2000);
    });
  };

  return (
    <div className="feedback-buttons">
      <button onClick={handleCopy} className="copy-btn" title="Copy message">
        {isCopied ? <Check /> : <Copy />}
      </button>
      <button 
        onClick={() => handleFeedback(true)} 
        className={`feedback-btn ${selectedFeedback === 'positive' ? 'selected' : ''}`} 
        title="Thumbs up"
      >
        <ThumbsUp />
      </button>
      <div className="thumbs-down-container">
        <button 
          onClick={() => handleFeedback(false)} 
          className={`feedback-btn ${selectedFeedback === 'negative' ? 'selected' : ''}`} 
          title="Thumbs down"
        >
          <ThumbsDown />
        </button>
        
        {showNegativeFeedback && (
          <div className="feedback-popup">
            <button onClick={() => setShowNegativeFeedback(false)} className="close-btn">
              <X size={16} />
            </button>
            <h3>Tell us more:</h3>
            <div className="reason-buttons">
              {['Not factually correct', 'Other'].map((reason) => (
                <button
                  key={reason}
                  onClick={() => setNegativeReason(reason)}
                  className={`reason-btn ${negativeReason === reason ? 'selected' : ''}`}
                >
                  {reason}
                </button>
              ))}
            </div>
            <textarea
              className="feedback-textarea"
              placeholder="Provide additional feedback"
              value={additionalFeedback}
              onChange={(e) => setAdditionalFeedback(e.target.value)}
            />
            <button onClick={submitNegativeFeedback} className="submit-btn">
              Submit
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default FeedbackButtons;