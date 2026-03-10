import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import {
  Save, Plus, Trash2, Edit3, X, ChevronRight,
  UtensilsCrossed, RotateCcw, AlertTriangle, Check,
  GripVertical, Tag, DollarSign, Package, Settings2
} from 'lucide-react';

const API_URL = '/api/admin';

// ─── Utility ────────────────────────────────────────────────────────────────
const uid = () => Math.random().toString(36).slice(2, 9);

// ─── Sub-components ─────────────────────────────────────────────────────────

function AllergenTag({ text }) {
  return (
    <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-orange-500/15 text-orange-400 border border-orange-500/25">
      {text.trim()}
    </span>
  );
}

function OptionGroupEditor({ group, onChange, onDelete }) {
  const updateValue = (vIdx, field, val) => {
    const newVals = [...group.values];
    newVals[vIdx] = { ...newVals[vIdx], [field]: val };
    onChange({ ...group, values: newVals });
  };
  const addValue = () =>
    onChange({ ...group, values: [...group.values, { _id: uid(), name: 'New Option', price_mod: 0 }] });
  const removeValue = (vIdx) =>
    onChange({ ...group, values: group.values.filter((_, i) => i !== vIdx) });

  return (
    <div className="bg-slate-950 border border-slate-800 rounded-lg overflow-hidden">
      {/* Group Header */}
      <div className="flex items-center gap-2 px-3 py-2 bg-slate-900">
        <input
          className="flex-1 bg-transparent text-xs font-bold text-indigo-300 uppercase tracking-widest focus:outline-none focus:text-white border-b border-transparent focus:border-indigo-500 pb-0.5"
          value={group.name}
          onChange={e => onChange({ ...group, name: e.target.value })}
          placeholder="GROUP NAME"
        />
        <button onClick={onDelete} className="text-slate-600 hover:text-red-400 transition-colors p-0.5">
          <X size={12} />
        </button>
      </div>
      {/* Values */}
      <div className="divide-y divide-slate-800/60">
        {group.values.map((val, vIdx) => (
          <div key={val._id || vIdx} className="flex items-center gap-2 px-3 py-1.5">
            <GripVertical size={12} className="text-slate-700 shrink-0" />
            <input
              className="flex-1 bg-transparent text-xs text-slate-300 focus:outline-none focus:text-white min-w-0"
              value={val.name}
              onChange={e => updateValue(vIdx, 'name', e.target.value)}
              placeholder="Option name"
            />
            <div className="flex items-center gap-1 shrink-0">
              <span className="text-slate-600 text-xs">€</span>
              <input
                type="number"
                step="0.5"
                className="w-14 bg-slate-800 border border-slate-700 rounded px-1.5 py-0.5 text-xs text-slate-300 focus:outline-none focus:border-indigo-500 text-right"
                value={val.price_mod ?? 0}
                onChange={e => updateValue(vIdx, 'price_mod', parseFloat(e.target.value) || 0)}
              />
            </div>
            <label className="flex items-center gap-1 shrink-0 cursor-pointer" title="Default">
              <input
                type="checkbox"
                className="w-3 h-3 accent-indigo-500"
                checked={!!val.default}
                onChange={e => updateValue(vIdx, 'default', e.target.checked)}
              />
              <span className="text-[10px] text-slate-600">def</span>
            </label>
            <button onClick={() => removeValue(vIdx)} className="text-slate-700 hover:text-red-400 transition-colors">
              <X size={11} />
            </button>
          </div>
        ))}
      </div>
      <button
        onClick={addValue}
        className="w-full text-xs text-slate-600 hover:text-indigo-400 py-2 flex items-center justify-center gap-1 transition-colors hover:bg-slate-900/50"
      >
        <Plus size={11} /> Add Option
      </button>
    </div>
  );
}

function EditPanel({ item, categoryName, onSave, onClose }) {
  const [draft, setDraft] = useState(null);

  useEffect(() => {
    if (item) {
      // Normalize options for editing: each group gets _id and values get _id
      const opts = (item.options || []).map(g => ({
        ...g,
        _id: g._id || uid(),
        values: (g.values || []).map(v => ({ ...v, _id: v._id || uid() }))
      }));
      setDraft({ ...item, options: opts });
    }
  }, [item]);

  if (!draft) return null;

  const updateField = (field, val) => setDraft(prev => ({ ...prev, [field]: val }));
  const addOptionGroup = () =>
    setDraft(prev => ({
      ...prev,
      options: [...(prev.options || []), { _id: uid(), name: 'NEW GROUP', values: [] }]
    }));
  const updateGroup = (gIdx, updated) =>
    setDraft(prev => {
      const opts = [...prev.options];
      opts[gIdx] = updated;
      return { ...prev, options: opts };
    });
  const deleteGroup = (gIdx) =>
    setDraft(prev => ({ ...prev, options: prev.options.filter((_, i) => i !== gIdx) }));

  return (
    <div className="flex flex-col h-full bg-slate-900 border-l border-slate-800 w-80 shrink-0">
      {/* Panel Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800 bg-slate-900/80 backdrop-blur shrink-0">
        <div>
          <p className="text-[10px] text-slate-500 uppercase tracking-widest">{categoryName}</p>
          <h3 className="text-sm font-semibold text-white flex items-center gap-2">
            <Edit3 size={14} className="text-indigo-400" />
            {draft._isNew ? 'New Item' : 'Edit Item'}
          </h3>
        </div>
        <button onClick={onClose} className="text-slate-500 hover:text-white transition-colors p-1 rounded hover:bg-slate-800">
          <X size={16} />
        </button>
      </div>

      {/* Panel Body */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Name */}
        <div>
          <label className="text-[10px] font-semibold text-slate-500 uppercase tracking-widest mb-1.5 flex items-center gap-1">
            <Package size={10} /> Item Name
          </label>
          <input
            className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500 transition-colors"
            value={draft.name || ''}
            onChange={e => updateField('name', e.target.value)}
            placeholder="e.g. Chicken Spice Box"
          />
        </div>

        {/* Price */}
        <div>
          <label className="text-[10px] font-semibold text-slate-500 uppercase tracking-widest mb-1.5 flex items-center gap-1">
            <DollarSign size={10} /> Price (€)
          </label>
          <div className="relative">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 text-sm font-medium">€</span>
            <input
              type="number"
              step="0.5"
              min="0"
              className="w-full bg-slate-950 border border-slate-700 rounded-lg pl-7 pr-3 py-2 text-sm text-emerald-400 font-semibold focus:outline-none focus:border-indigo-500 transition-colors"
              value={draft.price ?? ''}
              onChange={e => updateField('price', parseFloat(e.target.value) || 0)}
              placeholder="0.00"
            />
          </div>
        </div>

        {/* Description */}
        <div>
          <label className="text-[10px] font-semibold text-slate-500 uppercase tracking-widest mb-1.5 block">Description</label>
          <textarea
            rows={3}
            className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-300 focus:outline-none focus:border-indigo-500 transition-colors resize-none placeholder-slate-700"
            value={draft.description || ''}
            onChange={e => updateField('description', e.target.value)}
            placeholder="Tell the AI what's inside..."
          />
        </div>

        {/* Allergens */}
        <div>
          <label className="text-[10px] font-semibold text-slate-500 uppercase tracking-widest mb-1.5 flex items-center gap-1">
            <Tag size={10} /> Allergens (comma separated)
          </label>
          <input
            className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-300 focus:outline-none focus:border-indigo-500 transition-colors"
            value={draft.allergens || ''}
            onChange={e => updateField('allergens', e.target.value)}
            placeholder="e.g. gluten, soya, eggs"
          />
        </div>

        {/* Options & Variations */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="text-[10px] font-semibold text-slate-500 uppercase tracking-widest flex items-center gap-1">
              <Settings2 size={10} /> Options & Variations
            </label>
            <button
              onClick={addOptionGroup}
              className="flex items-center gap-1 text-[10px] text-indigo-400 hover:text-indigo-300 bg-indigo-500/10 hover:bg-indigo-500/20 border border-indigo-500/30 rounded px-2 py-1 transition-colors"
            >
              <Plus size={10} /> Add Group
            </button>
          </div>
          <div className="space-y-2">
            {(draft.options || []).length === 0 && (
              <p className="text-xs text-slate-700 italic text-center py-3 border border-dashed border-slate-800 rounded-lg">
                No option groups. Click "Add Group" to create SIZE / MEAT / SAUCE etc.
              </p>
            )}
            {(draft.options || []).map((group, gIdx) => (
              <OptionGroupEditor
                key={group._id || gIdx}
                group={group}
                onChange={updated => updateGroup(gIdx, updated)}
                onDelete={() => deleteGroup(gIdx)}
              />
            ))}
          </div>
        </div>
      </div>

      {/* Panel Footer */}
      <div className="p-4 border-t border-slate-800 shrink-0">
        <button
          onClick={() => onSave(draft)}
          className="w-full flex items-center justify-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white py-2.5 rounded-xl font-semibold text-sm transition-all shadow-lg shadow-indigo-500/25 active:scale-95"
        >
          <Check size={16} /> Save Item
        </button>
      </div>
    </div>
  );
}

// ─── Main Component ──────────────────────────────────────────────────────────
export default function MenuGUI() {
  const [menuData, setMenuData]       = useState({});     // { CategoryName: [items] }
  const [activeCategory, setActiveCategory] = useState(null);
  const [editingItem, setEditingItem] = useState(null);   // { item, catName, itemIdx }
  const [loading, setLoading]         = useState(false);
  const [saving, setSaving]           = useState(false);
  const [message, setMessage]         = useState({ text: '', type: 'info' });
  const [isDirty, setIsDirty]         = useState(false);
  const [renamingCat, setRenamingCat] = useState(null);   // category name being renamed
  const [renameValue, setRenameValue] = useState('');

  // ── Flash message helper ──────────────────────────────────────────────────
  const flash = useCallback((text, type = 'info') => {
    setMessage({ text, type });
    setTimeout(() => setMessage({ text: '', type: 'info' }), 3500);
  }, []);

  // ── Load menu on mount ────────────────────────────────────────────────────
  useEffect(() => {
    fetchMenu();
  }, []);

  const fetchMenu = async () => {
    try {
      setLoading(true);
      const res = await axios.get(`${API_URL}/menu`);
      const data = JSON.parse(res.data.content);
      setMenuData(data);
      setActiveCategory(Object.keys(data)[0] || null);
      setIsDirty(false);
    } catch (err) {
      flash('Failed to load menu', 'error');
    } finally {
      setLoading(false);
    }
  };

  // ── Save to Cloud SQL ─────────────────────────────────────────────────────
  const handleSave = async () => {
    try {
      setSaving(true);
      flash('Saving to Cloud SQL...', 'info');
      await axios.post(`${API_URL}/menu`, { content: JSON.stringify(menuData, null, 4) });
      setIsDirty(false);
      flash('Menu saved & deployed to AI! ✓', 'success');
    } catch (err) {
      flash('Save failed. Check server logs.', 'error');
    } finally {
      setSaving(false);
    }
  };

  // ── Factory Reset ─────────────────────────────────────────────────────────
  const handleFactoryReset = async () => {
    if (!window.confirm('Restore the Original Factory Menu? All current changes will be lost.')) return;
    try {
      setLoading(true);
      const res = await axios.post(`${API_URL}/menu/factory-reset`);
      const data = JSON.parse(res.data.content);
      setMenuData(data);
      setActiveCategory(Object.keys(data)[0] || null);
      setEditingItem(null);
      setIsDirty(false);
      flash('Factory menu restored!', 'success');
    } catch (err) {
      flash('Factory reset failed.', 'error');
    } finally {
      setLoading(false);
    }
  };

  // ── Category Operations ───────────────────────────────────────────────────
  const addCategory = () => {
    const name = `New Category ${Date.now()}`;
    setMenuData(prev => ({ ...prev, [name]: [] }));
    setActiveCategory(name);
    setRenamingCat(name);
    setRenameValue(name);
    setIsDirty(true);
  };

  const beginRename = (catName, e) => {
    e.stopPropagation();
    setRenamingCat(catName);
    setRenameValue(catName);
  };

  const commitRename = () => {
    if (!renamingCat || !renameValue.trim() || renameValue === renamingCat) {
      setRenamingCat(null);
      return;
    }
    const newName = renameValue.trim();
    setMenuData(prev => {
      const entries = Object.entries(prev);
      const idx = entries.findIndex(([k]) => k === renamingCat);
      entries[idx] = [newName, entries[idx][1]];
      return Object.fromEntries(entries);
    });
    if (activeCategory === renamingCat) setActiveCategory(newName);
    setRenamingCat(null);
    setIsDirty(true);
  };

  const deleteCategory = (catName, e) => {
    e.stopPropagation();
    if (!window.confirm(`Delete category "${catName}" and all its items?`)) return;
    setMenuData(prev => {
      const next = { ...prev };
      delete next[catName];
      return next;
    });
    if (activeCategory === catName) {
      const remaining = Object.keys(menuData).filter(k => k !== catName);
      setActiveCategory(remaining[0] || null);
    }
    if (editingItem?.catName === catName) setEditingItem(null);
    setIsDirty(true);
  };

  // ── Item Operations ───────────────────────────────────────────────────────
  const openNewItem = () => {
    if (!activeCategory) return;
    setEditingItem({
      item: { _isNew: true, name: '', price: 0, description: '', allergens: '', options: [] },
      catName: activeCategory,
      itemIdx: -1,
    });
  };

  const openEditItem = (catName, itemIdx) => {
    const item = menuData[catName][itemIdx];
    setEditingItem({ item: { ...item }, catName, itemIdx });
  };

  const handleSaveItem = (draft) => {
    const { catName, itemIdx } = editingItem;
    // Strip internal _id keys before saving
    const clean = {
      name: draft.name,
      price: draft.price,
      description: draft.description,
      allergens: draft.allergens,
      options: (draft.options || []).map(g => ({
        name: g.name,
        values: (g.values || []).map(v => ({
          name: v.name,
          price_mod: v.price_mod ?? 0,
          ...(v.default ? { default: true } : {})
        }))
      }))
    };
    setMenuData(prev => {
      const items = [...(prev[catName] || [])];
      if (itemIdx === -1) {
        items.push(clean);
      } else {
        items[itemIdx] = clean;
      }
      return { ...prev, [catName]: items };
    });
    setEditingItem(null);
    setIsDirty(true);
  };

  const deleteItem = (catName, itemIdx, e) => {
    e.stopPropagation();
    if (!window.confirm(`Delete "${menuData[catName][itemIdx]?.name}"?`)) return;
    setMenuData(prev => {
      const items = [...prev[catName]];
      items.splice(itemIdx, 1);
      return { ...prev, [catName]: items };
    });
    if (editingItem?.catName === catName && editingItem?.itemIdx === itemIdx) {
      setEditingItem(null);
    }
    setIsDirty(true);
  };

  // ── Render ────────────────────────────────────────────────────────────────
  const categories = Object.keys(menuData);
  const currentItems = activeCategory ? (menuData[activeCategory] || []) : [];

  const msgColor = message.type === 'success' ? 'text-emerald-400'
                 : message.type === 'error'   ? 'text-red-400'
                 : 'text-indigo-300';

  return (
    <div className="flex h-[calc(100vh-13rem)] border border-slate-800 rounded-2xl overflow-hidden bg-slate-950 shadow-2xl mt-6">

      {/* ── LEFT: Category Sidebar ─────────────────────────────────────── */}
      <div className="flex flex-col w-52 bg-slate-900 border-r border-slate-800 shrink-0">
        {/* Sidebar Header */}
        <div className="p-4 border-b border-slate-800">
          <div className="flex items-center gap-2 mb-3">
            <div className="p-1.5 bg-indigo-500/15 rounded-lg">
              <UtensilsCrossed size={14} className="text-indigo-400" />
            </div>
            <span className="text-sm font-bold text-white">菜单数据库</span>
          </div>
          <button
            onClick={addCategory}
            className="w-full flex items-center justify-center gap-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white text-xs py-2 rounded-lg transition-colors border border-slate-700 hover:border-slate-600"
          >
            <Plus size={12} /> 添加分类
          </button>
        </div>

        {/* Category List */}
        <div className="flex-1 overflow-y-auto py-2">
          {categories.length === 0 && (
            <p className="text-xs text-slate-600 italic text-center px-4 py-8">
              No categories yet. Click "添加分类" to start.
            </p>
          )}
          {categories.map(catName => {
            const isActive = catName === activeCategory;
            const isRenaming = catName === renamingCat;
            return (
              <div
                key={catName}
                onClick={() => { setActiveCategory(catName); }}
                className={`group relative flex items-center gap-2 mx-2 mb-1 px-3 py-2.5 rounded-lg cursor-pointer transition-all duration-150 ${
                  isActive
                    ? 'bg-indigo-600/20 border border-indigo-500/40 text-white'
                    : 'text-slate-400 hover:bg-slate-800/60 hover:text-slate-200 border border-transparent'
                }`}
              >
                {isActive && <div className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 bg-indigo-500 rounded-r" />}

                {isRenaming ? (
                  <input
                    autoFocus
                    className="flex-1 bg-slate-800 border border-indigo-500 rounded px-1.5 py-0.5 text-xs text-white focus:outline-none min-w-0"
                    value={renameValue}
                    onChange={e => setRenameValue(e.target.value)}
                    onBlur={commitRename}
                    onKeyDown={e => { if (e.key === 'Enter') commitRename(); if (e.key === 'Escape') setRenamingCat(null); }}
                    onClick={e => e.stopPropagation()}
                  />
                ) : (
                  <>
                    <span className="flex-1 text-xs font-medium truncate">{catName}</span>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded-full shrink-0 ${
                      isActive ? 'bg-indigo-500/30 text-indigo-300' : 'bg-slate-800 text-slate-600'
                    }`}>
                      {(menuData[catName] || []).length}
                    </span>
                  </>
                )}

                {/* Action buttons on hover */}
                {!isRenaming && (
                  <div className="hidden group-hover:flex items-center gap-0.5 shrink-0">
                    <button
                      onClick={e => beginRename(catName, e)}
                      className="p-0.5 text-slate-600 hover:text-indigo-400 transition-colors"
                      title="Rename"
                    >
                      <Edit3 size={10} />
                    </button>
                    <button
                      onClick={e => deleteCategory(catName, e)}
                      className="p-0.5 text-slate-600 hover:text-red-400 transition-colors"
                      title="Delete category"
                    >
                      <Trash2 size={10} />
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Sidebar Footer */}
        <div className="p-3 border-t border-slate-800 space-y-2">
          {/* Factory Reset */}
          <button
            onClick={handleFactoryReset}
            disabled={loading}
            className="w-full flex items-center justify-center gap-1.5 text-xs text-slate-500 hover:text-red-400 py-1.5 rounded-lg transition-colors hover:bg-red-500/5 border border-transparent hover:border-red-500/20"
          >
            <RotateCcw size={11} /> Factory Reset
          </button>

          {/* Save Button */}
          <button
            onClick={handleSave}
            disabled={saving || !isDirty}
            className={`w-full flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-semibold transition-all duration-200 ${
              isDirty
                ? 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-500/25 active:scale-95'
                : 'bg-slate-800 text-slate-600 cursor-not-allowed'
            }`}
          >
            {saving ? (
              <span className="animate-pulse">Saving...</span>
            ) : (
              <>
                <Save size={14} />
                Save & Deploy
                {isDirty && (
                  <span className="w-2 h-2 bg-orange-400 rounded-full animate-pulse" />
                )}
              </>
            )}
          </button>
        </div>
      </div>

      {/* ── CENTER: Item Card Grid ─────────────────────────────────────── */}
      <div className="flex flex-col flex-1 min-w-0 bg-slate-950">
        {/* Top Bar */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-slate-800 shrink-0">
          <div className="flex items-center gap-3 min-w-0">
            {activeCategory ? (
              <>
                <h2 className="text-base font-bold text-white truncate">{activeCategory}</h2>
                <span className="text-xs text-slate-500 shrink-0">{currentItems.length} items</span>
              </>
            ) : (
              <h2 className="text-base font-bold text-slate-600">Select a category</h2>
            )}
          </div>
          <div className="flex items-center gap-3 shrink-0">
            {message.text && (
              <span className={`text-xs ${msgColor} animate-pulse`}>{message.text}</span>
            )}
            {activeCategory && (
              <button
                onClick={openNewItem}
                className="flex items-center gap-1.5 bg-indigo-600 hover:bg-indigo-500 text-white text-xs px-3 py-2 rounded-lg font-medium transition-all shadow-lg shadow-indigo-500/25 active:scale-95"
              >
                <Plus size={13} /> Add Item
              </button>
            )}
          </div>
        </div>

        {/* Item Grid */}
        <div className="flex-1 overflow-y-auto p-4">
          {loading ? (
            <div className="flex items-center justify-center h-full">
              <div className="flex flex-col items-center gap-3 text-slate-600">
                <div className="w-8 h-8 border-2 border-slate-700 border-t-indigo-500 rounded-full animate-spin" />
                <span className="text-sm">Loading Menu from Cloud SQL...</span>
              </div>
            </div>
          ) : !activeCategory ? (
            <div className="flex items-center justify-center h-full text-slate-700 text-sm">
              ← Select a category from the sidebar
            </div>
          ) : currentItems.length === 0 ? (
            <div
              onClick={openNewItem}
              className="flex flex-col items-center justify-center h-48 border-2 border-dashed border-slate-800 rounded-2xl text-slate-700 cursor-pointer hover:border-indigo-500/50 hover:text-indigo-500 transition-colors"
            >
              <Plus size={24} className="mb-2" />
              <span className="text-sm font-medium">Add first item to {activeCategory}</span>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3 pb-4">
              {currentItems.map((item, idx) => {
                const isEditing = editingItem?.catName === activeCategory && editingItem?.itemIdx === idx;
                const allergenList = item.allergens ? item.allergens.split(',').filter(Boolean) : [];
                return (
                  <div
                    key={idx}
                    onClick={() => openEditItem(activeCategory, idx)}
                    className={`group relative flex flex-col bg-slate-900 border rounded-xl p-3.5 cursor-pointer transition-all duration-150 hover:border-indigo-500/60 hover:-translate-y-0.5 hover:shadow-lg hover:shadow-indigo-500/10 ${
                      isEditing ? 'border-indigo-500/80 ring-1 ring-indigo-500/30' : 'border-slate-800'
                    }`}
                  >
                    {/* Card Top */}
                    <div className="flex items-start justify-between gap-2 mb-2">
                      <h4 className="text-sm font-semibold text-white leading-tight line-clamp-2 flex-1">
                        {item.name || <span className="text-slate-600 italic">Unnamed</span>}
                      </h4>
                      <span className="text-base font-bold text-emerald-400 shrink-0">
                        €{Number(item.price).toFixed(2)}
                      </span>
                    </div>

                    {/* Description */}
                    {item.description && (
                      <p className="text-xs text-slate-500 line-clamp-2 mb-2 leading-relaxed">
                        {item.description}
                      </p>
                    )}

                    {/* Footer Badges */}
                    <div className="mt-auto pt-2 flex flex-wrap items-center gap-1.5">
                      {allergenList.map((a, ai) => <AllergenTag key={ai} text={a} />)}
                      {(item.options?.length > 0) && (
                        <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium bg-slate-800 text-slate-500 border border-slate-700">
                          <Settings2 size={9} /> {item.options.length} opt{item.options.length !== 1 ? 's' : ''}
                        </span>
                      )}
                    </div>

                    {/* Hover action buttons */}
                    <div className="absolute top-2.5 right-2.5 hidden group-hover:flex items-center gap-1 bg-slate-950/90 backdrop-blur rounded-lg p-1 border border-slate-700">
                      <button
                        onClick={e => { e.stopPropagation(); openEditItem(activeCategory, idx); }}
                        className="p-1 text-slate-400 hover:text-indigo-400 transition-colors"
                        title="Edit"
                      >
                        <Edit3 size={12} />
                      </button>
                      <button
                        onClick={e => deleteItem(activeCategory, idx, e)}
                        className="p-1 text-slate-400 hover:text-red-400 transition-colors"
                        title="Delete"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* ── RIGHT: Edit Panel ──────────────────────────────────────────── */}
      <div className={`transition-all duration-300 ease-in-out overflow-hidden ${editingItem ? 'w-80' : 'w-0'}`}>
        {editingItem && (
          <EditPanel
            item={editingItem.item}
            categoryName={editingItem.catName}
            onSave={handleSaveItem}
            onClose={() => setEditingItem(null)}
          />
        )}
      </div>
    </div>
  );
}
