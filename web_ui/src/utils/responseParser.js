/**
 * Parses AI response text to extract structured information
 * @param {string} responseText - The raw response text from the AI
 * @returns {Object} - Parsed response with recommendation, diagnosis, steps, and other content
 */
export const parseAIResponse = (responseText) => {
  if (!responseText || typeof responseText !== 'string') {
    return {
      recommendation: null,
      diagnosis: null,
      steps: [],
      otherContent: responseText || '',
      hasStructuredContent: false
    };
  }

  let recommendation = null;
  let diagnosis = null;
  let steps = [];
  let otherContent = '';

  // Extract recommendation section (starts with "**Especially for you:**" and ends with "---")
  const recommendationMatch = responseText.match(/\*\*Especially for you:\*\*([\s\S]*?)(?=---|$)/i);
  if (recommendationMatch) {
    recommendation = recommendationMatch[1].trim();
    // Remove recommendation from the main text
    responseText = responseText.replace(/\*\*Especially for you:\*\*[\s\S]*?---/i, '').trim();
  }

  // Extract diagnosis (bold text that's not part of steps)
  const diagnosisMatches = responseText.match(/\*\*(.*?)\*\*/g);
  if (diagnosisMatches) {
    // Filter out step markers and other formatting, look for substantial diagnosis text
    const potentialDiagnosis = diagnosisMatches
      .map(match => match.replace(/\*\*/g, '').trim())
      .filter(text => 
        text.length > 20 && // Must be substantial text
        !text.match(/^Step \d+/) && // Not a step header
        !text.match(/^Here are/) && // Not the steps introduction
        !text.match(/^SecMate's/) // Not just product name
      );
    
    if (potentialDiagnosis.length > 0) {
      diagnosis = potentialDiagnosis[0];
    }
  }

  // Extract numbered steps
  const stepMatches = responseText.match(/^\d+\.\s+(.+?)(?=\n\d+\.|\n\n|$)/gm);
  if (stepMatches) {
    steps = stepMatches.map((step, index) => {
      // Remove the number and clean up the text
      const cleanStep = step.replace(/^\d+\.\s+/, '').trim();
      return {
        id: index + 1,
        text: cleanStep,
        completed: false
      };
    });
  } else {
    // Try alternative pattern for steps that might be on separate lines
    const alternativeStepMatches = responseText.match(/\d+\.\s+[^\n]+/g);
    if (alternativeStepMatches) {
      steps = alternativeStepMatches.map((step, index) => {
        const cleanStep = step.replace(/^\d+\.\s+/, '').trim();
        return {
          id: index + 1,
          text: cleanStep,
          completed: false
        };
      });
    }
  }

  // Extract other content (everything that's not recommendation, diagnosis, or steps)
  let remainingText = responseText;
  
  // Remove diagnosis if found
  if (diagnosis) {
    remainingText = remainingText.replace(new RegExp(`\\*\\*${diagnosis.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\*\\*`, 'g'), '');
  }
  
  // Remove steps
  if (stepMatches) {
    stepMatches.forEach(step => {
      remainingText = remainingText.replace(step, '');
    });
  }

  // Clean up remaining text
  otherContent = remainingText
    .replace(/\n{3,}/g, '\n\n') // Remove excessive line breaks
    .replace(/^\s*---\s*$/gm, '') // Remove separator lines
    .trim();

  const hasStructuredContent = !!(recommendation || diagnosis || steps.length > 0);

  return {
    recommendation,
    diagnosis,
    steps,
    otherContent,
    hasStructuredContent
  };
};

/**
 * Formats recommendation text for display
 * @param {string} recommendation - Raw recommendation text
 * @returns {Object} - Formatted recommendation with product and description
 */
export const formatRecommendation = (recommendation) => {
  if (!recommendation) return null;

  // Extract product name (usually in **bold**)
  const productMatch = recommendation.match(/\*\*([^*]+)\*\*/);
  const productName = productMatch ? productMatch[1] : null;

  // Clean up the recommendation text
  const cleanText = recommendation
    .replace(/\*\*/g, '') // Remove bold markers
    .trim();

  return {
    productName,
    description: cleanText,
    rawText: recommendation
  };
}; 