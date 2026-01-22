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
      <form onSubmit={handleSubmit} className="w-full flex flex-col gap-4" noValidate>
        {/* Email Field */}
        <div className="group relative">
          <label
            className="block text-sm font-medium text-gray-800 mb-2"
          >
            Email
          </label>
          <input
            type="email"
            placeholder="your@email.com"
            id="Email"
            name="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full px-4 py-3 bg-gray-50 border border-gray-300 rounded-lg text-gray-900 placeholder-gray-400 focus:outline-none focus:border-gray-500 focus:ring-1 focus:ring-gray-500 transition-colors"
            autoComplete="email"
          />
        </div>

        {/* Password Field */}
        <div className="group relative">
          <label
            className="block text-sm font-medium text-gray-800 mb-2"
          >
            Password
          </label>
          <input
            type="password"
            placeholder="••••••••"
            name="password"
            id="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full px-4 py-3 bg-gray-50 border border-gray-300 rounded-lg text-gray-900 placeholder-gray-400 focus:outline-none focus:border-gray-500 focus:ring-1 focus:ring-gray-500 transition-colors"
            autoComplete="current-password"
          />
          <div className="text-right mt-2">
            <a
              href="#"
              className="text-sm text-gray-600 hover:text-gray-900 transition-colors"
            >
              Forgot password?
            </a>
          </div>
        </div>

        {/* Login Button */}
        <div className="mt-6">
          <AuthButton type="login" loading={loading} disabled={isSubmitDisabled} />
        </div>

        {error && (
          <p className="text-sm text-red-600 text-center mt-3">
            {error}
          </p>
        )}
      </form>
    </div>
  );
};

export default LoginForm;
