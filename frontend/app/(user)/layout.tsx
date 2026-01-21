// Name: V.Hemanathan
// Describe: layout for authentication pages.
// Framework: Next.js -15.3.2 

import { getUserSession } from "@/actions/auth";
import { redirect } from "next/navigation";

export default async function AuthLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const response = await getUserSession();
  if (response?.user) {
    redirect("/");
  }
  
  return <>{children}</>;
}
