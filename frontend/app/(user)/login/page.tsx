// Name: V.Hemanathan
// Describe: login component. Form for login.(components\user\LoginForm.tsx)
// Framework: Next.js -15.3.2 

import LoginForm from "@/components/user/LoginForm";
import Link from "next/link";

export default function LoginPage() {
  return (
    <div
      className="fixed inset-0 w-full h-full flex items-center justify-center p-4"
      style={{
        background: 'linear-gradient(135deg, #4fd1c5 0%, #a78bfa 50%, #f472b6 100%)',
        zIndex: 9999,
      }}
    >
      {/* Decorative geometric shapes for more dynamic background */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div
          className="absolute rounded-3xl"
          style={{
            top: '-25%',
            left: '-25%',
            width: '50%',
            height: '50%',
            background: 'linear-gradient(to bottom right, rgba(34, 211, 238, 0.3), transparent)',
            transform: 'rotate(12deg)',
          }}
        />
        <div
          className="absolute rounded-3xl"
          style={{
            bottom: '-25%',
            right: '-25%',
            width: '66%',
            height: '66%',
            background: 'linear-gradient(to top left, rgba(147, 51, 234, 0.3), transparent)',
            transform: 'rotate(-12deg)',
          }}
        />
        <div
          className="absolute rounded-3xl"
          style={{
            top: '33%',
            right: '0',
            width: '33%',
            height: '50%',
            background: 'linear-gradient(to left, rgba(232, 121, 249, 0.2), transparent)',
          }}
        />
      </div>

      <section
        className="h-[400px] w-full max-w-[320px] rounded-2xl overflow-hidden relative"
        style={{
          backgroundColor: '#ffffff',
          padding: '40px',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
          zIndex: 100,
        }}
      >
        <h1
          className="text-center font-bold tracking-tight"
          style={{
            fontSize: '1.25rem',
            marginBottom: '2.5rem',
            color: '#1f2937',
          }}
        >
          Login
        </h1>
        <LoginForm />

        {/* Social Login Section */}
        {/* <div className="text-center" style={{ marginTop: '2rem' }}>
          <p style={{ fontSize: '0.875rem', color: '#9ca3af', marginBottom: '1rem' }}>
            Or Sign Up Using
          </p>
          <div className="flex items-center justify-center" style={{ gap: '1rem' }}>
            {/* Facebook */}
        {/* <button
              type="button"
              className="flex items-center justify-center rounded-full transition-all duration-200 hover:-translate-y-0.5"
              style={{
                width: '48px',
                height: '48px',
                backgroundColor: '#3b5998',
                color: 'white',
                border: 'none',
                cursor: 'pointer',
                boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)',
              }}
              aria-label="Sign in with Facebook"
            >
              <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                <path d="M9.198 21.5h4v-8.01h3.604l.396-3.98h-4V7.5a1 1 0 0 1 1-1h3v-4h-3a5 5 0 0 0-5 5v2.01h-2l-.396 3.98h2.396v8.01Z" />
              </svg>
            </button> */}
        {/* Twitter */}
        {/* <button
              type="button"
              className="flex items-center justify-center rounded-full transition-all duration-200 hover:-translate-y-0.5"
              style={{
                width: '48px',
                height: '48px',
                backgroundColor: '#1da1f2',
                color: 'white',
                border: 'none',
                cursor: 'pointer',
                boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)',
              }}
              aria-label="Sign in with Twitter"
            >
              <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                <path d="M22.46 6c-.77.35-1.6.58-2.46.69a4.3 4.3 0 0 0 1.88-2.38 8.59 8.59 0 0 1-2.72 1.04 4.28 4.28 0 0 0-7.32 3.91A12.15 12.15 0 0 1 3.11 4.7a4.28 4.28 0 0 0 1.33 5.72c-.7-.02-1.36-.21-1.94-.53v.05a4.29 4.29 0 0 0 3.44 4.2 4.3 4.3 0 0 1-1.94.07 4.29 4.29 0 0 0 4 2.98A8.6 8.6 0 0 1 2 18.58a12.13 12.13 0 0 0 6.56 1.92c7.88 0 12.2-6.53 12.2-12.2 0-.19 0-.37-.01-.56A8.72 8.72 0 0 0 23 5.38a8.55 8.55 0 0 1-2.54.7Z" />
              </svg>
            </button> */}
        {/* Google */}
        {/* <button
              type="button"
              className="flex items-center justify-center rounded-full transition-all duration-200 hover:-translate-y-0.5"
              style={{
                width: '48px',
                height: '48px',
                backgroundColor: '#ea4335',
                color: 'white',
                border: 'none',
                cursor: 'pointer',
                boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)',
              }}
              aria-label="Sign in with Google"
            >
              <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                <path d="M21.35 11.1h-9.17v2.73h6.51c-.33 3.81-3.5 5.44-6.5 5.44-3.84 0-7.19-2.99-7.19-7.33 0-4.15 3.17-7.24 7.19-7.24 2.78 0 4.37 1.39 4.82 2.08l1.97-1.94C16.94 3.16 14.45 2 12 2 6.48 2 2 6.48 2 12s4.48 10 10 10c5.03 0 9.5-3.52 9.5-10 0-.56-.08-1.32-.15-1.9Z" />
              </svg>
            </button>
          </div>
        </div> */}

        {/* Sign Up Section */}
        {/* <div
          className="text-center"
          style={{
            marginTop: '2.5rem',
            paddingTop: '1.5rem',
            borderTop: '1px solid #f3f4f6',
          }}
        >
          <p style={{ fontSize: '0.875rem', color: '#9ca3af' }}>
            Or Sign Up Using
          </p>
          <Link
            href="#"
            className="block uppercase transition-colors hover:text-purple-600"
            style={{
              marginTop: '0.5rem',
              fontSize: '0.875rem',
              fontWeight: '600',
              color: '#4b5563',
              letterSpacing: '0.025em',
            }}
          >
            SIGN UP
          </Link>
        </div> */}
      </section>
    </div>
  );
}
