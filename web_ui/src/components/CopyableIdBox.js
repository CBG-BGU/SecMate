import React, { useState } from 'react';
import { Copy, Check } from 'lucide-react';

const CopyableIdBox = ({ id, maxLength = 12 }) => {
  const [isCopied, setIsCopied] = useState(false);

  const handleCopy = () => {
    if (id) {
      navigator.clipboard.writeText(id).then(() => {
        setIsCopied(true);
        setTimeout(() => setIsCopied(false), 2000);
      });
    }
  };

  const truncatedId = id 
    ? id.length > maxLength 
      ? `${id.slice(0, maxLength)}...` 
      : id
    : 'Not generated';

  return (
    <div className="copyable-id-box">
      <div className="id-display" title={id || 'ID not generated'}>
        {truncatedId}
      </div>
      <button className="copy-button" onClick={handleCopy} title="Copy ID" disabled={!id}>
        {isCopied ? <Check size={16} /> : <Copy size={16} />}
      </button>
    </div>
  );
};

export default CopyableIdBox;