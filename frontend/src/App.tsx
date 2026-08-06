import React, { useState, useEffect } from 'react';
import { 
  FileText, CheckSquare, AlertTriangle, Clock, Upload, 
  Check, X, FileCode, FileDown, RefreshCw, MessageSquare, Plus, Activity
} from 'lucide-react';

const API_BASE = 'http://localhost:8000';

// Simple Markdown to HTML formatter helper (Light Mode themed)
const renderMarkdown = (text: string) => {
  if (!text) return '';
  let html = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  
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
    if (p.trim().startsWith('<h') || p.trim().startsWith('<li') || p.trim().startsWith('<ul')) {
      return p;
    }
    return `<p class="text-slate-700 text-xs leading-relaxed mb-2.5">${p.replace(/\n/g, '<br/>')}</p>`;
  }).join('');
  
  return <div dangerouslySetInnerHTML={{ __html: html }} />;
};

export default function App() {
  const [activeTab, setActiveTab] = useState('brief');
  const [workspaces, setWorkspaces] = useState<any[]>([]);
  const [activeWorkspaceId, setActiveWorkspaceId] = useState<string>('');
  
  const [documents, setDocuments] = useState<any[]>([]);
  const [briefSections, setBriefSections] = useState<any[]>([]);
  const [conflicts, setConflicts] = useState<any[]>([]);
  const [reviews, setReviews] = useState<any[]>([]);
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

  // Initial workspaces fetch
  useEffect(() => {
    fetchWorkspaces();
  }, []);

  // Fetch workspaces list
  const fetchWorkspaces = async () => {
    try {
      const res = await fetch(`${API_BASE}/workspaces`);
      if (res.ok) {
        const data = await res.json();
        setWorkspaces(data);
        if (data.length > 0 && !activeWorkspaceId) {
          // Default to Default Workspace if it exists, otherwise first one
          const defaultWs = data.find((w: any) => w.name === 'Default Workspace') || data[0];
          setActiveWorkspaceId(defaultWs.id);
        }
      }
    } catch (e) {
      console.error("Error fetching workspaces:", e);
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
                                <span className="font-semibold text-slate-800">
                                  Version {hist.version} 
                                  {hist.version === sec.version && (
                                    <span className="text-[8px] bg-slate-200 border border-slate-300 text-slate-800 px-1 py-0.2 ml-2 uppercase font-bold">
                                      Current
                                    </span>
                                  )}
                                </span>
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
        {activeTab === 'reviews' && (
          <div className="max-w-4xl mx-auto space-y-4">
            {reviews.filter(r => r.status === 'pending').length === 0 ? (
              <div className="bg-white border border-slate-200 p-12 text-center text-slate-400 rounded-none">
                <Check className="h-10 w-10 text-green-600 mx-auto mb-2 p-2 bg-green-50 rounded-none border border-green-200" />
                <h4 className="text-sm font-bold text-slate-900 mb-1">No pending updates</h4>
                <p className="text-xs">All updates are resolved. Upload new project files to trigger recommendations.</p>
              </div>
            ) : (
              reviews.filter(r => r.status === 'pending').map((rev) => (
                <div key={rev.id} className="bg-white border border-slate-200 p-5 rounded-none flex flex-col justify-between space-y-4">
                  <div>
                    <div className="flex justify-between items-start border-b border-slate-200 pb-2 mb-3">
                      <div>
                        <span className="text-[9px] font-bold text-indigo-600 uppercase tracking-wide">Section Recommendation</span>
                        <h4 className="text-sm font-bold text-slate-900 mt-0.5">{rev.proposed_change.target_section}</h4>
                      </div>
                      <div className="text-right text-[10px]">
                        <span className="text-slate-400 block">Source Document</span>
                        <span className="font-semibold text-slate-800 block mt-0.5">{rev.proposed_change.source_document}</span>
                      </div>
                    </div>

                    {rev.conflict_id && (
                      <div className="p-2.5 mb-3 bg-amber-50 border border-amber-200 rounded-none flex items-start gap-2 text-xs text-amber-800">
                        <AlertTriangle className="h-4 w-4 shrink-0 text-amber-600 mt-0.5" />
                        <div>
                          <span className="font-bold text-[11px]">Conflict Resolution Included</span>
                          <p className="text-[10px] text-amber-700 mt-0.5">Approving this recommendation will mark the linked conflict as resolved.</p>
                        </div>
                      </div>
                    )}

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="space-y-1">
                        <span className="text-[9px] font-bold text-red-700 uppercase tracking-wider block">Current Text</span>
                        <div className="p-2.5 bg-red-50/50 border border-red-100 rounded-none text-xs text-slate-600 font-mono h-40 overflow-y-auto whitespace-pre-wrap">
                          {rev.proposed_change.old_value || "(Empty Section)"}
                        </div>
                      </div>
                      <div className="space-y-1">
                        <span className="text-[9px] font-bold text-green-700 uppercase tracking-wider block">Proposed Text</span>
                        <div className="p-2.5 bg-green-50/50 border border-green-100 rounded-none text-xs text-slate-800 font-mono h-40 overflow-y-auto whitespace-pre-wrap">
                          {rev.proposed_change.new_value}
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="flex gap-2 justify-end border-t border-slate-100 pt-3">
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
                  </div>
                </div>
              ))
            )}
          </div>
        )}

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
                          <td className="px-4 py-3 font-semibold text-slate-900">{doc.filename}</td>
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
                      { id: 'extraction', label: 'Fact Extract' },
                      { id: 'knowledge_merge', label: 'Merge Engine' },
                      { id: 'conflict_detection', label: 'Conflict Check' },
                      { id: 'generate_brief_updates', label: 'Draft Brief' }
                    ];

                    const currentNodeIndex = steps.findIndex(s => s.id === job.current_node);
                    
                    return (
                      <div key={job.id} className="p-4 bg-slate-50 border border-slate-200 rounded-none space-y-3">
                        <div className="flex justify-between items-center text-xs">
                          <div>
                            <span className="font-bold text-slate-900">Job {job.id.substring(0, 8)}...</span>
                            <span className="text-slate-500 ml-2">Started {new Date(job.started_at).toLocaleString()}</span>
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

                        {/* Node grid layout */}
                        <div className="grid grid-cols-2 md:grid-cols-6 gap-2 pt-2 border-t border-slate-200">
                          {steps.map((step, idx) => {
                            const isCompleted = idx < currentNodeIndex || (idx === currentNodeIndex && job.status === 'complete');
                            const isCurrent = idx === currentNodeIndex && job.status === 'running';
                            const isWaiting = idx > currentNodeIndex;

                            let stepStyle = "border-slate-200 text-slate-400 bg-white";
                            if (isCompleted) stepStyle = "border-green-300 text-green-700 bg-green-50/50";
                            if (isCurrent) stepStyle = "border-blue-400 text-blue-700 bg-blue-50 font-bold";

                            return (
                              <div key={step.id} className={`p-2 border text-center text-[10px] rounded-none ${stepStyle}`}>
                                <div className="font-semibold">{step.label}</div>
                                <div className="text-[8px] mt-0.5 font-normal">
                                  {isCompleted && "✓ Finished"}
                                  {isCurrent && "Processing..."}
                                  {isWaiting && "Waiting"}
                                </div>
                              </div>
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

    </div>
  );
}
