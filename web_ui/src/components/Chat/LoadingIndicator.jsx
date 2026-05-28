import React from 'react';
import gptImgLogo from '../../assets/Untitled.png';

const LoadingIndicator = ({ isLoading, loadingPrompt }) => {
    if (!isLoading) return null;

    return (
        <div className="chat bot loading-prompt">
            <img src={gptImgLogo} className="chatimg" alt="" />
            <div className="txt">
                <p>{loadingPrompt}</p>
                </div>
            </div>
    );
};

export default LoadingIndicator;