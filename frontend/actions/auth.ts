// Name: V.Hemanathan
// Describe: Server side authentication actions using FastAPI backend
// Framework: Next.js 16 - FastAPI

"use server";

import { headers } from "next/headers";
import { revalidatePath } from "next/cache";
import { API_BASE } from "@/lib/api";

type User = {
  id: string;
  name: string;
  email: string;
  systemRole: string;
  isActive: boolean;
};

type SessionData = {
  user: User | null;
  status: "success" | "error";
  session?: any;
};

/**
 * Get the current user session from FastAPI backend
 */
export async function getUserSession(): Promise<SessionData | null> {
  try {
    const headersList = await headers();
    const cookieHeader = headersList.get("cookie");

    const response = await fetch(`${API_BASE}/auth/session`, {
      headers: {
        Cookie: cookieHeader || "",
      },
      cache: "no-store",
    });

    if (!response.ok) {
      return null;
    }

    const data = await response.json();
    if (!data.user) {
      return null;
    }

    return {
      status: "success",
      user: data.user,
      session: {}, // Placeholder
    };
  } catch (error) {
    console.error("Error getting session:", error);
    return null;
  }
}

/**
 * Check if the current user is a system admin
 */
export async function isCurrentUserAdmin(): Promise<boolean> {
  const session = await getUserSession();
  return session?.user?.systemRole === "ADMIN";
}

/**
 * Server-side sign out
 */
export async function serverSignOut() {
  try {
    const headersList = await headers();
    const cookieHeader = headersList.get("cookie");

    await fetch(`${API_BASE}/auth/logout`, {
      method: "POST",
      headers: {
        Cookie: cookieHeader || "",
      },
    });

    revalidatePath("/", "layout");
    return { status: "success" };
  } catch (error) {
    console.error("Error signing out:", error);
    return { status: "error", message: "Failed to sign out" };
  }
}

// Other actions (updateUserProfile, sendProjectInvite, etc.) are removed/commented
// as they depend on the old Prisma client structure or need migration to FastAPI endpoints.
// For this task, we focus on core auth.