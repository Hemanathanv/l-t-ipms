'use client';

import React, { useMemo, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { AllCommunityModule, ModuleRegistry, ColDef, ValueFormatterParams, themeAlpine } from 'ag-grid-community';
import { AgGridReact } from 'ag-grid-react';
import {
    useAdminDashboard,
    type MessageRow,
    type TokenUsageSummary,
} from '@/actions/useAdminDashboard';
import {
    Zap,
    ArrowDownToLine,
    ArrowUpFromLine,
    MessageSquare,
    MessagesSquare,
    Wrench,
    Timer,
    ArrowLeft,
    Download
} from 'lucide-react';

// Register AG Grid Community modules
ModuleRegistry.registerModules([AllCommunityModule]);

/* ───────────────────── Stat Card ───────────────────── */

interface StatCardProps {
    title: string;
    value: string | number;
    subtitle?: string;
    icon: React.ReactNode;
    gradient: string;
}

function StatCard({ title, value, subtitle, icon, gradient }: StatCardProps) {
    return (
        <div className="admin-stat-card" style={{ background: gradient }}>
            <div className="admin-stat-icon">{icon}</div>
            <div className="admin-stat-info">
                <span className="admin-stat-value">{value}</span>
                <span className="admin-stat-title">{title}</span>
                {subtitle && <span className="admin-stat-subtitle">{subtitle}</span>}
            </div>
        </div>
    );
}

/* ───────────────── Number Formatter ───────────────── */

function fmtNum(n: number): string {
    if (n >= 1_000_000) return (n / 1_000_000).toFixed(2) + 'M';
    if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K';
    return n.toLocaleString();
}

/* ────────────────── Role Badge Renderer ────────────── */

function RoleCellRenderer(params: { value: string }) {
    const role = params.value;
    const cls = `role-badge role-${role}`;
    return <span className={cls}>{role}</span>;
}

/* ─────────────────── Main Page ─────────────────────── */

export default function AdminDashboardPage() {
    const { data, isLoading, isError, error } = useAdminDashboard();
    const router = useRouter();

    /* AG Grid column definitions */
    const columnDefs = useMemo<ColDef<MessageRow>[]>(() => [
        {
            headerName: 'Role',
            field: 'role',
            width: 120,
            filter: true,
            cellRenderer: RoleCellRenderer,
        },
        {
            headerName: 'Content',
            field: 'content',
            flex: 2,
            minWidth: 250,
            filter: true,
            tooltipField: 'content',
        },
        {
            headerName: 'Input Tokens',
            field: 'input_tokens',
            width: 130,
            filter: 'agNumberColumnFilter',
            sortable: true,
            valueFormatter: (p: ValueFormatterParams) => p.value ? p.value.toLocaleString() : '—',
        },
        {
            headerName: 'Output Tokens',
            field: 'output_tokens',
            width: 140,
            filter: 'agNumberColumnFilter',
            sortable: true,
            valueFormatter: (p: ValueFormatterParams) => p.value ? p.value.toLocaleString() : '—',
        },
        {
            headerName: 'Total Tokens',
            field: 'total_tokens',
            width: 130,
            filter: 'agNumberColumnFilter',
            sortable: true,
            valueFormatter: (p: ValueFormatterParams) => p.value ? p.value.toLocaleString() : '—',
        },
        {
            headerName: 'Tool Name',
            field: 'tool_name',
            width: 160,
            filter: true,
            valueFormatter: (p: ValueFormatterParams) => p.value || '—',
        },
        {
            headerName: 'Model',
            field: 'model',
            width: 180,
            filter: true,
            valueFormatter: (p: ValueFormatterParams) => p.value || '—',
        },
        {
            headerName: 'Latency (ms)',
            field: 'latency_ms',
            width: 130,
            filter: 'agNumberColumnFilter',
            sortable: true,
            valueFormatter: (p: ValueFormatterParams) => p.value != null ? `${p.value}` : '—',
        },
        {
            headerName: 'Feedback',
            field: 'feedback',
            width: 110,
            filter: true,
            valueFormatter: (p: ValueFormatterParams) => p.value || '—',
        },
        {
            headerName: 'Date',
            field: 'created_at',
            width: 180,
            sortable: true,
            filter: true,
            valueFormatter: (p: ValueFormatterParams) => {
                if (!p.value) return '—';
                return new Date(p.value).toLocaleString();
            },
        },
    ], []);

    const defaultColDef = useMemo<ColDef>(() => ({
        resizable: true,
        sortable: true,
    }), []);

    const onBtnExport = useCallback(() => {
        const gridApi = (document.querySelector('.ag-root') as any)?.__agGridApi;
        // Fallback: use the grid ref approach below
    }, []);

    const gridRef = React.useRef<AgGridReact>(null);

    const handleExportCsv = useCallback(() => {
        gridRef.current?.api?.exportDataAsCsv({
            fileName: 'token_usage_report.csv',
        });
    }, []);

    /* ─── Loading & Error States ─── */

    if (isLoading) {
        return (
            <div className="admin-dashboard">
                <div className="admin-loading">
                    <div className="admin-spinner" />
                    <p>Loading dashboard data...</p>
                </div>
            </div>
        );
    }

    if (isError) {
        return (
            <div className="admin-dashboard">
                <div className="admin-error">
                    <h2>Access Denied</h2>
                    <p>{(error as Error)?.message || 'Failed to load dashboard'}</p>
                    <button onClick={() => router.push('/')} className="admin-back-btn">
                        <ArrowLeft size={16} /> Go Back
                    </button>
                </div>
            </div>
        );
    }

    const summary: TokenUsageSummary = data!.summary;
    const messages: MessageRow[] = data!.messages;

    return (
        <div className="admin-dashboard">
            {/* Header */}
            <header className="admin-header">
                <div className="admin-header-left">
                    <button onClick={() => router.push('/')} className="admin-back-btn">
                        <ArrowLeft size={18} />
                    </button>
                    <div>
                        <h1 className="admin-title">Token Usage Dashboard</h1>
                        <p className="admin-subtitle">AI consumption analytics & message details</p>
                    </div>
                </div>
                <button onClick={handleExportCsv} className="admin-export-btn">
                    <Download size={16} />
                    Export CSV
                </button>
            </header>

            {/* Stat Cards */}
            <div className="admin-cards-grid">
                <StatCard
                    title="Total Tokens"
                    value={fmtNum(summary.total_tokens)}
                    subtitle="All-time usage"
                    icon={<Zap size={24} />}
                    gradient="linear-gradient(135deg, #667eea 0%, #764ba2 100%)"
                />
                <StatCard
                    title="Input Tokens"
                    value={fmtNum(summary.total_input_tokens)}
                    subtitle="Prompts sent"
                    icon={<ArrowDownToLine size={24} />}
                    gradient="linear-gradient(135deg, #f093fb 0%, #f5576c 100%)"
                />
                <StatCard
                    title="Output Tokens"
                    value={fmtNum(summary.total_output_tokens)}
                    subtitle="Responses generated"
                    icon={<ArrowUpFromLine size={24} />}
                    gradient="linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)"
                />
                <StatCard
                    title="Messages"
                    value={fmtNum(summary.total_messages)}
                    subtitle="Total messages"
                    icon={<MessageSquare size={24} />}
                    gradient="linear-gradient(135deg, #43e97b 0%, #38f9d7 100%)"
                />
                <StatCard
                    title="Conversations"
                    value={fmtNum(summary.total_conversations)}
                    subtitle="Chat threads"
                    icon={<MessagesSquare size={24} />}
                    gradient="linear-gradient(135deg, #fa709a 0%, #fee140 100%)"
                />
                <StatCard
                    title="Tool Calls"
                    value={fmtNum(summary.total_tool_calls)}
                    subtitle={summary.avg_latency_ms != null ? `Avg latency: ${summary.avg_latency_ms}ms` : 'No latency data'}
                    icon={<Wrench size={24} />}
                    gradient="linear-gradient(135deg, #a18cd1 0%, #fbc2eb 100%)"
                />
            </div>

            {/* AG Grid Table */}
            <div className="admin-grid-container">
                <div className="admin-grid-header">
                    <h2>Message Details</h2>
                    <span className="admin-grid-count">{messages.length} records</span>
                </div>
                <div className="admin-grid-wrapper" style={{ height: '600px' }}>
                    <AgGridReact
                        ref={gridRef}
                        rowData={messages}
                        columnDefs={columnDefs}
                        defaultColDef={defaultColDef}
                        theme={themeAlpine}
                        pagination={true}
                        paginationPageSize={25}
                        paginationPageSizeSelector={[10, 25, 50, 100]}
                        animateRows={true}
                        rowSelection="multiple"
                        tooltipShowDelay={300}
                        suppressCellFocus={true}
                    />
                </div>
            </div>
        </div>
    );
}
