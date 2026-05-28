/*
 * Placeholder Amplify configuration for the release UI.
 *
 * The experiment deployment used AWS Cognito for participant login. Replace
 * these values with your own authentication provider configuration, or replace
 * the Authenticator wrapper in App.js with another login flow.
 */
const awsExports = {
  Auth: {
    Cognito: {
      userPoolId: process.env.REACT_APP_COGNITO_USER_POOL_ID || "",
      userPoolClientId: process.env.REACT_APP_COGNITO_USER_POOL_CLIENT_ID || "",
      identityPoolId: process.env.REACT_APP_COGNITO_IDENTITY_POOL_ID || "",
      loginWith: {
        email: true,
      },
    },
  },
};

export default awsExports;
