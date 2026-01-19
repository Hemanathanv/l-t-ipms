import { ChatContainer } from "@/components/ChatContainer";

interface ChatPageProps {
    params: Promise<{ threadId: string }>;
}

export default async function ChatPage({ params }: ChatPageProps) {
    const { threadId } = await params;
    return <ChatContainer initialThreadId={threadId} />;
}
