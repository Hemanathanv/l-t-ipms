import LoginForm from "@/components/user/LoginForm";

export default function LoginPage() {
  return (
    <div
      className="fixed inset-0 w-full h-full flex items-center justify-center p-4 bg-cover bg-center bg-no-repeat"
      style={{
        backgroundImage: 'url(data:image/svg+xml,%3Csvg width="1200" height="800" xmlns="http://www.w3.org/2000/svg"%3E%3Crect fill="%23111827" width="1200" height="800"/%3E%3C/svg%3E)',
        backdropFilter: 'blur(10px)',
      }}
    >
      {/* Blurred overlay background */}
      <div
        className="absolute inset-0"
        style={{
          background: 'rgba(17, 24, 39, 0.4)',
          backdropFilter: 'blur(8px)',
        }}
      />

      {/* Login Card */}
      <section
        className="relative w-full max-w-[400px] rounded-lg overflow-hidden"
        style={{
          backgroundColor: 'rgba(255, 255, 255, 0.95)',
          padding: '48px',
          boxShadow: '0 10px 40px rgba(0, 0, 0, 0.2)',
          zIndex: 100,
          backdropFilter: 'blur(20px)',
        }}
      >
        <div className="text-center">
          <h1
            className="font-bold tracking-tight text-gray-900"
            style={{
              fontSize: '1.875rem',
              marginBottom: '0.5rem',
            }}
          >
            Welcome back
          </h1>
          <p
            className="text-gray-600"
            style={{
              fontSize: '0.875rem',
              marginBottom: '2rem',
            }}
          >
            Sign in to your account
          </p>
        </div>

        <LoginForm />
      </section>
    </div>
  );
}
