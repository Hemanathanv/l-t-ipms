// Name: V.Hemanathan
// Describe: This component is used to logout the user using Better Auth client.
// Framework: Next.js 16 - Better Auth

"use client"

import { LogOut } from "lucide-react"
import { motion, Transition } from "framer-motion"
import { useState } from "react"
import { signOut } from "@/lib/auth-client"
import { useQueryClient } from "@tanstack/react-query"
import { useRouter } from "next/navigation"

interface LogoutProps {
  className?: string;
}

const Logout = ({ className }: LogoutProps) => {
  const [isLoading, setIsLoading] = useState(false)
  const qc = useQueryClient()
  const router = useRouter()

  const handleLogout = async () => {
    setIsLoading(true)
    try {
      await qc.cancelQueries()
      qc.clear()
      await signOut()
      router.push("/login")
      router.refresh()
    } catch (error) {
      console.error("Error logging out:", error)
      setIsLoading(false)
    }
  }

  const hoverTransition: Transition = {
    type: "spring",
    stiffness: 400,
    damping: 17,
  };

  const tapTransition: Transition = {
    type: "spring",
    stiffness: 600,
    damping: 20,
  };

  const iconVariants = {
    idle: {
      scale: 1,
      rotate: 0,
      pathLength: 1,
      opacity: 1,
    },
    hover: {
      scale: 1.1,
      rotate: 5,
      pathLength: 1,
      opacity: 1,
      transition: hoverTransition,
    },
    tap: {
      scale: 0.95,
      transition: tapTransition,
    },
  }

  return (
    <button
      onClick={handleLogout}
      disabled={isLoading}
      className={`relative flex items-center gap-2 px-4 py-2 rounded-lg cursor-pointer outline-none group transition-all duration-200 ${className || "w-full text-left text-red-400 hover:text-red-500 hover:bg-red-500/10"}`}
    >
      <motion.div variants={iconVariants} initial="idle" whileHover="hover" className="relative flex-shrink-0">
        <LogOut
          size={18}
          className="currentColor"
        />
      </motion.div>

      <motion.span
        className="text-sm font-bold tracking-wide"
        animate={{
          x: 0,
        }}
        whileHover={{
          x: 2,
        }}
        transition={{ type: "spring", stiffness: 400, damping: 17 }}
      >
        {isLoading ? "Signing out..." : "Sign out"}
      </motion.span>

      {/* Loading indicator */}
      {isLoading && (
        <motion.div
          className="absolute right-3"
          animate={{ rotate: 360 }}
          transition={{
            duration: 1,
            repeat: Number.POSITIVE_INFINITY,
            ease: "linear",
          }}
        >
          <div className="w-3 h-3 border border-red-400 border-t-transparent rounded-full" />
        </motion.div>
      )}
    </button>
  );
}

export default Logout
