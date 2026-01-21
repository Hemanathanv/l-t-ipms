import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(request: NextRequest) {
    const sessionToken = request.cookies.get("session_token")?.value;
    const { pathname } = request.nextUrl;

    // Define paths that don't require authentication
    const publicPaths = ["/login", "/register", "/forgot-password"];
    const isPublicPath = publicPaths.some((path) => pathname.startsWith(path));

    // Define paths that should be ignored (assets, api, etc)
    if (
        pathname.startsWith("/_next") ||
        pathname.startsWith("/api") || // internal next api
        pathname.startsWith("/static") ||
        pathname.includes(".") // files with extensions
    ) {
        return NextResponse.next();
    }

    // If user is authenticated and tries to access login page, redirect to home
    if (sessionToken && isPublicPath) {
        return NextResponse.redirect(new URL("/", request.url));
    }

    // If user is NOT authenticated and tries to access a protected page, redirect to login
    if (!sessionToken && !isPublicPath) {
        return NextResponse.redirect(new URL("/login", request.url));
    }

    return NextResponse.next();
}

export const config = {
    matcher: [
        /*
         * Match all request paths except for the ones starting with:
         * - api (API routes)
         * - _next/static (static files)
         * - _next/image (image optimization files)
         * - favicon.ico (favicon file)
         */
        "/((?!api|_next/static|_next/image|favicon.ico).*)",
    ],
};
