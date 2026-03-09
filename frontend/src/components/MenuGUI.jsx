import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Save, AlertTriangle, RotateCcw, Plus, Trash2, ChevronDown, ChevronRight, Edit3 } from 'lucide-react';

const API_URL = '/api/admin';

export default function MenuGUI({ t }) {
  const [menuData, setMenuData] = useState({});
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  
  // UI State
  const [expandedCategory, setExpandedCategory] = useState(null);
  const [expandedItem, setExpandedItem] = useState(null);

  useEffect(() => {
    fetchMenu();
  }, []);

  const fetchMenu = async () => {
    try {
      setLoading(true);
      const res = await axios.get(`${API_URL}/menu`);
      setMenuData(JSON.parse(res.data.content));
    } catch (err) {
      console.error(err);
      setMessage('Error loading menu data');
    } finally {
      setLoading(false);
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
      setMenuData(JSON.parse(res.data.content));
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
      setLoading(true);
      setMessage('Saving menu and creating backup...');
      await axios.post(`${API_URL}/menu`, {
        content: JSON.stringify(menuData, null, 4)
      });
      setMessage('Saved and deployed to AI successfully!');
      setTimeout(() => setMessage(''), 3000);
    } catch (err) {
      console.error(err);
      setMessage('Error saving menu. Check server logs.');
    } finally {
      setLoading(false);
    }
  };

  // State Builders
  const updateItem = (category, itemIndex, field, value) => {
    const newData = { ...menuData };
    newData[category][itemIndex][field] = value;
    setMenuData(newData);
  };

  const addCategory = () => {
    const name = prompt('New Category Name:');
    if (name && !menuData[name]) {
      setMenuData({ ...menuData, [name]: [] });
      setExpandedCategory(name);
    }
  };

  const deleteCategory = (category) => {
    if (window.confirm(`Delete entire category "${category}"?`)) {
      const newData = { ...menuData };
      delete newData[category];
      setMenuData(newData);
    }
  };

  const addItem = (category) => {
    const newData = { ...menuData };
    newData[category].push({
      name: "New Item",
      price: 0,
      currency: "EUR",
      description: "",
      allergens: "",
      options: []
    });
    setMenuData(newData);
  };

  const deleteItem = (category, itemIndex) => {
    if (window.confirm('Delete this item?')) {
      const newData = { ...menuData };
      newData[category].splice(itemIndex, 1);
      setMenuData(newData);
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-14rem)] border border-slate-800 rounded-xl overflow-hidden bg-slate-900 shadow-xl mt-6">
      {/* Header Toolbar */}
      <div className="h-14 bg-slate-800/80 border-b border-slate-800 flex items-center justify-between px-4 shrink-0">
        <div className="flex items-center gap-3">
          <span className="text-sm font-semibold text-slate-200 flex items-center gap-2">
            <Edit3 size={16} className="text-indigo-400" /> Interactive Menu Builder
          </span>
          <span className="flex items-center gap-1 text-[10px] bg-amber-900/30 text-amber-500 px-2 py-0.5 rounded border border-amber-800/50">
            <AlertTriangle size={10} /> Live AI Data
          </span>
        </div>
        <div className="flex items-center gap-4">
           {message && <span className="text-xs animate-pulse text-indigo-300 font-medium">{message}</span>}
           <button onClick={handleFactoryReset} disabled={loading} className="flex items-center gap-2 bg-red-900/40 hover:bg-red-800/60 border border-red-800/50 disabled:opacity-50 text-red-300 px-3 py-1.5 rounded text-sm transition-colors" title="Restore Original Menu">
             <RotateCcw size={14} /> Factory Reset
           </button>
           <button onClick={addCategory} className="flex items-center gap-2 bg-slate-700 hover:bg-slate-600 text-white px-3 py-1.5 rounded text-sm transition-colors">
             <Plus size={14} /> Add Category
           </button>
           <button onClick={handleSave} disabled={loading} className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white px-4 py-1.5 rounded text-sm font-medium transition-colors shadow-lg shadow-indigo-500/20">
             <Save size={14} /> Save & Deploy
           </button>
        </div>
      </div>
      
      {/* Main Content Scroll Area */}
      <div className="flex-1 overflow-y-auto p-4 bg-slate-950/50">
        {loading ? (
           <div className="h-full flex items-center justify-center text-slate-500 font-mono text-sm">Loading Menu Engine...</div>
        ) : (
           <div className="max-w-4xl mx-auto space-y-4 pb-10">
             {Object.keys(menuData).map((categoryName) => (
               <div key={categoryName} className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden shrink-0">
                 {/* Category Header */}
                 <div 
                    className="flex items-center justify-between p-4 cursor-pointer hover:bg-slate-800/50 transition-colors"
                    onClick={() => setExpandedCategory(expandedCategory === categoryName ? null : categoryName)}
                 >
                    <h2 className="text-lg font-bold text-white flex items-center gap-2">
                      {expandedCategory === categoryName ? <ChevronDown size={20} className="text-indigo-400"/> : <ChevronRight size={20} className="text-slate-500"/>}
                      {categoryName}
                      <span className="text-xs font-normal text-slate-500 bg-slate-800 px-2 py-0.5 rounded-full ml-2">{menuData[categoryName]?.length || 0} items</span>
                    </h2>
                    <button 
                      onClick={(e) => { e.stopPropagation(); deleteCategory(categoryName); }} 
                      className="text-slate-500 hover:text-red-400 p-1"
                    >
                      <Trash2 size={16} />
                    </button>
                 </div>

                 {/* Category Items List */}
                 {expandedCategory === categoryName && (
                   <div className="border-t border-slate-800 bg-slate-950 p-4 space-y-3">
                      {menuData[categoryName].map((item, idx) => {
                        const itemKey = `${categoryName}-${idx}`;
                        const isItemExpanded = expandedItem === itemKey;

                        return (
                          <div key={idx} className={`border ${isItemExpanded ? 'border-indigo-500/50 bg-slate-900' : 'border-slate-800 bg-slate-900'} rounded-lg overflow-hidden transition-all duration-200`}>
                            {/* Item Summary Row */}
                            <div 
                              className="flex items-center gap-4 p-3 cursor-pointer hover:bg-slate-800/80"
                              onClick={() => setExpandedItem(isItemExpanded ? null : itemKey)}
                            >
                               <div className="flex-1 grid grid-cols-12 gap-4 items-center">
                                  <div className="col-span-8 md:col-span-7">
                                     <input 
                                       className="w-full bg-transparent border-b border-transparent hover:border-slate-700 focus:border-indigo-500 focus:outline-none text-slate-200 font-medium px-1 py-0.5"
                                       value={item.name}
                                       placeholder="Item Name"
                                       onClick={(e) => e.stopPropagation()}
                                       onChange={(e) => updateItem(categoryName, idx, 'name', e.target.value)}
                                     />
                                  </div>
                                  <div className="col-span-4 md:col-span-3 flex items-center">
                                     <span className="text-slate-500 mr-1">€</span>
                                     <input 
                                       type="number"
                                       step="0.1"
                                       className="w-20 bg-slate-800 border border-slate-700 rounded px-2 py-1 focus:border-indigo-500 focus:outline-none text-slate-200 text-sm"
                                       value={item.price}
                                       onClick={(e) => e.stopPropagation()}
                                       onChange={(e) => updateItem(categoryName, idx, 'price', parseFloat(e.target.value))}
                                     />
                                  </div>
                               </div>
                               <button 
                                 onClick={(e) => { e.stopPropagation(); deleteItem(categoryName, idx); }} 
                                 className="text-slate-600 hover:text-red-400 bg-slate-950 p-1.5 rounded"
                               >
                                 <Trash2 size={14} />
                               </button>
                            </div>

                            {/* Item Details Form */}
                            {isItemExpanded && (
                               <div className="p-4 border-t border-slate-800 bg-slate-900/50 grid grid-cols-1 gap-4">
                                  <div>
                                    <label className="block text-xs font-medium text-slate-500 mb-1">Description (Tell AI what's inside)</label>
                                    <textarea 
                                      className="w-full bg-slate-950 border border-slate-800 rounded-md px-3 py-2 text-sm text-slate-300 focus:border-indigo-500 focus:outline-none placeholder-slate-700"
                                      rows="2"
                                      placeholder="e.g. Hot Chicken wings, crispy spring rolls..."
                                      value={item.description || ''}
                                      onChange={(e) => updateItem(categoryName, idx, 'description', e.target.value)}
                                    />
                                  </div>
                                  <div>
                                    <label className="block text-xs font-medium text-slate-500 mb-1">Allergens (comma separated)</label>
                                    <input 
                                      className="w-full bg-slate-950 border border-slate-800 rounded-md px-3 py-2 text-sm text-slate-300 focus:border-indigo-500 focus:outline-none placeholder-slate-700"
                                      value={item.allergens || ''}
                                      placeholder="e.g. gluten, soya, eggs"
                                      onChange={(e) => updateItem(categoryName, idx, 'allergens', e.target.value)}
                                    />
                                  </div>
                                  
                                  {/* Sub-Options rendering could go here as an advanced feature later */}
                                  <div className="bg-indigo-950/10 border border-indigo-900/30 rounded p-3 mt-2 flex items-center justify-between">
                                     <span className="text-xs text-indigo-400">
                                       This item has {item.options?.length || 0} Option Group(s). 
                                       <span className="text-slate-500 ml-2">(Options editing is currently view-only in GUI. Switch to Advanced Editor to modify sauce sizes etc.)</span>
                                     </span>
                                  </div>
                               </div>
                            )}
                          </div>
                        );
                      })}
                      
                      <button 
                        onClick={() => addItem(categoryName)}
                        className="w-full flex items-center justify-center gap-2 py-3 border border-dashed border-slate-700 rounded-lg text-slate-400 hover:text-indigo-400 hover:bg-slate-800/50 hover:border-indigo-500/50 transition-colors text-sm font-medium"
                      >
                        <Plus size={16} /> Add Dish to {categoryName}
                      </button>
                   </div>
                 )}
               </div>
             ))}
           </div>
        )}
      </div>
    </div>
  );
}
