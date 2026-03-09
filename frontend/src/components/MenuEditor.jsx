import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Editor } from '@monaco-editor/react';
import { Save, AlertTriangle, RotateCcw } from 'lucide-react';

const API_URL = '/api/admin';

export default function MenuEditor({ t }) {
  const [code, setCode] = useState('// Loading...');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    fetchMenu();
  }, []);

  const fetchMenu = async () => {
    try {
      setLoading(true);
      const res = await axios.get(`${API_URL}/menu`);
      setCode(res.data.content);
    } catch (err) {
      console.error(err);
      setCode('// Error loading menu data');
    } finally {
      setLoading(false);
    }
  };

  const handleFormat = () => {
    try {
      const parsed = JSON.parse(code);
      setCode(JSON.stringify(parsed, null, 4));
      setMessage('JSON Formatted!');
      setTimeout(() => setMessage(''), 3000);
    } catch (err) {
      setMessage('Format Error: Invalid JSON');
    }
  };

  const handleFactoryReset = async () => {
    if (!window.confirm("Are you sure you want to completely erase current changes and restore the Original Factory Menu?")) {
      return;
    }
    try {
      setLoading(true);
      setMessage('Restoring factory defaults...');
      const res = await axios.post(`${API_URL}/menu/factory-reset`);
      setCode(res.data.content);
      setMessage('Factory Menu Restored!');
      setTimeout(() => setMessage(''), 3000);
    } catch (err) {
      console.error(err);
      setMessage('Failed to restore factory defaults.');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    try {
      // Pre-flight check
      JSON.parse(code);
      
      setMessage('Saving menu and creating backup...');
      await axios.post(`${API_URL}/menu`, {
        content: code
      });
      setMessage('Menu saved and reloaded into memory!');
      setTimeout(() => setMessage(''), 3000);
    } catch (err) {
      if (err instanceof SyntaxError) {
         setMessage('Save Error: Invalid JSON Format');
      } else {
         setMessage('Error saving menu. Check server logs.');
      }
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-14rem)] border border-slate-800 rounded-xl overflow-hidden bg-slate-900 shadow-xl mt-6">
      {/* Main Editor Area */}
      <div className="flex-1 flex flex-col bg-slate-900">
        <div className="h-14 bg-slate-800/50 border-b border-slate-800 flex items-center justify-between px-4">
          <div className="flex items-center gap-2">
            <span className="text-sm font-mono text-cyan-400">menu.json</span>
            <span className="flex items-center gap-1 text-[10px] bg-amber-900/30 text-amber-500 px-2 py-0.5 rounded border border-amber-800/50">
              <AlertTriangle size={10} /> Core Data Structure
            </span>
          </div>
          <div className="flex items-center gap-4">
             {message && <span className="text-xs animate-pulse text-indigo-300">{message}</span>}
             
             <button
               onClick={handleFactoryReset}
               disabled={loading}
               className="flex items-center gap-2 bg-red-900/40 hover:bg-red-800/60 border border-red-800/50 disabled:opacity-50 text-red-300 px-3 py-1.5 rounded text-sm transition-colors"
               title="Restore Original Menu"
             >
               <RotateCcw size={14} /> Factory Reset
             </button>

             <button
               onClick={handleFormat}
               disabled={loading}
               className="flex items-center gap-2 bg-slate-700 hover:bg-slate-600 disabled:opacity-50 text-white px-3 py-1.5 rounded text-sm transition-colors"
             >
               Format JSON
             </button>

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
             <div className="h-full flex items-center justify-center text-slate-500 font-mono text-sm">Loading Menu Editor...</div>
          ) : (
            <Editor
              height="100%"
              language="json"
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
