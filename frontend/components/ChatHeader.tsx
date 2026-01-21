'use client';

import { useProjects } from '@/actions/useProjects';

import Logout from '@/components/user/Logout';

interface ChatHeaderProps {
    title: string;
    selectedProjectId: string;
    onProjectChange: (projectId: string) => void;
    onMenuToggle: () => void;
}

export function ChatHeader({
    title,
    selectedProjectId,
    onProjectChange,
    onMenuToggle
}: ChatHeaderProps) {
    const { data: projectsData, isLoading } = useProjects();

    return (
        <header className="main-header">
            <div className="header-left">
                <button className="menu-toggle" onClick={onMenuToggle}>☰</button>
                <h2 className="chat-title">{title}</h2>
            </div>
            <div className="header-right">
                <div className="project-selector">
                    <label htmlFor="projectSelect">Project:</label>
                    <select
                        id="projectSelect"
                        value={selectedProjectId}
                        onChange={(e) => onProjectChange(e.target.value)}
                        disabled={isLoading}
                    >
                        <option value="">Select Project</option>
                        {projectsData?.projects.map((project) => (
                            <option key={project.id} value={project.id}>
                                {project.name}
                            </option>
                        ))}
                    </select>
                </div>
                <div className="date-range">
                    {isLoading
                        ? 'Loading dates...'
                        : projectsData?.dateRange
                            ? `${projectsData.dateRange.from} - ${projectsData.dateRange.to}`
                            : 'No data'}
                </div>
                <Logout className="w-auto px-4 py-2 bg-gradient-to-r from-red-600 to-rose-600 hover:from-red-700 hover:to-rose-700 text-white rounded-xl shadow-md hover:shadow-lg hover:-translate-y-0.5" />
            </div>
        </header>
    );
}
