import React from "react";
import "./LoadingDots.css";

const LoadingDots = () => {
  return (
    <div className="flex items-center justify-center space-x-2">
      <div className="loading-dot"></div>
      <div className="loading-dot"></div>
      <div className="loading-dot"></div>
    </div>
  );
};

export default LoadingDots;
