// Name: V.Hemanathan
// Describe: This component is used to display the authentication buttons for login, sign up, reset password, and forgot password. It uses the server action declared in the actions/auth.ts file.
// Framework: Next.js -15.3.2 

import React from "react";

const AuthButton = ({
  type,
  loading,
  disabled
}: {
  type: "login" | "Sign up" | "Reset Password" | "Forgot Password" | "Join Team" | "Send Reset Link";
  loading: boolean;
  disabled: boolean;
}) => {
  return (
    <button
      disabled={loading || disabled}
      type="submit"
      className={`
        relative w-full px-8 py-3 
        bg-gradient-to-r from-cyan-400 to-purple-600 hover:from-cyan-500 hover:to-purple-700
        text-white font-bold text-sm tracking-widest uppercase
        rounded-full shadow-lg hover:shadow-xl hover:-translate-y-0.5
        transition-all duration-200 ease-out
        disabled:opacity-70 disabled:cursor-not-allowed disabled:transform-none disabled:shadow-none
        flex items-center justify-center gap-2
      `}
    >
      {loading ? (
        <>
          <svg className="animate-spin -ml-1 mr-2 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
          PROCESSING...
        </>
      ) : (
        "LOGIN"
      )}
    </button>
  );
};

export default AuthButton;
