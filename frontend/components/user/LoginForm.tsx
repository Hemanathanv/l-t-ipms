"use client";
import React, { useState } from "react";
import AuthButton from "./AuthButton";
import { useRouter } from "next/navigation";
import { signIn } from "@/lib/auth-client";
import { User, Lock } from "lucide-react";

const LoginForm: React.FC = () => {
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  const [loading, setLoading] = useState<boolean>(false);

  // controlled inputs
  const [email, setEmail] = useState<string>("");
  const [password, setPassword] = useState<string>("");

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();
    setLoading(true);
    setError(null);

    // basic local validation (UX)
    if (!email.trim() || !password) {
      setError("Please enter email and password.");
      setLoading(false);
      return;
    }

    try {
      const result = await signIn.email({
        email: email.trim(),
        password,
      });

      if (result.error) {
        setError(result.error.message || "Login failed");
      } else {
        router.refresh();
        router.push("/");
      }
    } catch (err) {
      if (err instanceof Error) setError(err.message);
      else setError(String(err ?? "Login failed"));
    } finally {
      setLoading(false);
    }
  };

  // disable when loading or required fields empty
  const isSubmitDisabled = loading || !email.trim() || !password;

  return (
    <div>
      <form onSubmit={handleSubmit} className="w-full flex flex-col" style={{ gap: '1.5rem' }} noValidate>
        {/* Username Field */}
        <div className="group relative">
          <label
            className="block uppercase tracking-wide transition-colors"
            style={{
              fontSize: '0.75rem',
              fontWeight: '700',
              color: '#6b7280',
              marginBottom: '0.5rem',
            }}
          >
            Email
          </label>
          <div className="relative flex items-center">
            <User
              className="absolute pointer-events-none transition-colors"
              style={{
                left: '0',
                top: '50%',
                transform: 'translateY(-50%)',
                width: '20px',
                height: '20px',
                color: '#9ca3af',
              }}
            />
            <input
              type="email"
              placeholder="Type your username"
              id="Email"
              name="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              style={{
                width: '100%',
                paddingLeft: '2rem',
                paddingTop: '0.5rem',
                paddingBottom: '0.5rem',
                backgroundColor: 'transparent',
                borderTop: 'none',
                borderLeft: 'none',
                borderRight: 'none',
                borderBottom: '1px solid #d1d5db',
                color: '#374151',
                fontSize: '0.875rem',
                outline: 'none',
              }}
              autoComplete="email"
            />
          </div>
        </div>

        {/* Password Field */}
        <div className="group relative">
          <label
            className="block uppercase tracking-wide transition-colors"
            style={{
              fontSize: '0.75rem',
              fontWeight: '700',
              color: '#6b7280',
              marginBottom: '0.5rem',
            }}
          >
            Password
          </label>
          <div className="relative flex items-center">
            <Lock
              className="absolute pointer-events-none transition-colors"
              style={{
                left: '0',
                top: '50%',
                transform: 'translateY(-50%)',
                width: '20px',
                height: '20px',
                color: '#9ca3af',
              }}
            />
            <input
              type="password"
              placeholder="Type your password"
              name="password"
              id="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              style={{
                width: '100%',
                paddingLeft: '2rem',
                paddingTop: '0.5rem',
                paddingBottom: '0.5rem',
                backgroundColor: 'transparent',
                borderTop: 'none',
                borderLeft: 'none',
                borderRight: 'none',
                borderBottom: '1px solid #d1d5db',
                color: '#374151',
                fontSize: '0.875rem',
                outline: 'none',
              }}
              autoComplete="current-password"
            />
          </div>
          <div className="text-right" style={{ marginTop: '0.5rem' }}>
            <a
              href="#"
              className="hover:underline"
              style={{
                fontSize: '0.75rem',
                color: '#9ca3af',
              }}
            >
              Forgot password?
            </a>
          </div>
        </div>

        {/* Login Button */}
        <div style={{ marginTop: '1rem' }}>
          <AuthButton type="login" loading={loading} disabled={isSubmitDisabled} />
        </div>

        {error && (
          <p style={{ color: '#ef4444', fontSize: '0.875rem', textAlign: 'center' }}>
            {error}
          </p>
        )}
      </form>
    </div>
  );
};

export default LoginForm;
