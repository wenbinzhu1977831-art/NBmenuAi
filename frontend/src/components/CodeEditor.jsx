import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Editor } from '@monaco-editor/react';
import { Save, History, Code, AlertTriangle } from 'lucide-react';

const API_URL = '/api/admin';

export default function CodeEditor() {
  const [activeFile, setActiveFile] = useState('prompts.py');
  const [code, setCode] = useState('// Loading...');
  const [backups, setBackups] = useState([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');

  const files = [
    'prompts.py',
    'tools_address.py',
    'tools_history.py', 
    'tools_pricing.py',
    'server.py',
    'config.py'
  ];

  useEffect(() => {
    fetchCode(activeFile);
    fetchBackups(activeFile);
  }, [activeFile]);

  const fetchCode = async (fileName) => {
    try {
      setLoading(true);
      const res = await axios.get(`${API_URL}/code?file=${fileName}`);
      setCode(res.data.content);
    } catch (err) {
      console.error(err);
      setCode('# Error loading file or file does not exist');
    } finally {
      setLoading(false);
    }
  };

  const fetchBackups = async (fileName) => {
    try {
      const res = await axios.get(`${API_URL}/backups?file=${fileName}`);
      setBackups(res.data);
    } catch (err) {
      console.error('Failed to fetch backups', err);
    }
  };

  const handleSave = async () => {
    try {
      setMessage('Saving text and creating backup snapshot...');
      const res = await axios.post(`${API_URL}/code`, {
        file: activeFile,
        content: code
      });
      setMessage('Saved successfully!');
      fetchBackups(activeFile); // refresh backup list
      setTimeout(() => setMessage(''), 3000);
    } catch (err) {
      setMessage('Error saving file. Check server logs.');
    }
  };

  const handleRestore = async (backupName) => {
    if (window.confirm(`Are you sure you want to restore ${backupName}? This will overwrite current code.`)) {
      try {
        setMessage('Restoring backup...');
        await axios.post(`${API_URL}/restore`, {
          target_file: activeFile,
          backup_filename: backupName
        });
        setMessage('Restored successfully!');
        fetchCode(activeFile);
        setTimeout(() => setMessage(''), 3000);
      } catch (err) {
        setMessage('Failed to restore backup.');
      }
    }
  };

  return (
    <div className="flex h-[calc(100vh-10rem)] border border-slate-800 rounded-xl overflow-hidden bg-slate-900 shadow-xl">
      {/* File Explorer Sidebar */}
      <div className="w-64 bg-slate-950 border-r border-slate-800 flex flex-col">
        <div className="p-4 border-b border-slate-800">
          <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-2">
            <Code size={16} /> Python Files
          </h3>
        </div>
        <div className="flex-1 overflow-y-auto py-2">
          {files.map(f => (
            <button
              key={f}
              onClick={() => setActiveFile(f)}
              className={`w-full text-left px-4 py-2 text-sm transition-colors ${
                activeFile === f 
                ? 'bg-indigo-900/40 text-indigo-300 border-r-2 border-indigo-500' 
                : 'text-slate-400 hover:bg-slate-900 hover:text-slate-200'
              }`}
            >
              {f}
            </button>
          ))}
        </div>
        
        {/* Backup History Panel */}
        <div className="h-1/3 min-h-[200px] border-t border-slate-800 bg-slate-900/50 flex flex-col">
           <div className="p-3 border-b border-slate-800 flex justify-between items-center">
             <h4 className="text-xs font-semibold text-slate-400 flex items-center gap-1"><History size={14}/> Backups</h4>
           </div>
           <div className="flex-1 overflow-y-auto p-2 space-y-1">
             {backups.length === 0 ? (
               <div className="text-xs text-slate-600 text-center p-4 italic">No backups yet. Save to create one.</div>
             ) : (
               backups.map(b => (
                 <div key={b.filename} className="group flex justify-between items-center p-2 rounded hover:bg-slate-800 text-xs text-slate-400">
                    <span className="truncate pr-2" title={b.filename}>{b.timestamp}</span>
                    <button 
                      onClick={() => handleRestore(b.filename)}
                      className="opacity-0 group-hover:opacity-100 text-indigo-400 hover:text-indigo-300 transition-opacity"
                      title="Restore this version"
                    >
                      Restore
                    </button>
                 </div>
               ))
             )}
           </div>
        </div>
      </div>

      {/* Main Editor Area */}
      <div className="flex-1 flex flex-col bg-slate-900">
        <div className="h-12 bg-slate-800/50 border-b border-slate-800 flex items-center justify-between px-4">
          <div className="flex items-center gap-2">
            <span className="text-sm font-mono text-cyan-400">{activeFile}</span>
            {['server.py', 'config.py', 'tools_manage_call.py'].includes(activeFile) && (
              <span className="flex items-center gap-1 text-[10px] bg-amber-900/30 text-amber-500 px-2 py-0.5 rounded border border-amber-800/50">
                <AlertTriangle size={10} /> Core Logic
              </span>
            )}
          </div>
          <div className="flex items-center gap-4">
             {message && <span className="text-xs animate-pulse text-indigo-300">{message}</span>}
             <button
               onClick={handleSave}
               disabled={loading}
               className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white px-3 py-1.5 rounded text-sm transition-colors shadow-lg"
             >
               <Save size={14} /> Commit & Backup
             </button>
          </div>
        </div>
        
        <div className="flex-1">
          {loading ? (
             <div className="h-full flex items-center justify-center text-slate-500 font-mono text-sm">Loading Editor...</div>
          ) : (
            <Editor
              height="100%"
              language="python"
              theme="vs-dark"
              value={code}
              onChange={(val) => setCode(val)}
              options={{
                minimap: { enabled: false },
                fontSize: 14,
                fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                scrollBeyondLastLine: false,
                wordWrap: 'on',
                lineHeight: 24,
                padding: { top: 16 }
              }}
            />
          )}
        </div>
      </div>
    </div>
  );
}
