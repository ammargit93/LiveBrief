import React, { useState, useEffect } from 'react';
import { 
  FileText, CheckSquare, AlertTriangle, Clock, Upload, 
  Check, FileCode, FileDown, RefreshCw, MessageSquare, Plus, Activity
} from 'lucide-react';

const API_BASE = 'http://localhost:8000';

// Simple Markdown to HTML formatter helper (Light Mode themed)
const renderMarkdown = (text: string) => {
  if (!text) return '';
  let html = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  
  // Links
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer" class="text-indigo-600 hover:text-indigo-900 underline font-medium">$1</a>');
  
  // Headers
  html = html.replace(/^### (.*$)/gim, '<h4 class="text-xs font-bold text-slate-800 mt-2 mb-1">$1</h4>');
  html = html.replace(/^## (.*$)/gim, '<h3 class="text-sm font-bold text-slate-900 mt-3 mb-2">$1</h3>');
  html = html.replace(/^# (.*$)/gim, '<h2 class="text-base font-bold text-slate-900 mt-4 mb-3 border-b border-slate-200 pb-1">$1</h2>');
  
  // Bold
  html = html.replace(/\*\*(.*)\*\*/gim, '<strong class="font-bold text-slate-950">$1</strong>');
  html = html.replace(/\*(.*)\*/gim, '<em class="italic text-slate-800">$1</em>');
  
  // Lists
  html = html.replace(/^\- (.*$)/gim, '<li class="ml-4 list-disc text-slate-700 my-1 text-xs">$1</li>');
  
  // Paragraphs / Linebreaks
  html = html.split('\n\n').map(p => {
    if (p.trim().startsWith('<h') || p.trim().startsWith('<li') || p.trim().startsWith('<ul') || p.trim().startsWith('<a')) {
      return p;
    }
    return `<p class="text-slate-700 text-xs leading-relaxed mb-2.5">${p.replace(/\n/g, '<br/>')}</p>`;
  }).join('');
  
  return <div dangerouslySetInnerHTML={{ __html: html }} />;
};

const diffLines = (oldStr: string, newStr: string) => {
  const oldLines = oldStr.split('\n');
  const newLines = newStr.split('\n');
  
  const matrix: number[][] = Array(oldLines.length + 1).fill(null).map(() => Array(newLines.length + 1).fill(0));
  
  for (let i = 1; i <= oldLines.length; i++) {
    for (let j = 1; j <= newLines.length; j++) {
      if (oldLines[i - 1] === newLines[j - 1]) {
        matrix[i][j] = matrix[i - 1][j - 1] + 1;
      } else {
        matrix[i][j] = Math.max(matrix[i - 1][j], matrix[i][j - 1]);
      }
    }
  }
  
  let i = oldLines.length;
  let j = newLines.length;
  const result: { type: 'added' | 'removed' | 'unchanged'; value: string }[] = [];
  
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && oldLines[i - 1] === newLines[j - 1]) {
      result.unshift({ type: 'unchanged', value: oldLines[i - 1] });
      i--;
      j--;
    } else if (j > 0 && (i === 0 || matrix[i][j - 1] >= matrix[i - 1][j])) {
      result.unshift({ type: 'added', value: newLines[j - 1] });
      j--;
    } else {
      result.unshift({ type: 'removed', value: oldLines[i - 1] });
      i--;
    }
  }
  
  return result;
};

export default function App() {
  const [activeTab, setActiveTab] = useState('brief');
  const [diffViewMode, setDiffViewMode] = useState<'split' | 'unified'>('unified');
  const [workspaces, setWorkspaces] = useState<any[]>([]);
  const [activeWorkspaceId, setActiveWorkspaceId] = useState<string>(() => {
    return localStorage.getItem('activeWorkspaceId') || '';
  });
  
  const [documents, setDocuments] = useState<any[]>([]);
  const [briefSections, setBriefSections] = useState<any[]>([]);
  const [conflicts, setConflicts] = useState<any[]>([]);
  const [reviews, setReviews] = useState<any[]>([]);
  const [editingReviewId, setEditingReviewId] = useState<string | null>(null);
  const [editTargetSection, setEditTargetSection] = useState<string>('');
  const [editNewValue, setEditNewValue] = useState<string>('');
  const [timeline, setTimeline] = useState<any[]>([]);
  const [jobs, setJobs] = useState<any[]>([]);
  
  const [loading, setLoading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<string>('');
  const [rejectReason, setRejectReason] = useState<string>('');
  const [showRejectModal, setShowRejectModal] = useState<string | null>(null);
  
  const [expandedHistorySection, setExpandedHistorySection] = useState<string | null>(null);
  const [sectionHistoryData, setSectionHistoryData] = useState<any[]>([]);

  const [showWorkspaceModal, setShowWorkspaceModal] = useState(false);
  const [newWorkspaceName, setNewWorkspaceName] = useState('');

  const [viewingDoc, setViewingDoc] = useState<any | null>(null);
  const [viewingDocContent, setViewingDocContent] = useState<string>('');
  const [loadingDocContent, setLoadingDocContent] = useState(false);

  // Initial workspaces fetch
  useEffect(() => {
    fetchWorkspaces();
  }, []);

  // Sync activeWorkspaceId to localStorage
  useEffect(() => {
    if (activeWorkspaceId) {
      localStorage.setItem('activeWorkspaceId', activeWorkspaceId);
    }
  }, [activeWorkspaceId]);

  // Fetch workspaces list
  const fetchWorkspaces = async () => {
    try {
      const res = await fetch(`${API_BASE}/workspaces`);
      if (res.ok) {
        const data = await res.json();
        setWorkspaces(data);
        if (data.length > 0) {
          const storedId = localStorage.getItem('activeWorkspaceId');
          const exists = data.some((w: any) => w.id === storedId);
          if (exists) {
            setActiveWorkspaceId(storedId!);
          } else {
            const defaultWs = data.find((w: any) => w.name === 'Default Workspace') || data[0];
            setActiveWorkspaceId(defaultWs.id);
          }
        }
      }
    } catch (e) {
      console.error("Error fetching workspaces:", e);
    }
  };

  const handleViewDocument = async (doc: any) => {
    setViewingDoc(doc);
    setViewingDocContent('');
    setLoadingDocContent(true);
    try {
      const res = await fetch(`${API_BASE}/documents/${doc.id}/content?workspace_id=${activeWorkspaceId}`);
      if (res.ok) {
        const data = await res.json();
        setViewingDocContent(data.content || 'No content found in this document.');
      } else {
        setViewingDocContent('Failed to retrieve document content.');
      }
    } catch (error) {
      console.error("Error loading document content:", error);
      setViewingDocContent('Error loading document content.');
    } finally {
      setLoadingDocContent(false);
    }
  };

  // Poll workspace-specific data when workspace changes
  useEffect(() => {
    if (activeWorkspaceId) {
      fetchWorkspaceData(activeWorkspaceId);
    }
  }, [activeWorkspaceId]);

  // Periodic poll of job runs & timeline updates
  useEffect(() => {
    if (!activeWorkspaceId) return;
    const interval = setInterval(() => {
      fetchLightweightUpdates(activeWorkspaceId);
    }, 3000);
    return () => clearInterval(interval);
  }, [activeWorkspaceId]);

  const fetchWorkspaceData = async (wsId: string) => {
    setLoading(true);
    try {
      const urlParams = `?workspace_id=${wsId}`;
      
      const docsRes = await fetch(`${API_BASE}/documents${urlParams}`);
      const docsData = await docsRes.json();
      setDocuments(docsData);

      const briefRes = await fetch(`${API_BASE}/project-summary${urlParams}`);
      const briefData = await briefRes.json();
      setBriefSections(briefData);

      const confRes = await fetch(`${API_BASE}/conflicts${urlParams}`);
      const confData = await confRes.json();
      setConflicts(confData);

      const revRes = await fetch(`${API_BASE}/review${urlParams}`);
      const revData = await revRes.json();
      setReviews(revData);

      const timeRes = await fetch(`${API_BASE}/timeline${urlParams}`);
      const timeData = await timeRes.json();
      setTimeline(timeData);

      const jobsRes = await fetch(`${API_BASE}/jobs${urlParams}`);
      const jobsData = await jobsRes.json();
      setJobs(jobsData);
    } catch (error) {
      console.error("Error fetching workspace data:", error);
    } finally {
      setLoading(false);
    }
  };

  const fetchLightweightUpdates = async (wsId: string) => {
    try {
      const urlParams = `?workspace_id=${wsId}`;
      
      const docsRes = await fetch(`${API_BASE}/documents${urlParams}`);
      const docsData = await docsRes.json();
      setDocuments(docsData);

      const briefRes = await fetch(`${API_BASE}/project-summary${urlParams}`);
      const briefData = await briefRes.json();
      setBriefSections(briefData);

      const revRes = await fetch(`${API_BASE}/review${urlParams}`);
      const revData = await revRes.json();
      setReviews(revData);

      const confRes = await fetch(`${API_BASE}/conflicts${urlParams}`);
      const confData = await confRes.json();
      setConflicts(confData);

      const timeRes = await fetch(`${API_BASE}/timeline${urlParams}`);
      const timeData = await timeRes.json();
      setTimeline(timeData);

      const jobsRes = await fetch(`${API_BASE}/jobs${urlParams}`);
      const jobsData = await jobsRes.json();
      setJobs(jobsData);
    } catch (e) {
      // Ignore poll connection issues silently
    }
  };

  const handleCreateWorkspace = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newWorkspaceName.trim()) return;

    try {
      const res = await fetch(`${API_BASE}/workspaces`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newWorkspaceName.trim() }),
      });
      if (res.ok) {
        const data = await res.json();
        setNewWorkspaceName('');
        setShowWorkspaceModal(false);
        // Refresh workspaces and select the new one
        const listRes = await fetch(`${API_BASE}/workspaces`);
        if (listRes.ok) {
          const listData = await listRes.json();
          setWorkspaces(listData);
          setActiveWorkspaceId(data.id);
        }
      } else {
        const err = await res.json();
        alert(`Failed to create workspace: ${err.detail || 'Error'}`);
      }
    } catch (e) {
      alert(`Error creating workspace: ${e}`);
    }
  };

  const handleToggleHistory = async (sectionName: string) => {
    if (expandedHistorySection === sectionName) {
      setExpandedHistorySection(null);
      setSectionHistoryData([]);
    } else {
      setExpandedHistorySection(sectionName);
      try {
        const res = await fetch(`${API_BASE}/project-summary/${encodeURIComponent(sectionName)}/history?workspace_id=${activeWorkspaceId}`);
        if (res.ok) {
          const data = await res.json();
          setSectionHistoryData(data);
        }
      } catch (e) {
        console.error("Error fetching history:", e);
      }
    }
  };

  const handleRollbackSection = async (sectionName: string, versionNumber: number) => {
    if (!activeWorkspaceId) return;
    if (!window.confirm(`Are you sure you want to rollback "${sectionName}" to version ${versionNumber}?`)) return;
    
    try {
      const res = await fetch(`${API_BASE}/project-summary/${encodeURIComponent(sectionName)}/rollback?version=${versionNumber}&workspace_id=${activeWorkspaceId}`, {
        method: 'POST'
      });
      if (res.ok) {
        fetchWorkspaceData(activeWorkspaceId);
        const histRes = await fetch(`${API_BASE}/project-summary/${encodeURIComponent(sectionName)}/history?workspace_id=${activeWorkspaceId}`);
        if (histRes.ok) {
          const histData = await histRes.json();
          setSectionHistoryData(histData);
        }
      } else {
        const err = await res.json();
        alert(`Rollback failed: ${err.detail || 'Error'}`);
      }
    } catch (e) {
      alert(`Error during rollback: ${e}`);
    }
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0 || !activeWorkspaceId) return;
    
    setUploadStatus('Uploading file(s) to workspace...');
    const formData = new FormData();
    for (let i = 0; i < e.target.files.length; i++) {
      formData.append('files', e.target.files[i]);
    }

    try {
      const res = await fetch(`${API_BASE}/documents/upload?workspace_id=${activeWorkspaceId}`, {
        method: 'POST',
        body: formData,
      });
      if (res.ok) {
        setUploadStatus('Upload complete. Parsing job runs initialized.');
        setTimeout(() => setUploadStatus(''), 4000);
        fetchWorkspaceData(activeWorkspaceId);
      } else {
        const err = await res.json();
        setUploadStatus(`Upload failed: ${err.detail || 'Error'}`);
      }
    } catch (error) {
      setUploadStatus(`Upload error: ${error}`);
    }
  };

  const handleApproveReview = async (id: string) => {
    try {
      const res = await fetch(`${API_BASE}/review/${id}/approve?workspace_id=${activeWorkspaceId}`, {
        method: 'POST',
      });
      if (res.ok) {
        fetchWorkspaceData(activeWorkspaceId);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleSaveReviewEdit = async (id: string, approveAfterSave = false) => {
    try {
      const res = await fetch(`${API_BASE}/review/${id}?workspace_id=${activeWorkspaceId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target_section: editTargetSection,
          new_value: editNewValue,
        }),
      });
      if (res.ok) {
        if (approveAfterSave) {
          await handleApproveReview(id);
        } else {
          fetchWorkspaceData(activeWorkspaceId);
        }
        setEditingReviewId(null);
      } else {
        const err = await res.json();
        alert(`Failed to save edit: ${err.detail || 'Error'}`);
      }
    } catch (e) {
      console.error(e);
      alert(`Error saving edit: ${e}`);
    }
  };

  const handleRejectReview = async () => {
    if (!showRejectModal) return;
    try {
      const res = await fetch(`${API_BASE}/review/${showRejectModal}/reject?workspace_id=${activeWorkspaceId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: rejectReason }),
      });
      if (res.ok) {
        setShowRejectModal(null);
        setRejectReason('');
        fetchWorkspaceData(activeWorkspaceId);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const pendingReviewsCount = reviews.filter(r => r.status === 'pending').length;
  const openConflictsCount = conflicts.filter(c => !c.resolved).length;
  const activeJobsCount = jobs.filter(j => j.status === 'running').length;

  return (
    <div className="flex min-h-screen bg-slate-50 text-slate-900 font-sans">
      
      {/* Sidebar navigation (Solid Gray, Sharp, Corporate) */}
      <aside className="w-64 bg-slate-900 text-white flex flex-col fixed h-full z-10 rounded-none border-r border-slate-800">
        
        {/* Workspace Title & Selector */}
        <div className="p-4 border-b border-slate-800 space-y-3">
          <div className="flex items-center gap-2">
            <div className="bg-white text-slate-900 p-1 font-bold text-xs">
              LB
            </div>
            <div>
              <h1 className="font-bold text-xs tracking-wide text-white">LiveBrief System</h1>
              <span className="text-[8px] text-slate-400 font-medium uppercase tracking-wider block">Agentic Document Reconciliation</span>
            </div>
          </div>
          
          {/* Workspace Switcher */}
          <div className="space-y-1">
            <label className="text-[9px] uppercase tracking-wider text-slate-400 font-semibold block">Select Workspace</label>
            <div className="flex gap-1.5">
              <select 
                value={activeWorkspaceId}
                onChange={(e) => setActiveWorkspaceId(e.target.value)}
                className="flex-1 bg-slate-800 border border-slate-700 text-white text-xs px-2.5 py-1.5 focus:outline-none focus:border-slate-500 rounded-none"
              >
                {workspaces.map((ws) => (
                  <option key={ws.id} value={ws.id}>{ws.name}</option>
                ))}
              </select>
              <button 
                onClick={() => setShowWorkspaceModal(true)}
                className="p-1.5 bg-slate-800 border border-slate-700 hover:bg-slate-700 text-white rounded-none cursor-pointer"
                title="Create Workspace"
              >
                <Plus className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>

        <nav className="flex-1 px-2 py-4 space-y-1.5">
          <button 
            onClick={() => setActiveTab('brief')}
            className={`w-full flex items-center justify-between px-3 py-2 text-xs font-semibold rounded-none transition-all ${
              activeTab === 'brief' ? 'bg-slate-800 border-l-4 border-slate-400 text-white' : 'text-slate-400 hover:bg-slate-800 hover:text-white'
            }`}
          >
            <span className="flex items-center gap-2">
              <FileText className="h-4 w-4" /> Project Brief
            </span>
          </button>
          
          <button 
            onClick={() => setActiveTab('reviews')}
            className={`w-full flex items-center justify-between px-3 py-2 text-xs font-semibold rounded-none transition-all ${
              activeTab === 'reviews' ? 'bg-slate-800 border-l-4 border-slate-400 text-white' : 'text-slate-400 hover:bg-slate-800 hover:text-white'
            }`}
          >
            <span className="flex items-center gap-2">
              <CheckSquare className="h-4 w-4" /> Review Queue
            </span>
            {pendingReviewsCount > 0 && (
              <span className="bg-slate-700 text-[10px] text-white px-2 py-0.5 rounded-none font-bold">
                {pendingReviewsCount}
              </span>
            )}
          </button>

          <button 
            onClick={() => setActiveTab('conflicts')}
            className={`w-full flex items-center justify-between px-3 py-2 text-xs font-semibold rounded-none transition-all ${
              activeTab === 'conflicts' ? 'bg-slate-800 border-l-4 border-slate-400 text-white' : 'text-slate-400 hover:bg-slate-800 hover:text-white'
            }`}
          >
            <span className="flex items-center gap-2">
              <AlertTriangle className="h-4 w-4" /> Conflicts
            </span>
            {openConflictsCount > 0 && (
              <span className="bg-orange-600 text-[10px] text-white px-2 py-0.5 rounded-none font-bold">
                {openConflictsCount}
              </span>
            )}
          </button>

          <button 
            onClick={() => setActiveTab('documents')}
            className={`w-full flex items-center justify-between px-3 py-2 text-xs font-semibold rounded-none transition-all ${
              activeTab === 'documents' ? 'bg-slate-800 border-l-4 border-slate-400 text-white' : 'text-slate-400 hover:bg-slate-800 hover:text-white'
            }`}
          >
            <span className="flex items-center gap-2">
              <FileCode className="h-4 w-4" /> Documents
            </span>
          </button>

          <button 
            onClick={() => setActiveTab('jobs')}
            className={`w-full flex items-center justify-between px-3 py-2 text-xs font-semibold rounded-none transition-all ${
              activeTab === 'jobs' ? 'bg-slate-800 border-l-4 border-slate-400 text-white' : 'text-slate-400 hover:bg-slate-800 hover:text-white'
            }`}
          >
            <span className="flex items-center gap-2">
              <Activity className="h-4 w-4" /> Pipeline Jobs
            </span>
            {activeJobsCount > 0 && (
              <span className="bg-emerald-600 text-[10px] text-white px-2 py-0.5 rounded-none font-bold">
                {activeJobsCount}
              </span>
            )}
          </button>

          <button 
            onClick={() => setActiveTab('timeline')}
            className={`w-full flex items-center justify-between px-3 py-2 text-xs font-semibold rounded-none transition-all ${
              activeTab === 'timeline' ? 'bg-slate-800 border-l-4 border-slate-400 text-white' : 'text-slate-400 hover:bg-slate-800 hover:text-white'
            }`}
          >
            <span className="flex items-center gap-2">
              <Clock className="h-4 w-4" /> Audit Trail
            </span>
          </button>
        </nav>

        <div className="p-3 border-t border-slate-800 bg-slate-950 text-slate-500 text-[9px] tracking-wide font-mono">
          WS: {activeWorkspaceId ? activeWorkspaceId.substring(0, 8) : 'None'}
        </div>
      </aside>

      {/* Main pane content */}
      <main className="flex-1 ml-64 p-6 min-h-screen">
        
        {/* Header Toolbar (Sharp, Corporate) */}
        <header className="flex justify-between items-center mb-6 border-b border-slate-200 pb-4">
          <div>
            <h2 className="text-xl font-bold tracking-tight text-slate-900 capitalize">
              {activeTab.replace('-', ' ')}
            </h2>
          </div>

          <div className="flex items-center gap-3">
            {activeTab === 'brief' && activeWorkspaceId && (
              <div className="flex items-center gap-1.5 border-r border-slate-200 pr-3 mr-1">
                <a 
                  href={`${API_BASE}/project-summary/export?format=pdf&workspace_id=${activeWorkspaceId}`} 
                  download 
                  className="flex items-center gap-1 px-3 py-1.5 border border-red-300 text-red-700 bg-red-50 hover:bg-red-100 text-xs font-semibold rounded-none transition-all"
                >
                  <FileDown className="h-3.5 w-3.5" /> PDF
                </a>
                <a 
                  href={`${API_BASE}/project-summary/export?format=docx&workspace_id=${activeWorkspaceId}`} 
                  download 
                  className="flex items-center gap-1 px-3 py-1.5 border border-blue-300 text-blue-700 bg-blue-50 hover:bg-blue-100 text-xs font-semibold rounded-none transition-all"
                >
                  <FileDown className="h-3.5 w-3.5" /> Word
                </a>
              </div>
            )}
            
            <button 
              onClick={() => activeWorkspaceId && fetchWorkspaceData(activeWorkspaceId)}
              disabled={loading || !activeWorkspaceId}
              className="flex items-center gap-1 px-3 py-1.5 border border-slate-300 bg-white hover:bg-slate-100 text-xs font-medium transition-all text-slate-700 rounded-none cursor-pointer"
            >
              <RefreshCw className={`h-3 w-3 ${loading ? 'animate-spin' : ''}`} />
              Sync
            </button>
            
            <label className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold rounded-none cursor-pointer transition-all shadow-sm">
              <Upload className="h-3.5 w-3.5" />
              Upload Files
              <input 
                type="file" 
                multiple 
                onChange={handleUpload} 
                className="hidden" 
                accept=".md,.pdf,.docx" 
              />
            </label>
          </div>
        </header>

        {uploadStatus && (
          <div className={`p-3 mb-4 rounded-none border text-xs font-medium ${
            uploadStatus.includes('failed') ? 'bg-red-50 border-red-200 text-red-800' : 'bg-slate-100 border-slate-200 text-slate-800'
          }`}>
            {uploadStatus}
          </div>
        )}

        {/* -------------------- TAB: PROJECT BRIEF -------------------- */}
        {activeTab === 'brief' && (
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
            
            {/* Left submenu */}
            <div className="lg:col-span-1 space-y-2">
              <div className="bg-white border border-slate-200 p-3 rounded-none">
                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest px-2 mb-2 block">Brief Sections</span>
                <div className="space-y-1">
                  {briefSections.map((sec) => (
                    <a 
                      key={sec.id}
                      href={`#section-${sec.section.replace(/\s+/g, '-').toLowerCase()}`}
                      className="flex items-center justify-between px-2 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 hover:text-slate-900 border-b border-slate-100 last:border-0"
                    >
                      <span>{sec.section}</span>
                      <span className="text-[9px] bg-slate-100 border border-slate-200 px-1 py-0.2 rounded-none font-mono">
                        v{sec.version}
                      </span>
                    </a>
                  ))}
                </div>
              </div>
            </div>

            {/* Content Display */}
            <div className="lg:col-span-3 space-y-4">
              {briefSections.length === 0 ? (
                <div className="bg-white border border-slate-200 p-8 text-center text-slate-400 rounded-none">
                  <p className="text-xs">No brief content generated. Please upload documents to begin compiling.</p>
                </div>
              ) : (
                briefSections.map((sec) => (
                  <div 
                    key={sec.id} 
                    id={`section-${sec.section.replace(/\s+/g, '-').toLowerCase()}`}
                    className="bg-white border border-slate-200 p-6 rounded-none relative"
                  >
                    <div className="flex justify-between items-center mb-3 border-b border-slate-200 pb-2">
                      <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wide">{sec.section}</h3>
                      <div className="flex items-center gap-2 text-[10px] text-slate-500 font-medium">
                        <span>Version {sec.version}</span>
                        <span>&bull;</span>
                        <span>Updated {new Date(sec.updated_at).toLocaleDateString()}</span>
                        <span>&bull;</span>
                        <button 
                          onClick={() => handleToggleHistory(sec.section)}
                          className="text-[10px] text-indigo-600 hover:text-indigo-800 font-semibold cursor-pointer underline flex items-center gap-0.5"
                        >
                          <Clock className="h-3 w-3" /> History
                        </button>
                      </div>
                    </div>

                    <div className="prose prose-slate max-w-none text-slate-800">
                      {renderMarkdown(sec.content)}
                    </div>

                    {/* Version History Drawer */}
                    {expandedHistorySection === sec.section && (
                      <div className="mt-4 border-t border-slate-200 pt-4 space-y-3">
                        <h4 className="text-[10px] font-bold text-indigo-600 uppercase tracking-wider">Version History ({sectionHistoryData.length})</h4>
                        <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
                          {sectionHistoryData.map((hist) => (
                            <div key={hist.id} className="p-3 bg-slate-50 border border-slate-200 rounded-none space-y-1.5">
                              <div className="flex justify-between items-center text-[10px]">
                                <div className="flex items-center gap-2">
                                  <span className="font-semibold text-slate-800">
                                    Version {hist.version} 
                                  </span>
                                  {hist.version === sec.version ? (
                                    <span className="text-[8px] bg-slate-200 border border-slate-300 text-slate-800 px-1 py-0.2 uppercase font-bold">
                                      Current
                                    </span>
                                  ) : (
                                    <button
                                      onClick={() => handleRollbackSection(sec.section, hist.version)}
                                      className="text-[9px] text-indigo-600 hover:text-indigo-800 font-bold uppercase tracking-wider cursor-pointer border border-indigo-200 hover:border-indigo-400 bg-white px-1.5 py-0.2 transition-all"
                                    >
                                      Rollback
                                    </button>
                                  )}
                                </div>
                                <span className="text-slate-500 font-mono text-[9px]">{new Date(hist.updated_at).toLocaleString()}</span>
                              </div>
                              
                              <div className="text-[11px] text-slate-600 whitespace-pre-wrap font-mono bg-white p-2 border border-slate-200">
                                {hist.content}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {/* -------------------- TAB: REVIEWS -------------------- */}
        {activeTab === 'reviews' && (() => {
          const pendingReviews = reviews.filter(r => r.status === 'pending');
          
          if (pendingReviews.length === 0) {
            return (
              <div className="max-w-4xl mx-auto bg-white border border-slate-200 p-12 text-center text-slate-400 rounded-none">
                <Check className="h-10 w-10 text-green-600 mx-auto mb-2 p-2 bg-green-50 rounded-none border border-green-200" />
                <h4 className="text-sm font-bold text-slate-900 mb-1">No pending updates</h4>
                <p className="text-xs">All updates are resolved. Upload new project files to trigger recommendations.</p>
              </div>
            );
          }

          // Group reviews by source document
          const uniqueDocs = Array.from(new Set(pendingReviews.map(r => r.proposed_change.source_document || 'General Ingestion')));

          const ALL_SECTIONS = [
            "Project Overview",
            "Architecture",
            "Major Features",
            "Current Decisions",
            "Known Risks",
            "Pending Decisions",
            "Open Questions",
            "Timeline"
          ];

          return (
            <div className="max-w-4xl mx-auto space-y-8">
              {uniqueDocs.map(docName => {
                const docReviews = pendingReviews.filter(r => (r.proposed_change.source_document || 'General Ingestion') === docName);
                const changedSections = docReviews.map(r => r.proposed_change.section || r.proposed_change.target_section);
                const unchangedSections = ALL_SECTIONS.filter(s => !changedSections.includes(s));

                return (
                  <div key={docName} className="space-y-4 bg-white border border-slate-200 p-6 rounded-none shadow-sm text-left">
                    {/* Source Document Header */}
                    <div className="border-b border-indigo-100 pb-3 mb-4 flex justify-between items-center bg-indigo-50/30 px-3 py-2 -mx-6 -mt-6">
                      <span className="text-xs font-bold text-indigo-700 uppercase tracking-wider">Document Ingestion Run: {docName}</span>
                      <span className="text-[10px] text-indigo-600 bg-indigo-50 border border-indigo-100 px-2 py-0.5 font-semibold">
                        {docReviews.length} section change(s)
                      </span>
                    </div>

                    {/* Section Updates */}
                    <div className="space-y-6">
                      {docReviews.map(rev => {
                        const operation = rev.proposed_change.operation || 'MODIFY';
                        const reason = rev.proposed_change.reason || 'Entity update detected by planner.';
                        const sourceProv = rev.proposed_change.source_provenance || rev.proposed_change.source_document || docName;

                        return (
                          <div key={rev.id} className="border border-slate-200 p-4 rounded-none bg-slate-50/50 space-y-4">
                            <div className="flex justify-between items-start border-b border-slate-200 pb-2">
                              <div>
                                <span className={`text-[9px] font-bold px-1.5 py-0.5 border mr-2 uppercase tracking-wide rounded-none ${
                                  operation === 'add' ? 'bg-green-50 border-green-200 text-green-700' : 'bg-amber-50 border-amber-200 text-amber-700'
                                }`}>
                                  {rev.proposed_change.section || rev.proposed_change.target_section} — {operation.toUpperCase()}
                                </span>
                              </div>
                              <div className="text-right text-[10px]">
                                <span className="text-slate-500 font-semibold">Source: {sourceProv}</span>
                              </div>
                            </div>

                            {rev.conflict_id && (
                              <div className="p-2 bg-amber-50 border border-amber-200 rounded-none flex items-start gap-2 text-[10px] text-amber-800">
                                <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-amber-600" />
                                <div>
                                  <span className="font-bold">Conflict Resolution Included</span>
                                  <p className="text-[9px] text-amber-700 mt-0.5">Approving this recommendation will mark the linked conflict as resolved.</p>
                                </div>
                              </div>
                            )}

                            {/* Diff View Mode Toggle (rendered only when not editing) */}
                            {!editingReviewId && (
                              <div className="flex justify-between items-center bg-slate-50 p-2 border border-slate-200">
                                <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Visual Diff View</span>
                                <div className="flex border border-slate-300 shadow-sm bg-white">
                                  <button
                                    onClick={() => setDiffViewMode('unified')}
                                    className={`px-3 py-1 text-[9px] font-bold uppercase transition-all cursor-pointer ${
                                      diffViewMode === 'unified' ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100'
                                    }`}
                                  >
                                    Unified Diff (Git)
                                  </button>
                                  <button
                                    onClick={() => setDiffViewMode('split')}
                                    className={`px-3 py-1 text-[9px] font-bold uppercase transition-all cursor-pointer ${
                                      diffViewMode === 'split' ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100'
                                    }`}
                                  >
                                    Side-by-Side
                                  </button>
                                </div>
                              </div>
                            )}

                            {diffViewMode === 'unified' && !editingReviewId ? (
                              <div className="p-3 bg-slate-950 text-slate-200 rounded-none text-xs font-mono h-64 overflow-y-auto whitespace-pre border border-slate-800 text-left leading-relaxed">
                                {diffLines(rev.proposed_change.old_value || '', rev.proposed_change.new_value || '').map((line, idx) => {
                                  if (line.type === 'added') {
                                    return (
                                      <div key={idx} className="bg-green-950/60 text-green-300 px-2 py-0.5 border-l-4 border-green-500">
                                        + {line.value}
                                      </div>
                                    );
                                  } else if (line.type === 'removed') {
                                    return (
                                      <div key={idx} className="bg-red-950/60 text-red-300 px-2 py-0.5 border-l-4 border-red-500">
                                        - {line.value}
                                      </div>
                                    );
                                  } else {
                                    return (
                                      <div key={idx} className="text-slate-400 px-2 py-0.5 pl-6">
                                        {line.value}
                                      </div>
                                    );
                                  }
                                })}
                              </div>
                            ) : (
                              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <div className="space-y-1">
                                  <span className="text-[9px] font-bold text-red-700 uppercase tracking-wider block text-left">Current/Old Value</span>
                                  <div className="p-2.5 bg-red-50/30 border border-red-100 rounded-none text-xs text-slate-600 font-mono h-64 overflow-y-auto whitespace-pre-wrap text-left">
                                    {rev.proposed_change.old_value || "(Empty Section)"}
                                  </div>
                                </div>
                                <div className="space-y-1">
                                  <span className="text-[9px] font-bold text-green-700 uppercase tracking-wider block text-left">Proposed/New Value</span>
                                  {editingReviewId === rev.id ? (
                                    <textarea
                                      value={editNewValue}
                                      onChange={(e) => setEditNewValue(e.target.value)}
                                      className="w-full p-2.5 bg-white border border-slate-300 rounded-none text-xs text-slate-800 font-mono h-64 focus:outline-none focus:ring-1 focus:ring-indigo-500 resize-none text-left"
                                    />
                                  ) : (
                                    <div className="p-2.5 bg-green-50/30 border border-green-100 rounded-none text-xs text-slate-800 font-mono h-64 overflow-y-auto whitespace-pre-wrap text-left">
                                      {rev.proposed_change.new_value}
                                    </div>
                                  )}
                                </div>
                              </div>
                            )}

                            <div className="text-xs border-t border-slate-200 pt-2.5 flex flex-col gap-1 text-slate-700 text-left">
                              <div><span className="font-bold text-slate-800">Reason:</span> {reason}</div>
                            </div>

                            <div className="flex gap-2 justify-end border-t border-slate-100 pt-3">
                              {editingReviewId === rev.id ? (
                                <>
                                  <button
                                    onClick={() => setEditingReviewId(null)}
                                    className="px-3.5 py-1.5 text-xs font-semibold border border-slate-300 text-slate-700 hover:bg-slate-50 rounded-none cursor-pointer transition-all"
                                  >
                                    Cancel
                                  </button>
                                  <button
                                    onClick={() => handleSaveReviewEdit(rev.id, false)}
                                    className="px-3.5 py-1.5 text-xs font-semibold border border-indigo-300 text-indigo-700 hover:bg-indigo-50 rounded-none cursor-pointer transition-all"
                                  >
                                    Save Draft
                                  </button>
                                  <button
                                    onClick={() => handleSaveReviewEdit(rev.id, true)}
                                    className="px-3.5 py-1.5 text-xs font-bold bg-slate-900 hover:bg-slate-800 text-white rounded-none cursor-pointer transition-all flex items-center gap-1"
                                  >
                                    <Check className="h-4 w-4" /> Save & Approve
                                  </button>
                                </>
                              ) : (
                                <>
                                  <button
                                    onClick={() => {
                                      setEditingReviewId(rev.id);
                                      setEditTargetSection(rev.proposed_change.section || rev.proposed_change.target_section || '');
                                      setEditNewValue(rev.proposed_change.new_value || '');
                                    }}
                                    className="px-3.5 py-1.5 text-xs font-semibold border border-slate-300 text-slate-700 hover:bg-slate-50 rounded-none cursor-pointer transition-all"
                                  >
                                    Edit
                                  </button>
                                  <button 
                                    onClick={() => {
                                      setRejectReason('');
                                      setShowRejectModal(rev.id);
                                    }}
                                    className="px-3.5 py-1.5 text-xs font-semibold border border-red-300 text-red-700 hover:bg-red-50 rounded-none cursor-pointer transition-all"
                                  >
                                    Reject Draft
                                  </button>
                                  <button 
                                    onClick={() => handleApproveReview(rev.id)}
                                    className="px-3.5 py-1.5 text-xs font-bold bg-slate-900 hover:bg-slate-800 text-white rounded-none cursor-pointer transition-all flex items-center gap-1"
                                  >
                                    <Check className="h-4 w-4" /> Approve & Apply
                                  </button>
                                </>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>

                    {/* Unchanged Sections list */}
                    {unchangedSections.length > 0 && (
                      <div className="border-t border-slate-100 pt-3 mt-4 text-left">
                        <span className="text-[9px] font-bold text-slate-400 uppercase tracking-widest block mb-2">Unchanged Sections</span>
                        <div className="flex flex-wrap gap-2 justify-start">
                          {unchangedSections.map(secName => (
                            <span key={secName} className="text-[10px] bg-slate-100 border border-slate-200 text-slate-400 px-2 py-0.5 rounded-none font-mono">
                              {secName} — UNCHANGED
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          );
        })()}

        {/* -------------------- TAB: CONFLICTS -------------------- */}
        {activeTab === 'conflicts' && (
          <div className="bg-white border border-slate-200 p-4 rounded-none">
            {conflicts.length === 0 ? (
              <p className="text-xs text-slate-400 py-6 text-center">No conflicts found between ingested documents.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs text-slate-700">
                  <thead className="text-[10px] uppercase text-slate-400 border-b border-slate-200 bg-slate-50">
                    <tr>
                      <th className="px-4 py-3">Category</th>
                      <th className="px-4 py-3">Severity</th>
                      <th className="px-4 py-3">Description</th>
                      <th className="px-4 py-3">Resolution State</th>
                      <th className="px-4 py-3">Date Flagged</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200">
                    {conflicts.map((conflict) => (
                      <tr key={conflict.id} className="hover:bg-slate-50 transition-all">
                        <td className="px-4 py-3 font-bold text-slate-900">{conflict.category}</td>
                        <td className="px-4 py-3">
                          <span className={`text-[9px] font-bold uppercase px-2 py-0.5 rounded-none border ${
                            conflict.severity === 'high' ? 'bg-red-50 border-red-200 text-red-800' :
                            conflict.severity === 'medium' ? 'bg-orange-50 border-orange-200 text-orange-800' :
                            'bg-slate-100 border-slate-200 text-slate-800'
                          }`}>
                            {conflict.severity}
                          </span>
                        </td>
                        <td className="px-4 py-3 leading-relaxed">{conflict.description}</td>
                        <td className="px-4 py-3">
                          <span className={`text-[9px] font-bold uppercase px-2 py-0.5 rounded-none border ${
                            conflict.resolved ? 'bg-green-50 border-green-200 text-green-800' : 'bg-red-50 border-red-200 text-red-800'
                          }`}>
                            {conflict.resolved ? 'Resolved' : 'Active'}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-slate-500">
                          {new Date(conflict.created_at).toLocaleDateString()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* -------------------- TAB: DOCUMENTS -------------------- */}
        {activeTab === 'documents' && (
          <div className="space-y-4">
            
            {/* Simple Upload Box */}
            <div className="bg-white border-2 border-dashed border-slate-300 p-6 text-center rounded-none relative">
              <Upload className="h-6 w-6 text-slate-400 mx-auto mb-2" />
              <label className="text-xs font-semibold text-slate-900 cursor-pointer block hover:underline">
                Click to browse files & upload
                <input 
                  type="file" 
                  multiple 
                  onChange={handleUpload} 
                  className="hidden" 
                  accept=".md,.pdf,.docx" 
                />
              </label>
              <p className="text-[10px] text-slate-500 mt-1">Supports Markdown (.md), PDF (.pdf), and Word (.docx)</p>
            </div>

            {/* Document list */}
            <div className="bg-white border border-slate-200 p-4 rounded-none">
              {documents.length === 0 ? (
                <p className="text-xs text-slate-400 py-6 text-center">No documents have been ingested yet.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs text-slate-700">
                    <thead className="text-[10px] uppercase text-slate-400 border-b border-slate-200 bg-slate-50">
                      <tr>
                        <th className="px-4 py-3">Filename</th>
                        <th className="px-4 py-3">Logical Version</th>
                        <th className="px-4 py-3">Classified Type</th>
                        <th className="px-4 py-3">Confidence</th>
                        <th className="px-4 py-3">Ingestion State</th>
                        <th className="px-4 py-3">Uploaded At</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200">
                      {documents.map((doc) => (
                        <tr key={doc.id} className="hover:bg-slate-50 transition-all">
                           <td className="px-4 py-3 font-semibold text-slate-900">
                            <span 
                              onClick={() => handleViewDocument(doc)}
                              className="text-indigo-600 hover:text-indigo-900 hover:underline cursor-pointer font-medium"
                            >
                              {doc.filename}
                            </span>
                          </td>
                          <td className="px-4 py-3 font-mono text-[10px]">v{doc.version}</td>
                          <td className="px-4 py-3">{doc.type || 'Unknown'}</td>
                          <td className="px-4 py-3 font-mono text-[10px]">
                            {doc.classification_confidence !== null ? `${(doc.classification_confidence * 100).toFixed(0)}%` : 'N/A'}
                          </td>
                          <td className="px-4 py-3">
                            <span className={`text-[9px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-none border ${
                              doc.status === 'complete' ? 'bg-green-50 border-green-200 text-green-800' :
                              doc.status === 'failed' ? 'bg-red-50 border-red-200 text-red-800' :
                              doc.status === 'needs_classification' ? 'bg-orange-50 border-orange-200 text-orange-800' :
                              'bg-blue-50 border-blue-200 text-blue-800'
                            }`}>
                              {doc.status.replace(/_/g, ' ')}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-slate-500">
                            {new Date(doc.uploaded_at).toLocaleString()}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}

        {/* -------------------- TAB: PIPELINE JOBS -------------------- */}
        {activeTab === 'jobs' && (
          <div className="space-y-4">
            <div className="bg-white border border-slate-200 p-4 rounded-none">
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest block mb-3">Ingestion Runs</span>
              {jobs.length === 0 ? (
                <p className="text-xs text-slate-400 py-6 text-center">No background jobs have run in this workspace.</p>
              ) : (
                <div className="space-y-4">
                  {jobs.map((job) => {
                    const steps = [
                      { id: 'upload', label: 'File Upload' },
                      { id: 'classification', label: 'Classification' },
                      { id: 'planner', label: 'Planner Node' },
                      { id: 'extraction', label: 'Fact Extraction' },
                      { id: 'knowledge_merge', label: 'Knowledge Merge' },
                      { id: 'conflict_detection', label: 'Conflict Check' },
                      { id: 'generate_brief_updates', label: 'Brief Drafting' }
                    ];

                    const associatedDoc = documents.find(d => d.id === job.document_id);
                    const filename = associatedDoc ? associatedDoc.filename : 'Unknown Document';

                    const getStepStatus = (stepId: string) => {
                      const currentNodeIndex = steps.findIndex(s => s.id === job.current_node);
                      const stepIndex = steps.findIndex(s => s.id === stepId);
                      
                      // Check if skipped by planner
                      if (job.planner_decision) {
                        const decision = job.planner_decision;
                        if (stepId === 'extraction' && (!decision.entity_types_to_extract || decision.entity_types_to_extract.length === 0)) {
                          return 'skipped';
                        }
                        if ((stepId === 'knowledge_merge' || stepId === 'conflict_detection') && decision.requires_conflict_check === false) {
                          return 'skipped';
                        }
                      }
                      
                      // If the job failed at this node
                      if (job.status === 'failed' && job.current_node === stepId) {
                        return 'failed';
                      }
                      
                      // If the job is running at this node
                      if (job.status === 'running' && job.current_node === stepId) {
                        return 'running';
                      }
                      
                      // If the node is completed
                      if (job.status === 'complete') {
                        return 'completed';
                      }
                      
                      if (currentNodeIndex > stepIndex) {
                        return 'completed';
                      }
                      
                      if (job.current_node === stepId) {
                        if (job.status === 'waiting_for_review') {
                          return 'waiting_for_review';
                        }
                        return 'completed';
                      }
                      
                      return 'pending';
                    };

                    return (
                      <div key={job.id} className="p-4 bg-slate-50 border border-slate-200 rounded-none space-y-4">
                        
                        {/* Job Meta Header */}
                        <div className="flex justify-between items-center text-xs">
                          <div>
                            <span className="font-bold text-slate-900">Run {job.id.substring(0, 8)}...</span>
                            <span className="text-slate-400 font-medium ml-2">Document: <span className="font-mono text-slate-800 font-semibold">{filename}</span></span>
                            <span className="text-slate-400 ml-2">| Started {new Date(job.started_at).toLocaleString()}</span>
                          </div>
                          <span className={`text-[9px] font-bold uppercase px-2 py-0.5 border ${
                            job.status === 'running' ? 'bg-blue-50 border-blue-200 text-blue-800 animate-pulse' :
                            job.status === 'failed' ? 'bg-red-50 border-red-200 text-red-800' :
                            job.status === 'waiting_for_review' ? 'bg-orange-50 border-orange-200 text-orange-850' :
                            'bg-green-50 border-green-200 text-green-800'
                          }`}>
                            {job.status.replace(/_/g, ' ')}
                          </span>
                        </div>

                        {job.error && (
                          <div className="p-2 bg-red-50 border border-red-200 text-[10px] text-red-700 font-mono">
                            Error Details: {job.error}
                          </div>
                        )}

                        {/* Planner Decision Panel */}
                        {job.planner_decision && (
                          <div className="bg-white border border-slate-200 p-3 space-y-2 text-xs">
                            <div className="flex items-center gap-2 font-bold text-slate-800 text-[10px] uppercase tracking-wide">
                              <span className="bg-slate-900 text-white px-1.5 py-0.5 font-mono text-[8px]">PLAN</span>
                              <span>Adaptive Pipeline Plan & Reasoning</span>
                            </div>
                            <p className="text-[10px] text-slate-600 leading-relaxed font-sans italic">
                              "{job.planner_decision.reasoning}"
                            </p>
                            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 pt-2 border-t border-slate-100 text-[9px]">
                              <div>
                                <span className="text-slate-400 block font-semibold uppercase tracking-wider text-[8px]">Extract Entities</span>
                                <div className="flex flex-wrap gap-1 mt-1">
                                  {job.planner_decision.entity_types_to_extract && job.planner_decision.entity_types_to_extract.length > 0 ? (
                                    job.planner_decision.entity_types_to_extract.map((t: string) => (
                                      <span key={t} className="bg-slate-100 border border-slate-200 text-slate-700 px-1 py-0.2 font-semibold">
                                        {t}
                                      </span>
                                    ))
                                  ) : (
                                    <span className="bg-amber-50 text-amber-800 px-1 py-0.2 font-semibold border border-amber-200">
                                      Skipped
                                    </span>
                                  )}
                                </div>
                              </div>
                              <div>
                                <span className="text-slate-400 block font-semibold uppercase tracking-wider text-[8px]">Affected Sections</span>
                                <div className="flex flex-wrap gap-1 mt-1">
                                  {job.planner_decision.affected_sections && job.planner_decision.affected_sections.length > 0 ? (
                                    job.planner_decision.affected_sections.map((s: string) => (
                                      <span key={s} className="bg-slate-100 border border-slate-200 text-slate-700 px-1 py-0.2 font-semibold">
                                        {s}
                                      </span>
                                    ))
                                  ) : (
                                    <span className="text-slate-500 italic">None</span>
                                  )}
                                </div>
                              </div>
                              <div>
                                <span className="text-slate-400 block font-semibold uppercase tracking-wider text-[8px]">Conflict Auditing</span>
                                <div className="mt-1">
                                  {job.planner_decision.requires_conflict_check ? (
                                    <span className="bg-green-50 border border-green-200 text-green-700 px-1.5 py-0.2 font-bold uppercase text-[8px]">
                                      Enabled
                                    </span>
                                  ) : (
                                    <span className="bg-amber-50 border border-amber-200 text-amber-700 px-1.5 py-0.2 font-bold uppercase text-[8px]">
                                      Bypassed
                                    </span>
                                  )}
                                </div>
                              </div>
                              <div>
                                <span className="text-slate-400 block font-semibold uppercase tracking-wider text-[8px]">Timeline Updates</span>
                                <div className="mt-1">
                                  {job.planner_decision.requires_timeline_update ? (
                                    <span className="bg-green-50 border border-green-200 text-green-700 px-1.5 py-0.2 font-bold uppercase text-[8px]">
                                      Enabled
                                    </span>
                                  ) : (
                                    <span className="bg-slate-150 border border-slate-250 text-slate-500 px-1.5 py-0.2 font-bold uppercase text-[8px]">
                                      Disabled
                                    </span>
                                  )}
                                </div>
                              </div>
                            </div>
                          </div>
                        )}

                        {/* Interactive Branching Node Flow */}
                        <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-slate-200">
                          {steps.map((step, idx) => {
                            const status = getStepStatus(step.id);
                            
                            let stepStyle = "";
                            let labelSuffix = "";
                            if (status === 'completed') {
                              stepStyle = "border-green-300 text-green-700 bg-green-50/50";
                              labelSuffix = "✓ Finished";
                            } else if (status === 'skipped') {
                              stepStyle = "border-slate-200 border-dashed text-slate-400 bg-slate-100/60";
                              labelSuffix = "⤏ Bypassed";
                            } else if (status === 'running') {
                              stepStyle = "border-blue-400 text-blue-700 bg-blue-50 animate-pulse font-bold";
                              labelSuffix = "Active Node";
                            } else if (status === 'failed') {
                              stepStyle = "border-red-300 text-red-700 bg-red-50 font-bold";
                              labelSuffix = "✗ Error Node";
                            } else if (status === 'waiting_for_review') {
                              stepStyle = "border-orange-300 text-orange-700 bg-orange-50 font-semibold";
                              labelSuffix = "Review Queue";
                            } else {
                              stepStyle = "border-slate-200 text-slate-400 bg-white";
                              labelSuffix = "Waiting";
                            }

                            return (
                              <React.Fragment key={step.id}>
                                <div className={`p-2 border flex-1 min-w-[110px] text-center text-[10px] rounded-none ${stepStyle}`}>
                                  <div className="font-bold text-[9px] uppercase tracking-wider text-slate-400 mb-0.5">{step.id}</div>
                                  <div className="font-semibold text-[10px]">{step.label}</div>
                                  <div className="text-[8px] mt-1 font-normal font-mono opacity-80">
                                    {labelSuffix}
                                  </div>
                                </div>
                                {idx < steps.length - 1 && (
                                  <span className={`hidden md:inline text-xs font-bold ${
                                    status === 'completed' ? 'text-green-500' : 'text-slate-300'
                                  }`}>
                                    →
                                  </span>
                                )}
                              </React.Fragment>
                            );
                          })}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        )}

        {/* -------------------- TAB: TIMELINE (Audit log) -------------------- */}
        {activeTab === 'timeline' && (
          <div className="max-w-3xl mx-auto">
            {timeline.length === 0 ? (
              <div className="bg-white border border-slate-200 p-8 text-center text-slate-400 rounded-none">
                <p className="text-xs">Timeline log is empty.</p>
              </div>
            ) : (
              <div className="border-l-2 border-slate-200 ml-4 space-y-6 py-2">
                {timeline.map((event) => {
                  const isApproved = event.actor === 'user:approved';
                  const isRejected = event.actor === 'user:rejected';
                  const isUploaded = event.actor === 'user:uploaded';
                  
                  let borderLeftColor = 'border-l-slate-400';
                  if (isApproved) borderLeftColor = 'border-l-green-600';
                  if (isRejected) borderLeftColor = 'border-l-red-600';
                  if (isUploaded) borderLeftColor = 'border-l-indigo-600';

                  return (
                    <div key={event.id} className="relative pl-6">
                      <span className="absolute -left-[5px] top-2.5 h-2 w-2 rounded-full bg-slate-300 border border-white"></span>
                      
                      <div className={`bg-white border border-slate-200 border-l-4 ${borderLeftColor} p-4 rounded-none space-y-1.5 shadow-sm`}>
                        <div className="flex flex-col md:flex-row md:items-center justify-between gap-1">
                          <h4 className="text-xs font-bold text-slate-900">{event.event}</h4>
                          <span className="text-[9px] text-slate-400 font-mono">
                            {new Date(event.timestamp).toLocaleString()}
                          </span>
                        </div>
                        <p className="text-[11px] text-slate-600 leading-relaxed">{event.reason}</p>
                        
                        <div className="flex items-center gap-2 pt-1.5 text-[9px] text-slate-400 border-t border-slate-100">
                          <span>Operator: <code className="text-slate-700 font-mono">{event.actor}</code></span>
                          {event.section && (
                            <>
                              <span>&bull;</span>
                              <span>Category: <span className="text-slate-600 font-semibold">{event.section}</span></span>
                            </>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

      </main>

      {/* Reject Modal dialog prompt */}
      {showRejectModal && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white border border-slate-300 p-5 rounded-none max-w-md w-full space-y-3.5 shadow-xl">
            <h4 className="text-sm font-bold text-slate-900 flex items-center gap-2">
              <MessageSquare className="h-5 w-5 text-red-600" />
              Provide Rejection Reason
            </h4>
            <p className="text-[11px] text-slate-500 leading-relaxed">
              Please enter a brief note explaining why this proposed change is being rejected. This will be logged in the immutable timeline.
            </p>
            
            <textarea 
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder="Explain reason for rejection..."
              className="w-full bg-slate-50 border border-slate-300 rounded-none p-2.5 text-xs text-slate-800 placeholder-slate-400 focus:outline-none focus:border-slate-500 min-h-[80px]"
            />

            <div className="flex justify-end gap-2">
              <button 
                onClick={() => setShowRejectModal(null)}
                className="px-3.5 py-1.5 text-xs font-semibold border border-slate-300 hover:bg-slate-100 rounded-none transition-all cursor-pointer"
              >
                Cancel
              </button>
              <button 
                onClick={handleRejectReview}
                className="px-4 py-1.5 text-xs font-bold bg-red-600 hover:bg-red-500 text-white rounded-none transition-all shadow-sm"
              >
                Confirm Rejection
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Workspace Creation Modal */}
      {showWorkspaceModal && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <form onSubmit={handleCreateWorkspace} className="bg-white border border-slate-300 p-5 rounded-none max-w-sm w-full space-y-3.5 shadow-xl">
            <h4 className="text-sm font-bold text-slate-900 flex items-center gap-2">
              <Plus className="h-5 w-5 text-slate-900" />
              Create New Workspace
            </h4>
            <p className="text-[11px] text-slate-500 leading-relaxed">
              Create a distinct workspace space. Each workspace has its own brief, files list, conflict checkings, reviews, and logs timeline.
            </p>
            
            <input 
              type="text"
              required
              value={newWorkspaceName}
              onChange={(e) => setNewWorkspaceName(e.target.value)}
              placeholder="Enter workspace name (e.g. Project Alpha)..."
              className="w-full bg-slate-50 border border-slate-300 rounded-none p-2 text-xs text-slate-800 placeholder-slate-400 focus:outline-none focus:border-slate-500"
            />

            <div className="flex justify-end gap-2 pt-1">
              <button 
                type="button"
                onClick={() => setShowWorkspaceModal(false)}
                className="px-3.5 py-1.5 text-xs font-semibold border border-slate-300 hover:bg-slate-100 rounded-none transition-all cursor-pointer"
              >
                Cancel
              </button>
              <button 
                type="submit"
                className="px-4 py-1.5 text-xs font-bold bg-slate-900 hover:bg-slate-800 text-white rounded-none transition-all shadow-sm"
              >
                Create Workspace
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Document Viewer Modal */}
      {viewingDoc && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white border border-slate-200 w-full max-w-4xl max-h-[85vh] flex flex-col rounded-none shadow-xl">
            {/* Modal Header */}
            <div className="flex justify-between items-center px-6 py-4 border-b border-slate-200">
              <div>
                <h3 className="text-sm font-bold text-slate-900 font-mono tracking-tight">{viewingDoc.filename}</h3>
                <p className="text-[10px] text-slate-400 mt-0.5">
                  Type: <span className="font-semibold">{viewingDoc.type || 'Unknown'}</span> | Version: <span className="font-semibold">v{viewingDoc.version}</span>
                </p>
              </div>
              <div className="flex items-center gap-3">
                <a
                  href={`${API_BASE}/documents/${viewingDoc.id}/download?workspace_id=${activeWorkspaceId}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[10px] font-bold uppercase tracking-wider border border-slate-200 bg-slate-50 text-slate-700 px-3 py-1.5 hover:bg-slate-100 transition-all"
                >
                  Download File
                </a>
                <button
                  onClick={() => setViewingDoc(null)}
                  className="text-slate-400 hover:text-slate-600 text-sm font-bold px-2 py-1"
                >
                  ✕
                </button>
              </div>
            </div>

            {/* Modal Body */}
            <div className="p-6 overflow-y-auto flex-1 bg-slate-50 font-sans text-xs text-slate-800 whitespace-pre-wrap leading-relaxed max-h-[60vh]">
              {loadingDocContent ? (
                <div className="flex flex-col items-center justify-center py-20 space-y-3">
                  <div className="w-6 h-6 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin"></div>
                  <span className="text-[10px] uppercase font-bold tracking-widest text-slate-400">Parsing and Loading Document Text...</span>
                </div>
              ) : (
                <div className="bg-white border border-slate-200 p-6 font-mono text-[11px] leading-relaxed shadow-sm overflow-x-auto text-slate-700 select-text">
                  {viewingDocContent}
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="px-6 py-3 border-t border-slate-200 flex justify-end bg-white">
              <button
                onClick={() => setViewingDoc(null)}
                className="text-[10px] font-bold uppercase tracking-wider bg-slate-900 text-white px-4 py-2 hover:bg-slate-800 transition-all rounded-none"
              >
                Close Viewer
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
