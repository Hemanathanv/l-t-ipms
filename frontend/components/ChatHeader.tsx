'use client';

import { useState } from 'react';
import { ChevronDown, Sparkles, Check, Menu } from 'lucide-react';
import { useProjects } from '@/actions/useProjects';
import { useSidebar } from '@/components/ui/sidebar';
import Logout from '@/components/user/Logout';

interface ChatHeaderProps {
    title: string;
    selectedProjectKey: string;
    onProjectChange: (projectKey: string) => void;
    hideBorder?: boolean;
}

const versions = [
    {
        id: 'pro',
        name: 'L&T-IPMS Pro',
        description: 'Advanced analytics & more',
        isPro: true
    },
    {
        id: 'standard',
        name: 'IPMS 1.0',
        description: 'Standard model',
        isPro: false
    },
];

export function ChatHeader({
    title,
    selectedProjectKey,
    onProjectChange,
    hideBorder = false,
}: ChatHeaderProps) {
    const { data: projectsData, isLoading } = useProjects();
    const { state, isMobile, toggleSidebar } = useSidebar();
    const isCollapsed = state === 'collapsed';
    const [selectedVersion, setSelectedVersion] = useState(versions[1]); // Default to standard
    const [isVersionDropdownOpen, setIsVersionDropdownOpen] = useState(false);

    const handleUpgrade = (e: React.MouseEvent) => {
        e.stopPropagation();
        // TODO: Implement upgrade logic
        alert('Upgrade to Pro coming soon!');
    };


    return (
        <header
            className={`main-header ${hideBorder ? 'no-border' : ''}`}
            style={{
                paddingLeft: isMobile ? '16px' : (isCollapsed ? 'calc(var(--sidebar-width-icon, 3rem) + 24px)' : '24px'),
                transition: 'padding-left 300ms ease-in-out',
            }}
        >
            <div className="header-left">
                {/* Mobile Menu Button - only visible on mobile */}
                {isMobile && (
                    <button
                        className="mobile-menu-btn"
                        onClick={toggleSidebar}
                        aria-label="Open menu"
                    >
                        <Menu size={24} />
                    </button>
                )}

                {/* Version Selector Dropdown - ChatGPT style */}
                <div className="version-selector">
                    <button
                        className="version-button"
                        onClick={() => setIsVersionDropdownOpen(!isVersionDropdownOpen)}
                        onBlur={() => setTimeout(() => setIsVersionDropdownOpen(false), 200)}
                    >
                        <span className="version-name">{selectedVersion.name}</span>
                        <ChevronDown size={16} className={`version-chevron ${isVersionDropdownOpen ? 'open' : ''}`} />
                    </button>
                    {isVersionDropdownOpen && (
                        <div className="version-dropdown">
                            {versions.map((version) => (
                                <div
                                    key={version.id}
                                    className={`version-card ${selectedVersion.id === version.id ? 'active' : ''}`}
                                    onClick={() => {
                                        if (!version.isPro) {
                                            setSelectedVersion(version);
                                            setIsVersionDropdownOpen(false);
                                        }
                                    }}
                                >
                                    <div className="version-card-left">
                                        {version.isPro && (
                                            <Sparkles size={18} className="version-pro-icon" />
                                        )}
                                        <div className="version-card-info">
                                            <span className="version-card-name">{version.name}</span>
                                            <span className="version-card-desc">{version.description}</span>
                                        </div>
                                    </div>
                                    <div className="version-card-right">
                                        {version.isPro ? (
                                            <button className="upgrade-btn" onClick={handleUpgrade}>
                                                Upgrade
                                            </button>
                                        ) : (
                                            selectedVersion.id === version.id && (
                                                <Check size={18} className="version-check" />
                                            )
                                        )}
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>

            <div className="header-right">
                <div className="project-selector">
                    <label htmlFor="projectSelect">Project:</label>
                    <select
                        id="projectSelect"
                        value={selectedProjectKey}
                        onChange={(e) => onProjectChange(e.target.value)}
                        disabled={isLoading}
                    >
                        <option value="">Select Project</option>
                        {projectsData?.projects.map((project) => (
                            <option key={project.project_key} value={project.project_key}>
                                {project.name}
                            </option>
                        ))}
                    </select>
                </div>
                <Logout className="w-auto px-4 py-2 bg-gradient-to-r from-red-600 to-rose-600 hover:from-red-700 hover:to-rose-700 text-white rounded-xl shadow-md hover:shadow-lg hover:-translate-y-0.5" />
            </div>
        </header>
    );
}
