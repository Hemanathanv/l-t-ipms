'use client';

import { useProjects } from '@/actions/useProjects';

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
            </div>
        </header>
    );
}
