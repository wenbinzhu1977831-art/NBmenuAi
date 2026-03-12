import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { 
  Settings, Bot, PhoneCall, ListOrdered, FileText, 
  RefreshCw, Save, CheckCircle2, XCircle, Power, 
  Webhook, BookOpen, Coffee, Code, Hash, Euro, Globe, Terminal, User, Users, MapPin, Trash2,
  BarChart2, Lock, LogOut, PhoneForwarded, PhoneIncoming
} from 'lucide-react';
import CodeEditor from './components/CodeEditor';

import MenuGUI from './components/MenuGUI';
import WebCallSimulator from './components/WebCallSimulator';
import {
  LineChart, Line, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, Legend, ResponsiveContainer,
  PieChart, Pie, Cell
} from 'recharts';

// Use relative path so it seamlessly works whether on port 5000, 5001 or any Cloud Run port.
// For local pure-frontend dev, you can prefix this with http://localhost:5000 once conditionally.
const API_URL = window.location.host.includes('localhost:5173')
  ? 'http://localhost:5000/api/admin'
  : '/api/admin';

const translations = {
  en: {
    dashboard: "Live Dashboard",
    history: "History Orders",
    customers: "Customer Info",
    analytics: "Call Analytics",
    ai: "AI Brain Core",
    menu: "Menu & Logic",
    tools: "System Scripts",
    config: "System Config",
    brandName: "AI Ordering System",
    controlPanel: "Control Panel",
    status: "Status",
    offline: "Offline",
    active: "Active",
    bypass: "Bypass",
    deploy: "Deploy Settings",
    saving: "Saving...",
    saved: "Saved!",
    fetchFailed: "Fetch failed!",
    saveFailed: "Save Failed!",
    init: "Initializing AI Control Panel...",
    
    // Dashboard
    aiCallsActive: "AI Calls Active",
    liveWs: "Live WebSocket Connections",
    ordersProcessed: "Orders Processed",
    todayViaAI: "Today via AI Server",
    lastSync: "Last Master Sync",
    nextSync: "Next sync in 3 mins",
    omniSync: "Omnichannel Sync Status",
    syncMsg1: "[INFO] Sync Script Idle... waiting for internal cron trigger.",
    syncMsg2: "[WARN] No external master platform configured in webhook endpoints.",
    syncMsg3: "System relying on local SQLite `app.db` until sync strategy is activated.",

    // AI Brain
    masterSwitch: "Master Switch & Call Routing",
    activeLabel: "Active (AI Takes Orders)",
    activeDesc: "AI will answer and process the full order flow.",
    bypassLabel: "Bypass to Human",
    bypassDesc: "AI answers, plays a message, and transfers directly.",
    offlineLabel: "Offline (Closed)",
    offlineDesc: "Hang up on all calls. Optionally play message.",
    bypassMessage: "Bypass Message (TTS voice)",
    bypassHelp: "Played right before transferring.",
    offlineMessage: "Offline Message (TTS voice)",
    offlineHelp: "Played right before hanging up. Leave blank to reject call immediately without answering.",
    waitQueueTitle: "Incoming Call Info",
    minWait: "min wait",
    transferBtn: "Transfer to Human",
    transferSuccess: "Transfer initiated to human agent.",
    transferFailed: "Failed to transfer customer. They might have hung up.",
    maxCalls: "Max Concurrent Calls",
    maxCallsHelp: "Calls exceeding this limit will be rejected.",
    concurrentCallsTitle: "Concurrent Call Limits",
    busyMessageLabel: "Busy Message (TTS)",
    busyMessageHelp: "Leave blank = direct busy tone (no answer); fill in = answer, play TTS, then hang up.",
    busyMessagePlaceholder: "Leave blank = busy tone; fill in = TTS then hang up",
    noCallLog: "No incoming calls yet",
    callLogMoreFmt: "Showing latest 20 of {n} total",
    linesSuffix: "lines",
    callActive: "🟢 Active",
    callCompleted: "⚫ Ended",
    callMissed: "🔴 Missed",
    tooltipWebrtc: "WebRTC Browser Call",
    tooltipTwilio: "Twilio Phone Call",
    tooltipOrderDone: "Order completed",
    tooltipOrderMissed: "Call ended without order",
    tooltipNoOrder: "No order placed",
    tooltipTransferred: "Transferred to human",
    modelSpecs: "Model Specifications",
    geminiModel: "Gemini Model",
    voicePersonality: "Voice Personality",

    // Menu Logic
    pricingRules: "Pricing & Global Rules",
    minDel: "Minimum Delivery Order (€)",
    cardFee: "Card Payment Surcharge (€)",
    globalDiscount: "Global Discount Engine",
    enableDiscount: "Enable Universal Promotional Discount",
    discountType: "Discount Type",
    pctOff: "Percentage (e.g. 10% off)",
    fixedOff: "Fixed Amount (e.g. 5 Euro off)",
    discountValue: "Discount Value",
    discountHelp: "If Percentage: use 0.10 for 10%. If fixed, use 5.0 for €5.",
    promoPitch: "Promotion Pitch (AI Awareness Text)",
    promoHelp: "Tell the AI what the promo is so it can brag about it to the customer.",

    // Config
    apiKeys: "API Keys (Secure)",
    googleKey: "Google Gemini API Key",
    autoAddressKey: "AutoAddress API Key (Ireland)",
    telephony: "Telephony Logic",
    humanNumber: "Human Transfer Number",
    humanHelp: "Include country code (+353...)",

    // Delivery & Editor
    deliveryAreaTitle: "Delivery Areas & Fees",
    saveDeliveryArea: "Save Delivery Areas",
    deliveryAreaHint: "Configure your delivery zones and their associated charges here. The AI will look up the customer's area in this list to automatically apply the correct delivery fee. Ensure each line follows the format: AreaName ........ €Fee",

    // WebRTC Simulator
    webSimTitle: "WebRTC Call Simulator",
    webSimDesc: "Test your AI agent directly from your browser's microphone without a real phone line. Simulates an incoming Twilio call.",
    virtualNumber: "Virtual Phone Number",
    startCall: "Start Voice Call",
    aiBusyBtn: "AI Currently Busy",
    endCall: "End Call",
    liveAudio: "Live Audio",

    // OrdersView
    noHistoryOrders: "No orders found",
    draftIncomplete: "Draft/Incomplete",
    itemUnit: "items",
    deleteOrder: "Delete Order",
    transcriptTitle: "Live Audio Transcript",
    noTranscript: "No transcript available",
    userRole: "Customer (User)",
    aiRole: "AI Agent",
    orderContentTitle: "Order Details",
    orderIdLabel: "Order ID:",
    orderCustomerLabel: "Customer:",
    orderPhoneLabel: "Phone:",
    orderAddressLabel: "Address:",
    orderDeliveryLabel: "Delivery:",
    orderNoteLabel: "Note:",
    orderNoteEmpty: "None",
    itemReceipt: "Itemized Receipt",
    deliveryFeeLabel: "Delivery Fee:",
    totalLabel: "Total",
    backToList: "Back to List",
    allHistoryTitle: "All History Orders",
    
    // Auth & Locks
    loginTitle: "System Authentication",
    staffAccess: "Staff Access",
    staffDesc: "Monitor live orders and dashboard stats",
    adminAccess: "Admin Control",
    adminDesc: "Full access to settings and AI logic",
    passwordLabel: "Admin Password",
    enterPassword: "Enter password...",
    loginBtn: "Login",
    unauthorized: "Unauthorized Access",
    lockedDesc: "This section requires Administrator privileges to view and alter system configurations.",
    logout: "Log Out",
    changePwd: "Change Admin Password",
    newPwd: "New Password",
    confirmPwd: "Confirm Password",
    updatePwdBtn: "Update Password",
  },
  zh: {
    dashboard: "实时仪表盘",
    history: "历史单据",
    customers: "客户信息",
    analytics: "通话分析",
    ai: "AI 大脑核心",
    menu: "菜单与费率",
    tools: "系统工具与脚本",
    config: "系统设置",
    brandName: "人工智能点餐系统",
    controlPanel: "控制台",
    status: "当前状态",
    offline: "停机离线",
    active: "运行中",
    bypass: "转接人工",
    deploy: "保存并部署",
    saving: "保存中...",
    saved: "已保存!",
    fetchFailed: "加载配置失败!",
    saveFailed: "保存失败!",
    init: "正在初始化 AI 控制台...",

    // Dashboard
    aiCallsActive: "当前 AI 通话数",
    liveWs: "实时 WebSocket 连接",
    ordersProcessed: "已处理订单",
    todayViaAI: "今日 AI 成功接单",
    lastSync: "上次全渠道同步",
    nextSync: "下次同步时间: 3分钟后",
    omniSync: "全渠道聚合状态",
    syncMsg1: "[INFO] 同步脚本空闲... 等待内部定时任务触发。",
    syncMsg2: "[WARN] 尚未配置外部现有系统 Webhook 终点。",
    syncMsg3: "在配置同步策略前，系统将使用本地 SQLite `app.db` 独立运行。",

    // AI Brain
    masterSwitch: "AI 点餐员总开关与路由",
    activeLabel: "运行中 (AI 接单)",
    activeDesc: "AI 将直接接听来电并处理完整的点餐流程。",
    bypassLabel: "人工转接模式",
    bypassDesc: "AI 接听，播放提示音后直接转接给人工客服。",
    offlineLabel: "关店离线模式",
    offlineDesc: "挂断所有来电，可选择在此之前播放打烊语音。",
    bypassMessage: "转接前提示语音 (TTS)",
    bypassHelp: "在呼叫转移给人工前播放给客人的语音。",
    offlineMessage: "离线打烊语音 (TTS)",
    offlineHelp: "挂断电话前播放。如果留空，系统将直接拒接来电以节省 Twilio 通话费。",
    waitMessage: "排队提示语音 (TTS)",
    waitMusicUrl: "排队等待音乐链接 (MP3)",
    waitQueueTitle: "电话呼入信息区",
    minWait: "分钟等待",
    transferBtn: "转接人工客服",
    transferSuccess: "已成功下达转接指令。",
    transferFailed: "转接失败，该用户可能已挂断。",
    maxCalls: "最大并发通话数",
    maxCallsHelp: "超过此数量的来电将被拒绝。",
    concurrentCallsTitle: "并发通话限制",
    busyMessageLabel: "繁忙话术 (TTS)",
    busyMessageHelp: "留空 = 直接忙音拒接（不接通）；填内容 = 接通后 TTS 播报内容再挂断。",
    busyMessagePlaceholder: "留空 = 直接忙音（不接通）；填内容 = TTS 播报后挂断",
    noCallLog: "暂无呼入记录",
    callLogMoreFmt: "仅显示最新20条，共{n}条",
    linesSuffix: "路",
    callActive: "🟢 进行中",
    callCompleted: "⚫ 已结束",
    callMissed: "🔴 未接通",
    tooltipWebrtc: "WebRTC 网页通话",
    tooltipTwilio: "Twilio 电话",
    tooltipOrderDone: "订单已完成",
    tooltipOrderMissed: "通话结束未完成订单",
    tooltipNoOrder: "未下单",
    tooltipTransferred: "已转人工",
    modelSpecs: "模型参数配置",
    geminiModel: "Gemini 语音大模型",
    voicePersonality: "语音音色性格",

    // Menu Logic
    pricingRules: "交易与配送规则",
    minDel: "最低配送金额 (€)",
    cardFee: "银行卡付款手续费 (€)",
    globalDiscount: "全局折扣引擎",
    enableDiscount: "启用全局促销折扣活动",
    discountType: "折扣类型",
    pctOff: "百分比折扣 (例如: 10% Off)",
    fixedOff: "固定金额减免 (例如: 立减 5 欧元)",
    discountValue: "折扣数值设定",
    discountHelp: "若是百分比，10% 请填 0.10。若是固定金额，减€5请填 5.0。",
    promoPitch: "促销话术 (AI 大脑感知)",
    promoHelp: "告诉 AI 目前的活动，AI 会在通话中主动并热情地告知客户！",

    // Config
    apiKeys: "API 密钥管理 (安全)",
    googleKey: "Google Gemini API 密钥",
    autoAddressKey: "AutoAddress API 密钥 (爱尔兰)",
    telephony: "电话通讯逻辑",
    humanNumber: "人工客服转接号码",
    humanHelp: "需包含国家代码 (例如 +353...)",

    // Delivery & Editor
    deliveryAreaTitle: "配送规则与邮费",
    saveDeliveryArea: "保存配送规则",
    deliveryAreaHint: "在此配置您的派送区域及其相关费用。AI 将在此列表中查找客户区域以自动应用正确的配送费。确保每一行遵循格式：【区域名称 ........ €费用】",

    // WebRTC Simulator
    webSimTitle: "WebRTC 网页通话模拟器",
    webSimDesc: "不打电话也能直接测试！允许麦克风权限后，可以在网页完全模拟真实的 Twilio 客户来电场景以测试 AI。",
    virtualNumber: "模拟来电号码",
    startCall: "开始语音通话",
    aiBusyBtn: "AI 正忙，禁止呼入",
    endCall: "挂断通话",
    liveAudio: "实时语音",

    // OrdersView
    noHistoryOrders: "暂无订单数据",
    draftIncomplete: "草稿/断线",
    itemUnit: "件商品",
    deleteOrder: "删除订单",
    transcriptTitle: "通话转录记录 (Transcript)",
    noTranscript: "无对话记录",
    userRole: "客户 (User)",
    aiRole: "AI 助理",
    orderContentTitle: "订单详情",
    orderIdLabel: "单号:",
    orderCustomerLabel: "客户:",
    orderPhoneLabel: "电话:",
    orderAddressLabel: "地址:",
    orderDeliveryLabel: "配送:",
    orderNoteLabel: "备注:",
    orderNoteEmpty: "无",
    itemReceipt: "商品明细",
    deliveryFeeLabel: "配送费:",
    totalLabel: "总计",
    backToList: "返回列表",
    allHistoryTitle: "全部历史订单 (All History)",
    
    // Auth & Locks
    loginTitle: "系统身份认证",
    staffAccess: "员工视图 (Staff)",
    staffDesc: "监控实时订单与通话数据",
    adminAccess: "高级后台 (Admin)",
    adminDesc: "接管 AI 逻辑设置与核心参数",
    passwordLabel: "管理员密码",
    enterPassword: "请输入密码...",
    loginBtn: "登录系统",
    unauthorized: "权限不足 (Unauthorized)",
    lockedDesc: "对不起，此区域被密码锁定，您需要切换为管理员身份才能查看和修改此页面的配置。",
    logout: "退出登录",
    changePwd: "修改管理员密码",
    newPwd: "新密码",
    confirmPwd: "确认新密码",
    updatePwdBtn: "更新密码",
  }
};

function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saveStatus, setSaveStatus] = useState('');
  
  // -- Auth States --
  const [sysToken, setSysToken] = useState(localStorage.getItem('sys_token') || null);
  const [sysRole, setSysRole] = useState(localStorage.getItem('sys_role') || null);
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [pwdStatus, setPwdStatus] = useState('');




  
  // -- Active Mode --
  const [menuViewMode, setMenuViewMode] = useState('gui');
  // -- Real-time Data States --
  const [activeCallCount, setActiveCallCount] = useState(0);
  const [activeCallsList, setActiveCallsList] = useState({}); // { sid: { start_time, caller_number, caller_name } }
  const [activeViewCallSid, setActiveViewCallSid] = useState(null); // Which call's transcript is currently visible
  // 按 call_sid 分组存储，彩道隔离，并发通话不互串
  const [transcripts, setTranscripts] = useState({}); // { [call_sid]: [{id,role,text,is_final},...] }
  const [totalOrders, setTotalOrders] = useState(0);         // 今日完成订单数
  const [incompleteOrders, setIncompleteOrders] = useState(0); // 今日草稿/断线订单数
  const [dashboardStats, setDashboardStats] = useState(null); // The historical trend stats
  const [liveOrder, setLiveOrder] = useState(null); // Real-time order data being built
  const [aiBusy, setAiBusy] = useState(false);

  // Orders Modal States
  const [showOrdersModal, setShowOrdersModal] = useState(false);
  const [ordersList, setOrdersList] = useState([]);
  const [allOrdersList, setAllOrdersList] = useState([]);
  const [customersList, setCustomersList] = useState([]);
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [orderToDelete, setOrderToDelete] = useState(null);

  // Delivery Area state
  const [deliveryAreaText, setDeliveryAreaText] = useState('');
  const [deliveryAreaSaveStatus, setDeliveryAreaSaveStatus] = useState('');
  
  // Language toggle state
  const [lang, setLang] = useState('zh');
  const t = (key) => translations[lang][key] || key;

  // 导航时不再需要检查密码
  const navigateTo = (tab) => {
    setActiveTab(tab);
  };

  // 模型历史记录：从 localStorage 读取，首次使用时预填内置常用模型
  const [modelHistory, setModelHistory] = useState(() => {
    try {
      const saved = localStorage.getItem('gemini_model_history');
      if (saved) return JSON.parse(saved);
    } catch {}
    // 内置常用模型作为默认历史，方便首次使用
    return [
      'models/gemini-2.5-flash-native-audio-preview-12-2025',
      'models/gemini-2.0-flash-live-001',
    ];
  });

  // 初始化时，如果已有 token，尝试自动登录
  useEffect(() => {
    if (sysToken) {
      // Setup Axios interceptors once we have a token
      const reqInterceptor = axios.interceptors.request.use(config => {
        config.headers.Authorization = `Bearer ${sysToken}`;
        return config;
      });

      const resInterceptor = axios.interceptors.response.use(
        response => response,
        error => {
          // 401 Means token is invalid/expired -> logout.
          // 403 Means insufficient permissions (e.g. Staff trying to fetch Settings). Do not auto-logout.
          if (error.response && error.response.status === 401) {
            handleLogout();
          }
          return Promise.reject(error);
        }
      );

      fetchSettings();
      initWebSocket();

      return () => {
        axios.interceptors.request.eject(reqInterceptor);
        axios.interceptors.response.eject(resInterceptor);
      };
    }
  }, [sysToken]);

  const handleLogout = () => {
    setSysToken(null);
    setSysRole(null);
    setActiveTab('dashboard');
    localStorage.removeItem('sys_token');
    localStorage.removeItem('sys_role');
  };
  
  const initWebSocket = () => {
    if (!sysToken) return;
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    
    // Support Vite dev server on port 5173
    const wsUrl = window.location.host.includes('localhost:5173')
      ? `ws://localhost:5000/api/admin/ws?token=${sysToken}`
      : `${protocol}//${window.location.host}/api/admin/ws?token=${sysToken}`;
      
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => console.log('Admin WS Connected');
    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        
        if (msg.event === 'sync') {
          if (msg.data.active_count !== undefined) setActiveCallCount(msg.data.active_count);
          if (msg.data.active_calls) setActiveCallsList(msg.data.active_calls);
          if (msg.data.total_orders !== undefined) setTotalOrders(msg.data.total_orders);
          if (msg.data.incomplete_orders !== undefined) setIncompleteOrders(msg.data.incomplete_orders);
          if (msg.data.ai_status !== undefined) setAiBusy(msg.data.ai_status.busy);
          if (msg.data.call_log !== undefined) setCallLog(msg.data.call_log);
        } else if (msg.event === 'new_order') {
          if (msg.data && msg.data.total_orders !== undefined) {
             setTotalOrders(msg.data.total_orders);
          }
          if (msg.data && msg.data.incomplete_orders !== undefined) {
             setIncompleteOrders(msg.data.incomplete_orders);
          }
        } else if (msg.event === 'call_start') {
          setActiveCallCount(msg.data.active_count);
          setActiveCallsList(msg.data.active_calls || {});
          // 不立刻清空小票和转写 — 等新通话的第一条转写到达再清
          setActiveViewCallSid(msg.data.call_sid);
          
        } else if (msg.event === 'call_end') {
          setActiveCallCount(msg.data.active_count);
          setActiveCallsList(msg.data.active_calls || {});
          const endedSid = msg.data.call_sid;
          setTranscripts(prev => ({
            ...prev,
            [endedSid]: [...(prev[endedSid] || []), { id: Date.now(), role: 'system', text: 'Call ended', is_final: true }]
          }));
        } else if (msg.event === 'transcript') {
          const { role, text, is_final, call_sid } = msg.data;

          // 切换当前视图到最新话路
          setActiveViewCallSid(current => current || call_sid);

          setTranscripts(prev => {
            const callEntries = [...(prev[call_sid] || [])];

            if ((role === 'user' || role === 'ai') && !is_final) {
              // 流式 chunk（服务端发送增量）：必须累加到已有文本后面
              const lastIdx = callEntries.length - 1;
              if (lastIdx >= 0 && callEntries[lastIdx].role === role && !callEntries[lastIdx].is_final) {
                const accText = callEntries[lastIdx].text + text; // 就是 prevText + 新chunk
                callEntries[lastIdx] = { ...callEntries[lastIdx], text: accText };
                return { ...prev, [call_sid]: callEntries };
              }
              // 新开一条流式条目
              return { ...prev, [call_sid]: [...callEntries, { id: Date.now() + Math.random(), role, text, is_final: false }] };
            }

            if ((role === 'user' || role === 'ai') && is_final) {
              // 完成 chunk：封厕最后一条未完成条目
              const lastIdx = callEntries.length - 1;
              if (lastIdx >= 0 && callEntries[lastIdx].role === role && !callEntries[lastIdx].is_final) {
                callEntries[lastIdx] = { ...callEntries[lastIdx], text, is_final: true };
                return { ...prev, [call_sid]: callEntries };
              }
              return { ...prev, [call_sid]: [...callEntries, { id: Date.now() + Math.random(), role, text, is_final: true }] };
            }

            // thought / system / tool 等直接追加
            return { ...prev, [call_sid]: [...callEntries, { id: Date.now() + Math.random(), role, text, is_final: true }] };
          });
        } else if (msg.event === 'ai_status') {
          setAiBusy(msg.data.busy);
        } else if (msg.event === 'call_log_update') {
          setCallLog(msg.data || []);
        } else if (msg.event === 'system_log') {
          const sid = msg.data.call_sid || '__system__';
          setTranscripts(prev => ({
            ...prev,
            [sid]: [...(prev[sid] || []), { id: Date.now() + Math.random(), role: 'system_log', text: msg.data.message, type: msg.data.type || 'info' }]
          }));
        } else if (msg.event === 'tool_call') {
          // 注：由于后端 (server.py + audio_injector.py) 现在已经原生向 WebSocket 音频流
          // 注入了高保真的预读取 WAV 打字声音，前端不再需要（也不能）使用
          // Web Audio API 来模拟发声，否则会导致回音混缩。

          msg.data.calls.forEach(c => {
            let toolDesc = "正在处理...";
            if (c.name === 'search_address') toolDesc = "正在查询地址...";
            else if (c.name === 'calculate_total') toolDesc = "正在计算订单金额...";
            else if (c.name === 'get_business_hours') toolDesc = "正在查询营业时间...";
            else if (c.name === 'get_restaurant_status') toolDesc = "正在查询门店状态...";
            else if (c.name === 'check_delivery_availability') toolDesc = "正在查询配送信息...";
            else if (c.name === 'get_past_order') toolDesc = "正在查询历史订单...";
            else if (c.name === 'end_call') toolDesc = "正在生成并保存订单...";
            
            const sid = msg.data.call_sid || activeViewCallSid || '__unknown__';
            const text = `⚙️ [系统] ${toolDesc}`;
            setTranscripts(prev => ({
              ...prev,
              [sid]: [...(prev[sid] || []), { id: Date.now() + Math.random(), role: 'tool', text, args: c.args, is_animating: true }]
            }));
          });
        } else if (msg.event === 'tool_response') {
          // Play a gentle "success" chime
          try {
            const AudioContext = window.AudioContext || window.webkitAudioContext;
            if (AudioContext) {
              const ctx = new AudioContext();
              const osc = ctx.createOscillator();
              const gain = ctx.createGain();
              osc.connect(gain);
              gain.connect(ctx.destination);
              osc.type = 'triangle';
              osc.frequency.setValueAtTime(800, ctx.currentTime);
              osc.frequency.exponentialRampToValueAtTime(400, ctx.currentTime + 0.1);
              gain.gain.setValueAtTime(0.03, ctx.currentTime);
              gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.1);
              osc.start(ctx.currentTime);
              osc.stop(ctx.currentTime + 0.1);
            }
          } catch(e) {}

          // 将最近一条 tool 条目标记为已完成
          setTranscripts(prev => {
            const sid = activeViewCallSid || Object.keys(prev).pop();
            if (!sid || !prev[sid]) return prev;
            const entries = [...prev[sid]];
            for (let i = entries.length - 1; i >= 0; i--) {
              if (entries[i].role === 'tool' && entries[i].is_animating) {
                entries[i] = { ...entries[i], is_animating: false, text: entries[i].text + ' (已完成)' };
                break;
              }
            }
            return { ...prev, [sid]: entries };
          });
        } else if (msg.event === 'live_order_update') {
          setLiveOrder(msg.data);
        }
      } catch (err) {
        console.error('WS parse error', err);
      }
    };
    ws.onclose = (event) => {
      console.log(`Admin WS Disconnected (Code: ${event.code}), retrying in 3s...`);
      setTimeout(() => initWebSocket(), 3000);
    };
  };



  const fetchSettings = async () => {
    try {
      setLoading(true);
      // Try fetching settings, but staffs will get 403. Catch it.
      let fetchedSettings = {};
      try {
        const res = await axios.get(`${API_URL}/settings`);
        fetchedSettings = res.data;
      } catch (err) {
        if (err.response && err.response.status === 403 && localStorage.getItem('sys_role') === 'staff') {
           console.log("Staff role bypasses settings fetch.");
        } else {
           throw err; // Re-throw if it's not an expected staff restriction
        }
      }
      setSettings(fetchedSettings);
      
      // Try fetching delivery areas (staffs will also get 403)
      try {
        const deliveryRes = await axios.get(`${API_URL}/delivery_areas`);
        setDeliveryAreaText(deliveryRes.data.content || '');
      } catch (err) {
        if (err.response && err.response.status === 403 && localStorage.getItem('sys_role') === 'staff') {
           // Ignore
        } else {
           throw err;
        }
      }
      
      // Fetch dashboard stats (Historical data)
      fetchStats();
      
    } catch (error) {
      console.error('Failed to fetch settings/stats:', error);
      setSaveStatus(t('fetchFailed'));
      // Fallback object to ensure dashboard can still render for staff even if fetch crashes unexpectedly
      setSettings({});
    } finally {
      setLoading(false);
    }
  };

  const fetchStats = async () => {
    try {
        const statsRes = await axios.get(`${API_URL}/stats`);
        setDashboardStats(statsRes.data);
    } catch (e) {
        console.error('Failed to fetch stats:', e);
    }
  };

  // liveOrder persists until next call starts (cleared in call_start handler below)

  const handleSaveDeliveryArea = async () => {
    try {
      setDeliveryAreaSaveStatus(t('saving'));
      await axios.post(`${API_URL}/delivery_areas`, { content: deliveryAreaText });
      setDeliveryAreaSaveStatus(t('saved'));
      setTimeout(() => setDeliveryAreaSaveStatus(''), 3000);
    } catch (error) {
      console.error('Failed to save delivery areas:', error);
      setDeliveryAreaSaveStatus(t('saveFailed'));
    }
  };

  const handleSaveSettings = async () => {
    try {
      setSaveStatus(t('saving'));
      await axios.post(`${API_URL}/settings`, { settings });
      setSaveStatus(t('saved'));
      setTimeout(() => setSaveStatus(''), 3000);

      // 保存成功后，将当前模型名称加入历史记录（去重，最多保留 10 条）
      const currentModel = settings?.ai_settings?.model_name;
      if (currentModel) {
        setModelHistory(prev => {
          const updated = [currentModel, ...prev.filter(m => m !== currentModel)].slice(0, 10);
          localStorage.setItem('gemini_model_history', JSON.stringify(updated));
          return updated;
        });
      }
    } catch (error) {
      console.error('Failed to save settings:', error);
      setSaveStatus(t('saveFailed'));
    }
  };

  const handleChangePassword = async () => {
    if (newPassword !== confirmPassword) {
      setPwdStatus('Mismatch');
      return;
    }
    if (!newPassword || newPassword.length < 4) {
      setPwdStatus('Invalid');
      return;
    }
    try {
      setPwdStatus(t('saving'));
      await axios.post(`${API_URL}/change-password`, { new_password: newPassword });
      setPwdStatus('Success. Relogging...');
      setNewPassword('');
      setConfirmPassword('');
      setTimeout(() => {
         setPwdStatus('');
         handleLogout();
      }, 1500);
    } catch (error) {
       console.error('Failed to change password:', error);
       setPwdStatus(t('saveFailed'));
    }
  };

  const handleOpenOrdersModal = async () => {
    try {
      // Dashboard modal shows TODAY's orders only (not all history)
      const res = await axios.get(`${API_URL}/orders`);
      setAllOrdersList(res.data.orders);
      setShowOrdersModal(true);
      setSelectedOrder(null); // Reset detail view
    } catch (e) {
      console.error('Failed to fetch orders:', e);
    }
  };

  const fetchAllOrdersForHistory = async () => {
    try {
      const res = await axios.get(`${API_URL}/orders?all=true`);
      setAllOrdersList(res.data.orders);
    } catch (e) {
      console.error('Failed to fetch all orders for history:', e);
    }
  };

  const fetchAllCustomers = async () => {
    try {
      const res = await axios.get(`${API_URL}/customers`);
      setCustomersList(res.data.customers);
    } catch (e) {
      console.error('Failed to fetch customers:', e);
    }
  };

  // Fetch when tab switches to history
  useEffect(() => {
    if (activeTab === 'history' || activeTab === 'analytics') {
      fetchAllOrdersForHistory();
    } else if (activeTab === 'customers') {
      fetchAllCustomers();
    }
  }, [activeTab]);

  const handleDeleteOrder = (orderId, e) => {
    e.stopPropagation(); // 阻止事件冒泡导致打开订单详情
    setOrderToDelete(orderId);
  };

  const confirmDeleteOrder = async () => {
    if (!orderToDelete) return;
    try {
      await axios.delete(`${API_URL}/orders/${orderToDelete}`);
      // 重新获取列表
      const res = await axios.get(`${API_URL}/orders?all=true`);
      setAllOrdersList(res.data.orders);
      
      // Update today's list for dashboard counts silently
      try {
        const todayRes = await axios.get(`${API_URL}/orders`);
        setOrdersList(todayRes.data.orders);
      } catch (err){}
      
      if (selectedOrder && selectedOrder.id === orderToDelete) {
        setSelectedOrder(null);
      }
      setOrderToDelete(null);
    } catch (err) {
      console.error('Failed to delete order:', err);
      alert('删除失败，请重试');
    }
  };

  const handleClearLogs = async () => {
    try {
      await axios.delete(`${API_URL}/logs`);
      setSaveStatus(lang === 'zh' ? '后台日志已清空' : 'Logs Cleared');
      setTimeout(() => setSaveStatus(''), 3000);
    } catch (err) {
      console.error('Failed to clear logs:', err);
      setSaveStatus(lang === 'zh' ? '清空日志失败' : 'Clear Logs Failed');
      setTimeout(() => setSaveStatus(''), 3000);
    }
  };

  // 呼入日志（替代原 waitQueue）
  const [callLog, setCallLog] = useState([]);

  const updateSetting = (category, key, value) => {
    setSettings(prev => ({
      ...prev,
      [category]: {
        ...(prev[category] || {}),
        [key]: value
      }
    }));
  };

  // 如果未登录，阻断渲染，显示登录界面
  if (!sysToken) {
    return <LoginScreen setSysToken={setSysToken} setSysRole={setSysRole} t={t} lang={lang} setLang={setLang} />;
  }

  // 如果仍加载或缺失数据
  if (loading || !settings) {
    return (
      <div className="flex items-center justify-center h-screen bg-slate-950 text-white">
        <div className="animate-spin mr-3"><RefreshCw size={24}/></div>
        {t('init')}
      </div>
    );
  }
  
  // 安全保障：如果在检查之后 settings 依然为空，抛出兜底
  if (!settings) return null;

  const aiSettings = settings.ai_settings || {};
  const routing = settings.phone_routing || {};
  const keys = settings.api_keys || {};
  const pricing = settings.pricing_rules || {};



  return (
    <div className="flex h-screen bg-slate-950 text-slate-200 font-sans">
      
      {/* Sidebar Navigation */}
      <aside className="w-64 bg-slate-900 border-r border-slate-800 flex flex-col">
        <div className="p-6">
          <img src="/logo.png" alt="Noodle Box Logo" className="w-auto h-12 object-contain" />
          <h1 className="text-xl font-bold font-mono text-cyan-400 flex items-center gap-2">
            {t('brandName')}
          </h1>
          <p className="text-xs text-slate-500 mt-1 uppercase tracking-wider">{t('controlPanel')}</p>
        </div>
        
        <nav className="flex-1 px-4 space-y-2">
          <NavItem icon={<Activity />} label={t('dashboard')} active={activeTab === 'dashboard'} onClick={() => navigateTo('dashboard')} />
          <NavItem icon={<ListOrdered />} label={t('history')} active={activeTab === 'history'} onClick={() => navigateTo('history')} />
          <NavItem icon={<Users />} label={t('customers')} active={activeTab === 'customers'} onClick={() => navigateTo('customers')} />
          <NavItem icon={<BarChart2 />} label={t('analytics')} active={activeTab === 'analytics'} onClick={() => navigateTo('analytics')} />
          <NavItem icon={<Bot />} label={t('ai')} active={activeTab === 'ai'} onClick={() => navigateTo('ai')} locked={sysRole === 'staff'} />
          <NavItem icon={<BookOpen />} label={t('menu')} active={activeTab === 'menu'} onClick={() => navigateTo('menu')} locked={sysRole === 'staff'} />

          <NavItem icon={<Settings />} label={t('config')} active={activeTab === 'config'} onClick={() => navigateTo('config')} locked={sysRole === 'staff'} />
        </nav>
        
        <div className="p-4 border-t border-slate-800 space-y-2">
          <div className={`flex items-center justify-center gap-2 text-sm p-3 rounded-lg border ${
            aiSettings.master_switch === 'active' ? 'bg-green-950/30 border-green-800 text-green-400' : 
            aiSettings.master_switch === 'bypass' ? 'bg-yellow-950/30 border-yellow-800 text-yellow-400' : 
            'bg-red-950/30 border-red-800 text-red-500'
          }`}>
            <Power size={18} />
            <span className="font-semibold capitalize">{t('status')}: {t(aiSettings.master_switch || 'offline')}</span>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 flex flex-col h-screen overflow-hidden">
        
        {/* Header bar */}
        <header className="h-16 border-b border-slate-800 bg-slate-900/50 flex items-center justify-between px-8">
          <h2 className="text-lg font-medium text-white capitalize">{t(activeTab) || activeTab}</h2>
          <div className="flex items-center gap-4">
            
            <button 
              onClick={handleLogout}
              className="flex items-center gap-2 px-3 py-1.5 rounded-md text-sm transition-colors border border-slate-700 hover:bg-red-900/30 text-slate-300 hover:text-red-400 mr-2 bg-slate-800"
              title={t('logout')}
            >
              <LogOut size={16} />
              <span className="hidden sm:inline font-medium">{t('logout')} ({sysRole === 'admin' ? t('adminAccess') : t('staffAccess')})</span>
            </button>

            <button 
              onClick={() => setLang(lang === 'zh' ? 'en' : 'zh')}
              className="flex items-center gap-2 px-3 py-1.5 rounded-md text-sm transition-colors border border-slate-700 hover:bg-slate-800 text-slate-300 mr-2"
            >
              <Globe size={16} />
              {lang === 'zh' ? 'English' : '中文'}
            </button>

            {saveStatus && (
              <span className={`text-sm flex items-center gap-1 ${saveStatus === t('saved') ? 'text-green-400' : 'text-slate-400'}`}>
                {saveStatus === t('saved') ? <CheckCircle2 size={16}/> : ''} {saveStatus}
              </span>
            )}
            <button 
              onClick={handleSaveSettings}
              className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2 rounded-md text-sm transition-colors shadow-lg shadow-indigo-900/20"
            >
              <Save size={16} /> {t('deploy')}
            </button>
          </div>
        </header>

        {/* Dynamic Content Scroll Area */}
        <div className="flex-1 overflow-y-auto p-8 bg-gradient-to-br from-slate-950 to-slate-900">
          <div className="h-full">

            {/* ---- TAB: CUSTOMERS ---- */}
            {activeTab === 'customers' && (
              <div className="max-w-5xl mx-auto h-full flex flex-col bg-slate-900 border border-slate-700 rounded-xl overflow-hidden shadow-2xl">
                <div className="px-6 py-4 border-b border-slate-800 flex justify-between items-center bg-slate-800/50 shrink-0">
                  <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                    <Users className="text-indigo-400" />
                    {t('customers')}
                  </h2>
                </div>
                
                <div className="flex-1 overflow-y-auto p-6 scrollbar-thin scrollbar-thumb-slate-700">
                  {customersList.length === 0 ? (
                    <div className="text-center text-slate-500 py-20 flex flex-col items-center">
                      <Users size={48} className="mb-4 opacity-50" />
                      <p>暂无客户数据 (No Customer Data)</p>
                    </div>
                  ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {customersList.map(c => (
                        <div key={c.id} className="bg-slate-800/40 border border-slate-700 rounded-xl p-4 hover:bg-slate-800/80 transition-colors">
                          <div className="flex justify-between items-start mb-3">
                            <div>
                              <div className="text-lg font-bold text-white flex items-center gap-2">
                                {c.name}
                              </div>
                              <div className="text-sm font-mono text-indigo-400 mt-1">{c.phone_number}</div>
                            </div>
                            <div className="bg-slate-900 px-2 py-1 rounded text-xs text-slate-500 border border-slate-800">
                              ID: {c.id}
                            </div>
                          </div>
                          
                          <div className="space-y-2 text-sm">
                            <div className="flex gap-2 text-slate-400">
                              <MapPin size={16} className="shrink-0 mt-0.5 text-slate-500" />
                              <span className="truncate" title={c.address}>{c.address !== 'Unknown' ? c.address : '暂无地址记录'}</span>
                            </div>
                            <div className="flex items-center gap-2 text-slate-400">
                              <ListOrdered size={16} className="shrink-0 text-slate-500" />
                              <span className="truncate" title={c.last_order_id}>最后订单: {c.last_order_id !== 'None' ? c.last_order_id : '无'}</span>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* ---- TAB: ANALYTICS ---- */}
            {activeTab === 'analytics' && (() => {
              const totalCalls = allOrdersList.length;
              const completed = allOrdersList.filter(o => !o.source.includes("Incomplete")).length;
              // We define "dropped" as incomplete without transfer attempt 
              // For simplicity: assume Incomplete means dropped.
              const incomplete = allOrdersList.filter(o => o.source.includes("Incomplete")).length;
              
              // We check how many transfers occurred by looking at transcripts
              // For a stronger logic, backend should perhaps explicitly flag transfers
              // But here we can guess based on transcript 'transfer_call' tool usage
              let transferredCount = 0;
              allOrdersList.forEach(o => {
                try {
                  const transcriptStr = typeof o.transcript === "string" ? o.transcript : JSON.stringify(o.transcript || []);
                  if (transcriptStr && transcriptStr.includes("transfer_call")) {
                    transferredCount++;
                  }
                } catch(e){}
              });

              // Adjust dropped if we know it was transferred
              const dropped = Math.max(0, incomplete - transferredCount);
              
              const pieData = [
                { name: 'Completed', value: completed, color: '#4ade80' },
                { name: 'Dropped', value: dropped, color: '#f87171' },
                { name: 'Transferred', value: transferredCount, color: '#60a5fa' }
              ];

              return (
                <div className="max-w-5xl mx-auto h-full flex flex-col bg-slate-900 border border-slate-700 rounded-xl overflow-hidden shadow-2xl">
                  <div className="px-6 py-4 border-b border-slate-800 bg-slate-800/50 shrink-0">
                    <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                      <BarChart2 className="text-indigo-400" />
                      {t('analytics')}
                    </h2>
                  </div>
                  
                  <div className="flex-1 overflow-y-auto p-6 scrollbar-thin scrollbar-thumb-slate-700 space-y-6">
                    {/* Top Stats Cards */}
                    <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                      <div className="bg-slate-800/40 border border-slate-700 rounded-xl p-5 flex flex-col items-center justify-center">
                        <span className="text-slate-400 text-sm mb-1">Total AI Calls</span>
                        <span className="text-3xl font-bold text-white">{totalCalls}</span>
                      </div>
                      <div className="bg-green-900/20 border border-green-900/50 rounded-xl p-5 flex flex-col items-center justify-center">
                        <span className="text-green-500 text-sm mb-1">Completed</span>
                        <span className="text-3xl font-bold text-green-400">{completed}</span>
                      </div>
                      <div className="bg-slate-800/40 border border-slate-700 rounded-xl p-5 flex flex-col items-center justify-center">
                        <span className="text-slate-400 text-sm mb-1">Incomplete / Dropped</span>
                        <span className="text-3xl font-bold text-red-400">{dropped}</span>
                      </div>
                      <div className="bg-blue-900/20 border border-blue-900/50 rounded-xl p-5 flex flex-col items-center justify-center">
                        <span className="text-blue-500 text-sm mb-1">Human Transfers</span>
                        <span className="text-3xl font-bold text-blue-400">{transferredCount}</span>
                      </div>
                    </div>

                    {/* Chart Container */}
                    {totalCalls > 0 ? (
                      <div className="bg-slate-800/40 border border-slate-700 rounded-xl p-6 h-80 flex flex-col">
                        <h3 className="text-slate-300 font-medium mb-4">Call Outcome Distribution</h3>
                        <div className="flex-1">
                          <ResponsiveContainer width="100%" height="100%">
                            <PieChart>
                              <Pie
                                data={pieData.filter(d => d.value > 0)}
                                cx="50%"
                                cy="50%"
                                labelLine={false}
                                outerRadius={100}
                                fill="#8884d8"
                                dataKey="value"
                                label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                              >
                                {pieData.map((entry, index) => (
                                  <Cell key={`cell-${index}`} fill={entry.color} />
                                ))}
                              </Pie>
                              <RechartsTooltip 
                                contentStyle={{ backgroundColor: '#1e293b', borderColor: '#334155', color: '#f8fafc' }}
                                itemStyle={{ color: '#f8fafc' }}
                              />
                            </PieChart>
                          </ResponsiveContainer>
                        </div>
                      </div>
                    ) : (
                      <div className="text-center text-slate-500 py-10">No call data available for analysis.</div>
                    )}
                  </div>
                </div>
              );
            })()}

            {/* ---- TAB: HISTORY ORDERS ---- */}
            {activeTab === 'history' && (
              <div className="max-w-5xl mx-auto h-full flex flex-col bg-slate-900 border border-slate-700 rounded-xl overflow-hidden shadow-2xl">
                <div className="px-6 py-4 border-b border-slate-800 flex justify-between items-center bg-slate-800/50 shrink-0">
                  <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                    {selectedOrder ? (
                      <>
                        <button onClick={() => setSelectedOrder(null)} className="text-slate-400 hover:text-white px-2 py-1 rounded bg-slate-800">
                          ← {t('backToList')}
                        </button>
                        <span>{t('orderDetailsTitle')} {selectedOrder.id}</span>
                      </>
                    ) : t('allHistoryTitle')}
                  </h2>
                </div>
                <OrdersView 
                  orders={allOrdersList} 
                  selectedOrder={selectedOrder} 
                  setSelectedOrder={setSelectedOrder} 
                  onDeleteOrder={handleDeleteOrder} 
                  t={t} 
                />
              </div>
            )}

            {/* ---- TAB: DASHBOARD ---- */}
            {activeTab === 'dashboard' && (
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 h-full pb-4">
                 {/* Left Column: Stats & Operations (Span 3 now - smaller and more left) */}
                 <div className="lg:col-span-3 space-y-3 flex flex-col overflow-y-auto right-pane-scrollbar">
                    {/* 呼入日志卡片区 */}
                    {(() => {
                      const activeCalls   = callLog.filter(r => r.status === 'active');
                      const activeCount   = activeCalls.length;
                      const maxCalls      = aiSettings?.max_concurrent_calls ?? 3;
                      const recentLog     = [...callLog].reverse().slice(0, 20);

                      const SRC_ICON      = { twilio: '📱', webrtc: '🖥️' };
                      const STATUS_CFG    = {
                        active:    { label: t('callActive'),    cls: 'text-emerald-400 bg-emerald-500/10 border-emerald-700/40' },
                        completed: { label: t('callCompleted'), cls: 'text-slate-400  bg-slate-700/20   border-slate-700/30'  },
                        missed:    { label: t('callMissed'),    cls: 'text-red-400   bg-red-500/10     border-red-700/40'    },
                      };

                      return (
                        <div className="border rounded-xl p-3 flex flex-col bg-slate-900 border-slate-800">
                          {/* Header: title + concurrent progress bar */}
                          <div className="flex items-center justify-between mb-2">
                            <h3 className="text-sm font-medium text-slate-400 flex items-center gap-1.5">
                              <PhoneIncoming size={14} className="text-green-400" />
                              {t('waitQueueTitle')}
                            </h3>
                            <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${
                              activeCount >= maxCalls
                                ? 'bg-red-500/20 text-red-300 border border-red-700/40'
                                : 'bg-emerald-500/10 text-emerald-400 border border-emerald-700/30'
                            }`}>
                              {activeCount} / {maxCalls} {t('linesSuffix')}
                            </span>
                          </div>
                          {/* Capacity bar */}
                          <div className="w-full h-1 bg-slate-800 rounded-full mb-3">
                            <div
                              className={`h-full rounded-full transition-all ${
                                activeCount >= maxCalls ? 'bg-red-500' : 'bg-emerald-500'
                              }`}
                              style={{ width: `${Math.min((activeCount / maxCalls) * 100, 100)}%` }}
                            />
                          </div>
                          {/* Call cards */}
                          <div className="overflow-y-auto max-h-[260px] pr-1 space-y-1.5">
                            {recentLog.length > 0 ? [...recentLog].reverse().slice(0, 10).map((log, idx) => {
                              const cfg      = STATUS_CFG[log.status] || STATUS_CFG.missed;
                              const srcIcon  = SRC_ICON[log.source] || '📞';
                              const callTime = new Date(log.joined_at * 1000).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});
                              const duration = log.ended_at
                                ? Math.round(log.ended_at - log.joined_at) + 's'
                                : '–';
                              return (
                                <div key={idx} className={`flex flex-col gap-0.5 p-2 rounded-lg border bg-slate-950 border-slate-800 text-[11px] ${
                                  log.status === 'active' ? 'ring-1 ring-emerald-500/30' : 'opacity-80'
                                }`}>
                                  {/* Line 1: icon + number + time */}
                                  <div className="flex items-center gap-1.5 min-w-0">
                                    <span title={log.source === 'webrtc' ? t('tooltipWebrtc') : t('tooltipTwilio')}>{srcIcon}</span>
                                    <span className="font-mono text-slate-200 flex-1 truncate">{log.number}</span>
                                    <span className="text-slate-500 shrink-0">{callTime}</span>
                                    {log.ended_at && <span className="text-slate-600 shrink-0">{duration}</span>}
                                  </div>
                                  {/* Line 2: status + order outcome + transfer */}
                                  <div className="flex items-center gap-1.5 pl-5">
                                    <span className={`px-1.5 py-0.5 rounded border text-[10px] font-medium whitespace-nowrap ${cfg.cls}`}>{cfg.label}</span>
                                    {log.status === 'completed' && (
                                      <span title={log.order_finalized === true ? t('tooltipOrderDone') : log.order_finalized === false ? t('tooltipOrderMissed') : t('tooltipNoOrder')}>
                                        {log.order_finalized === true ? '✅' : log.order_finalized === false ? '⚠️' : '—'}
                                      </span>
                                    )}
                                    {log.transferred && <span title={t('tooltipTransferred')}>🔀</span>}
                                  </div>
                                </div>
                              );
                            }) : (
                              <div className="flex flex-col items-center justify-center text-slate-600 space-y-2 py-6">
                                <Coffee size={18} className="opacity-40" />
                                <span className="text-xs">{t('noCallLog')}</span>
                              </div>
                            )}
                            {recentLog.length > 10 && (
                              <p className="text-center text-[10px] text-slate-600 pt-1">{t('callLogMoreFmt').replace('{n}', recentLog.length)}</p>
                            )}
                          </div>
                        </div>
                      );
                    })()}


                    <DashboardCard 
                      title={t('aiCallsActive')} 
                      value={activeCallCount} 
                      subtitle={t('liveWs')}
                      icon={<PhoneCall className="text-cyan-400" size={18} />} 
                    />
                    <DashboardCard 
                      title={t('ordersProcessed')} 
                      value={totalOrders} 
                      subtitle={t('todayViaAI')}
                      icon={<CheckCircle2 className="text-green-400" size={18} />}
                      incomplete={incompleteOrders}
                      onClick={() => handleOpenOrdersModal()}
                    />
                    <DashboardCard 
                      title={t('lastSync')} 
                      value="2 mins ago" 
                      subtitle={t('nextSync')}
                      icon={<RefreshCw className="text-purple-400" size={18} />} 
                    />
                    
                    <div className="bg-slate-900 border border-slate-800 rounded-xl p-3 mb-3">
                      <h3 className="text-sm font-medium mb-2 flex items-center gap-1.5"><Webhook className="text-indigo-400" size={14}/> {t('omniSync')}</h3>
                      <div className="p-2 bg-slate-950 rounded-lg text-[11px] font-mono text-slate-400 leading-tight">
                        {t('syncMsg1')}<br/>
                        {t('syncMsg2')}<br/>
                        {t('syncMsg3')}
                      </div>
                    </div>

                    {sysRole === 'admin' ? (
                      <WebCallSimulator t={t} aiBusy={aiBusy} />
                    ) : (
                      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 text-center shadow-lg flex flex-col justify-center min-h-[220px]">
                        <div className="w-10 h-10 bg-red-950/50 rounded-full flex items-center justify-center mx-auto mb-3 border border-red-900/50">
                          <Lock size={18} className="text-red-500" />
                        </div>
                        <h3 className="text-slate-300 font-medium mb-2">{t('webSimTitle')}</h3>
                        <p className="text-slate-500 text-xs">{t('adminDesc')}</p>
                      </div>
                    )}
                 </div>
                 
                 {/* Right Column: Charts & Live Transcript (Span 9 now) */}
                 <div className="lg:col-span-9 flex flex-col xl:flex-row gap-6 h-full min-h-0">

                   {/* ---- LIVE TRANSCRIPT ROW (Left Side) ---- */}
                   <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden flex flex-col flex-1 min-w-0 min-h-[500px]">
                     <div className="px-6 py-4 border-b border-slate-800 bg-slate-900/50 flex justify-between items-center shrink-0">
                       <h3 className="text-lg font-medium text-white flex items-center gap-2">
                         <Terminal size={18} className="text-emerald-400" />
                         {lang === 'zh' ? '实时对话记录终端' : 'Live Transcript Terminal'}
                       </h3>
                      {activeCallCount > 0 && <span className="flex h-3 w-3 relative">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                        <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500"></span>
                      </span>}
                    </div>

                    {/* [NEW] Call Bookmarks / Tabs Area */}
                    {Object.keys(activeCallsList).length > 0 && (
                      <div className="px-4 py-2 border-b border-slate-800 bg-slate-950/40 flex gap-2 overflow-x-auto right-pane-scrollbar shrink-0">
                        {Object.entries(activeCallsList).map(([sid, call]) => {
                           const isActive = sid === activeViewCallSid;
                           return (
                             <button
                               key={sid}
                               onClick={() => setActiveViewCallSid(sid)}
                               className={`flex flex-col items-start px-3 py-1.5 rounded-t-md border-b-2 transition-colors whitespace-nowrap ${
                                 isActive 
                                   ? 'bg-slate-800 text-white border-emerald-400' 
                                   : 'bg-slate-900/50 text-slate-400 hover:bg-slate-800 hover:text-slate-200 border-transparent'
                               }`}
                             >
                               <span className="text-xs font-medium flex items-center gap-1.5">
                                  <PhoneCall size={12} className={isActive ? 'text-emerald-400' : 'text-slate-500'}/>
                                  {call.caller_name || 'Unknown Caller'}
                               </span>
                               <span className="text-[10px] font-mono opacity-60 ml-4">{call.caller_number}</span>
                             </button>
                           );
                        })}
                      </div>
                    )}

                    <div className="flex-1 overflow-y-auto p-4 space-y-3 font-mono text-sm" id="transcript-container">
                      {(() => {
                        // 只显示当前察看话路的记录，完全隔离并发干扰
                        const visibleEntries = [
                          ...(transcripts[activeViewCallSid] || []),
                          ...(transcripts['__system__'] || []),
                        ];
                        if (visibleEntries.length === 0) {
                          return <div className="text-slate-600 italic mt-4 text-center">
                            {lang === 'zh' ? '等待接入系统通话...' : 'Waiting for call...'}
                          </div>;
                        }
                        return visibleEntries.map((msg) => (
                          <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : msg.role === 'ai' ? 'justify-start' : 'justify-center'} w-full`}>
                            {msg.role === 'system' ? (
                              <div className="text-slate-500 text-xs my-2 bg-slate-950 px-3 py-1 rounded-full border border-slate-800">
                                {msg.text}
                              </div>
                            ) : msg.role === 'system_log' ? (
                              <div className={`text-xs my-1 px-3 py-1.5 rounded border ${msg.type === 'error' ? 'bg-red-950/30 text-red-400 border-red-900/50' : msg.type === 'success' ? 'bg-emerald-950/20 text-emerald-400 border-emerald-900/50' : 'bg-slate-800/30 text-slate-400 border-slate-700/50'} w-full font-mono whitespace-pre-wrap`}>
                                {'>'} {msg.text}
                              </div>
                            ) : msg.role === 'tool' || msg.role === 'tool_response' ? (
                              <div className="text-[11px] my-1 px-3 py-2 rounded-md border bg-slate-950 border-slate-800 text-indigo-300 w-full font-mono whitespace-pre-wrap mt-2 mb-2">
                                <div className="flex items-center">
                                  {msg.role === 'tool' ? <Code size={12} className="inline mr-1 text-indigo-400"/> : <CheckCircle2 size={12} className="inline mr-1 text-emerald-400"/>} 
                                  {msg.text}
                                  {msg.is_animating && <span className="animate-pulse ml-1 tracking-widest text-indigo-200">...</span>}
                                </div>
                                {msg.args && (
                                  <div className="mt-2 p-2 bg-slate-900 border border-slate-700/50 rounded overflow-x-auto text-[10px] text-slate-400">
                                    <pre>{JSON.stringify(msg.args, null, 2)}</pre>
                                  </div>
                                )}
                              </div>
                            ) : msg.role === 'thought' ? (
                              <div className="text-[11px] my-1 px-3 py-2 rounded-md border bg-slate-800/40 border-slate-700/50 text-slate-400 italic w-full font-mono whitespace-pre-wrap">
                                {msg.text}
                              </div>
                            ) : (
                              <div className={`max-w-[70%] rounded-lg px-4 py-2 ${
                                msg.role === 'user' 
                                  ? 'bg-indigo-600/20 text-indigo-100 border border-indigo-500/30' 
                                  : 'bg-emerald-900/20 text-emerald-100 border border-emerald-500/30'
                              }`}>
                                <div className="text-xs mb-1 opacity-50 flex items-center gap-1">
                                  {msg.role === 'user' ? <User size={10}/> : <Bot size={10}/>} {msg.role === 'user' ? (lang==='zh' ? '客户' : 'Caller') : 'AI'}
                                </div>
                                <TypewriterText text={msg.text} isStreaming={!msg.is_final} />
                              </div>
                            )}
                          </div>
                        ));
                      })()}
                       <AutoScrollTrigger transcripts={transcripts[activeViewCallSid] || []} />
                     </div>
                   </div>

                   {/* ---- STATS CHARTS ROW (Right Side, Vertical Stack) OR LIVE RECEIPT ---- */}
                   <div className="flex flex-col gap-6 w-full xl:w-[32%] shrink-0 h-full overflow-y-auto right-pane-scrollbar min-h-0 pb-1">
                       <LiveReceipt liveOrder={liveOrder} activeCallCount={activeCallCount} lang={lang} />
                   </div>
                 </div>
              </div>
            )}

            {/* ---- TAB: AI BRAIN ---- */}
            {activeTab === 'ai' && (
              sysRole !== 'admin' ? <LockedView t={t} /> :
              <div className="max-w-5xl mx-auto space-y-6">
                <Card title={t('masterSwitch')}>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
                    <RadioOption 
                      label={t('activeLabel')} 
                      description={t('activeDesc')}
                      value="active" 
                      current={aiSettings.master_switch}
                      onChange={(v) => updateSetting('ai_settings', 'master_switch', v)}
                      color="green"
                    />
                    <RadioOption 
                      label={t('bypassLabel')} 
                      description={t('bypassDesc')}
                      value="bypass" 
                      current={aiSettings.master_switch}
                      onChange={(v) => updateSetting('ai_settings', 'master_switch', v)}
                      color="yellow"
                    />
                    <RadioOption 
                      label={t('offlineLabel')} 
                      description={t('offlineDesc')}
                      value="offline" 
                      current={aiSettings.master_switch}
                      onChange={(v) => updateSetting('ai_settings', 'master_switch', v)}
                      color="red"
                    />
                  </div>

                  <div className="space-y-4 pt-4 border-t border-slate-800">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                      <InputGroup label={t('bypassMessage')} helpText={t('bypassHelp')}>
                        <textarea 
                          className="w-full p-3 bg-slate-950 border border-slate-700 rounded-lg text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 min-h-[80px] resize-y block" 
                          value={aiSettings.bypass_message || ''} 
                          onChange={(e) => updateSetting('ai_settings', 'bypass_message', e.target.value)} 
                          placeholder="e.g. Please hold on while I transfer you to our staff."
                        />
                      </InputGroup>
                      <InputGroup label={t('offlineMessage')} helpText={t('offlineHelp')}>
                        <textarea 
                          className="w-full p-3 bg-slate-950 border border-slate-700 rounded-lg text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 min-h-[80px] resize-y block" 
                          value={aiSettings.offline_message || ''} 
                          onChange={(e) => updateSetting('ai_settings', 'offline_message', e.target.value)} 
                          placeholder="e.g. Sorry, we are currently closed. Please call back during our normal business hours."
                        />
                      </InputGroup>
                    </div>
                    <div className="flex justify-end mt-2">
                       <button 
                         onClick={handleSaveSettings}
                         className="flex items-center gap-2 bg-indigo-900/40 hover:bg-indigo-800 border border-indigo-700/50 text-indigo-300 px-3 py-1.5 rounded text-xs transition-colors"
                       >
                         <Save size={12} /> {t('deploy')}
                       </button>
                    </div>
                  </div>

                  {/* 并发通话上限配置 */}
                  <div className="space-y-4 pt-4 border-t border-slate-800">
                    <h3 className="text-sm font-semibold text-slate-300 flex items-center gap-2">
                      <PhoneIncoming size={15} className="text-green-400" />
                      📞 {t('concurrentCallsTitle')}
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                      <InputGroup label={t('maxCalls')} helpText={t('maxCallsHelp')}>
                        <input
                          className="input-field"
                          type="number" min="1" max="10"
                          value={aiSettings.max_concurrent_calls ?? 3}
                          onChange={(e) => updateSetting('ai_settings', 'max_concurrent_calls', parseInt(e.target.value, 10))}
                        />
                      </InputGroup>
                    </div>
                    <InputGroup
                      label={t('busyMessageLabel')}
                      helpText={t('busyMessageHelp')}
                    >
                      <textarea
                        className="w-full p-3 bg-slate-950 border border-slate-700 rounded-lg text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 min-h-[60px] resize-y block"
                        value={aiSettings.busy_message || ''}
                        onChange={(e) => updateSetting('ai_settings', 'busy_message', e.target.value)}
                        placeholder={t('busyMessagePlaceholder')}
                      />
                    </InputGroup>
                  </div>
                </Card>


                <Card title={t('modelSpecs')}>
                   <div className="space-y-4">
                    <InputGroup label={t('geminiModel')}>
                       {/* datalist 提供浏览器原生下拉历史建议 */}
                       <input
                         className="input-field"
                         list="model-history-list"
                         value={aiSettings.model_name || ''}
                         onChange={(e) => updateSetting('ai_settings', 'model_name', e.target.value)}
                         placeholder="输入模型名称或从历史记录中选择..."
                       />
                       <datalist id="model-history-list">
                         {modelHistory.map((m, i) => (
                           <option key={i} value={m} />
                         ))}
                       </datalist>
                    </InputGroup>
                    <InputGroup label={t('voicePersonality')}>
                       <select className="input-field" value={aiSettings.voice_name || ''} onChange={(e) => updateSetting('ai_settings', 'voice_name', e.target.value)}>
                         <option value="Aoede">Aoede</option>
                         <option value="Kore">Kore</option>
                         <option value="Charon">Charon</option>
                         <option value="Puck">Puck</option>
                         <option value="Fenrir">Fenrir</option>
                       </select>
                    </InputGroup>
                   </div>
                </Card>
              </div>
            )}

            {/* ---- TAB: MENU & LOGIC ---- */}
            {activeTab === 'menu' && (
              sysRole !== 'admin' ? <LockedView t={t} /> :
              <div className="space-y-6">
                {/* Menu Database — full width, placed at the TOP */}
                <div>
                  <MenuGUI />
                </div>

                <Card title={t('pricingRules')}>
                  <div className="grid grid-cols-2 gap-6">
                    <InputGroup label={t('minDel')}>
                      <div className="relative">
                        <Euro className="absolute left-3 top-2.5 text-slate-500" size={16} />
                        <input className="input-field pl-9" type="number" step="0.5" value={pricing.minimum_delivery_order || 0} onChange={(e) => updateSetting('pricing_rules', 'minimum_delivery_order', parseFloat(e.target.value))} />
                      </div>
                    </InputGroup>
                    <InputGroup label={t('cardFee')}>
                      <div className="relative">
                        <Euro className="absolute left-3 top-2.5 text-slate-500" size={16} />
                        <input className="input-field pl-9" type="number" step="0.1" value={pricing.card_payment_surcharge || 0} onChange={(e) => updateSetting('pricing_rules', 'card_payment_surcharge', parseFloat(e.target.value))} />
                      </div>
                    </InputGroup>
                  </div>
                </Card>

                <Card title={t('globalDiscount')}>
                  <div className="mb-4">
                    <label className="flex items-center gap-2 cursor-pointer text-sm font-medium text-slate-300">
                      <input 
                        type="checkbox" 
                        checked={pricing.discount_active || false} 
                        onChange={(e) => updateSetting('pricing_rules', 'discount_active', e.target.checked)} 
                        className="rounded bg-slate-800 border-slate-700 text-indigo-500 focus:ring-offset-slate-900" 
                      />
                      {t('enableDiscount')}
                    </label>
                  </div>
                  
                  {pricing.discount_active && (
                    <div className="grid grid-cols-2 gap-6 bg-indigo-950/20 p-4 border border-indigo-900/50 rounded-lg">
                      <InputGroup label={t('discountType')}>
                        <select className="input-field" value={pricing.discount_type || 'percentage'} onChange={(e) => updateSetting('pricing_rules', 'discount_type', e.target.value)}>
                          <option value="percentage">{t('pctOff')}</option>
                          <option value="fixed">{t('fixedOff')}</option>
                        </select>
                      </InputGroup>
                      <InputGroup label={t('discountValue')}>
                        <input className="input-field" type="number" step="0.01" value={pricing.discount_value || 0} onChange={(e) => updateSetting('pricing_rules', 'discount_value', parseFloat(e.target.value))} />
                        <p className="text-xs text-slate-500 mt-1">{t('discountHelp')}</p>
                      </InputGroup>
                      <div className="col-span-2">
                        <InputGroup label={t('promoPitch')} helpText={t('promoHelp')}>
                          <input className="input-field" placeholder="e.g. We have a 10% off promotion running today for all orders!" value={pricing.discount_description || ''} onChange={(e) => updateSetting('pricing_rules', 'discount_description', e.target.value)} />
                        </InputGroup>
                      </div>
                    </div>
                  )}
                </Card>

                {/* [NEW] Delivery Area Setup */}
                <Card title={t('deliveryAreaTitle')} icon={<MapPin size={20} className="text-emerald-400" />}>
                  <div className="space-y-4">
                    <p className="text-sm text-slate-400" dangerouslySetInnerHTML={{ __html: t('deliveryAreaHint') }} />
                    <textarea
                      className="w-full p-4 bg-slate-950 font-mono text-sm text-slate-300 border border-slate-700 rounded-lg focus:outline-none focus:border-indigo-500 min-h-[250px] resize-y"
                      value={deliveryAreaText}
                      onChange={(e) => setDeliveryAreaText(e.target.value)}
                      placeholder="Drogheda ........ €3\nDonore .......... €5"
                    />
                    <div className="flex justify-end mt-2 items-center gap-4">
                      {deliveryAreaSaveStatus && (
                        <span className={`text-sm flex items-center gap-1 ${deliveryAreaSaveStatus === t('saved') ? 'text-green-400' : 'text-slate-400'}`}>
                          {deliveryAreaSaveStatus === t('saved') ? <CheckCircle2 size={16}/> : ''} {deliveryAreaSaveStatus}
                        </span>
                      )}
                      <button 
                        onClick={handleSaveDeliveryArea}
                        className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 rounded shadow-lg transition-all font-medium text-sm"
                      >
                        <Save size={16} /> {t('saveDeliveryArea')}
                      </button>
                    </div>
                  </div>
                </Card>
                
              </div>
            )}


            {/* ---- TAB: CONFIG ---- */}
            {activeTab === 'config' && (
              sysRole !== 'admin' ? <LockedView t={t} /> :
              <div className="max-w-5xl mx-auto space-y-6">

                <Card title={t('apiKeys')}>
                  <div className="space-y-4">
                     <InputGroup label={t('googleKey')}>
                       <input className="input-field font-mono text-sm" type="password" placeholder="AI Studio Key..." value={keys.google_api_key || ''} onChange={(e) => updateSetting('api_keys', 'google_api_key', e.target.value)} />
                     </InputGroup>
                     <InputGroup label={t('autoAddressKey')}>
                       <input className="input-field font-mono text-sm" type="password" placeholder="Eircode Lookup Key..." value={keys.autoaddress_api_key || ''} onChange={(e) => updateSetting('api_keys', 'autoaddress_api_key', e.target.value)} />
                     </InputGroup>
                  </div>
                </Card>

                <Card title={t('telephony')}>
                  <InputGroup label={t('humanNumber')} helpText={t('humanHelp')}>
                    <input className="input-field font-mono" value={routing.transfer_phone_number || ''} onChange={(e) => updateSetting('phone_routing', 'transfer_phone_number', e.target.value)} />
                  </InputGroup>
                </Card>

                <Card title={t('changePwd')} icon={<Lock size={20} className="text-red-400" />}>
                  <div className="space-y-4 max-w-sm">
                    <InputGroup label={t('newPwd')}>
                      <input className="input-field font-mono text-sm" type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} />
                    </InputGroup>
                    <InputGroup label={t('confirmPwd')}>
                      <input className="input-field font-mono text-sm" type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} />
                    </InputGroup>
                    <div className="flex justify-between items-center mt-4">
                      <span className={`text-sm ${pwdStatus.includes('uccess') || pwdStatus === t('saved') ? 'text-green-400' : 'text-red-400'}`}>{pwdStatus}</span>
                      <button onClick={handleChangePassword} className="bg-red-600 hover:bg-red-500 text-white px-4 py-2 rounded shadow-lg text-sm transition-all">{t('updatePwdBtn')}</button>
                    </div>
                  </div>
                </Card>
              </div>
            )}
            
          </div>
        </div>
      </main>



      {/* Orders Modal */}
      <OrdersModal 
        isOpen={showOrdersModal} 
        onClose={() => setShowOrdersModal(false)}
        orders={allOrdersList}
        selectedOrder={selectedOrder}
        setSelectedOrder={setSelectedOrder}
        onDeleteOrder={handleDeleteOrder}
        t={t}
      />

      {/* Delete Confirmation Modal (Bypass browser native restrictions) */}
      {orderToDelete && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl p-8 w-full max-w-sm">
            <h3 className="text-xl font-bold text-white mb-2 text-center flex justify-center items-center gap-2">
              <Trash2 className="text-red-500" size={24} /> 危险操作
            </h3>
            <p className="text-slate-300 text-sm text-center mb-6">确定要永久删除订单 <span className="text-indigo-400 font-mono break-all">{orderToDelete}</span> 吗？<br/><span className="text-red-400">删除后不可恢复！</span></p>
            <div className="flex gap-3">
              <button
                onClick={() => setOrderToDelete(null)}
                className="flex-1 px-4 py-2 rounded-lg border border-slate-700 text-slate-300 hover:bg-slate-800 text-sm transition-colors"
              >
                取消
              </button>
              <button
                onClick={confirmDeleteOrder}
                className="flex-1 px-4 py-2 rounded-lg bg-red-600 hover:bg-red-500 text-white text-sm font-medium transition-colors shadow-lg shadow-red-900/20"
              >
                确定删除
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ============== Helper Sub-Components ==============

function NavItem({ icon, label, active, onClick, locked }) {
  return (
    <button 
      onClick={onClick}
      className={`w-full flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-all duration-200 ${
        active 
          ? 'bg-indigo-600/20 text-indigo-400 font-medium' 
          : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
      }`}
    >
      <span className={active ? 'text-indigo-400' : 'text-slate-500'}>{React.cloneElement(icon, { size: 18 })}</span>
      <span className="flex-1 text-left">{label}</span>
      {locked && <Lock size={14} className="text-red-500/70" />}
    </button>
  );
}

function DashboardCard({ title, value, subtitle, icon, incomplete, onClick }) {
  return (
    <div 
      className={`bg-slate-900 border rounded-xl p-3 shadow-sm transition-colors ${incomplete > 0 ? 'border-yellow-800/60' : 'border-slate-800'} ${onClick ? 'cursor-pointer hover:border-indigo-500/50 hover:bg-slate-800/50' : ''}`}
      onClick={onClick}
    >
      <div className="flex justify-between items-center mb-1.5">
        <h3 className="text-slate-400 font-medium text-xs">{title}</h3>
        <div className="p-1 bg-slate-950 rounded border border-slate-800">{icon}</div>
      </div>
      <div className="text-xl font-bold text-white mb-0.5">{value}</div>
      <div className="text-[10px] text-slate-500">{subtitle}</div>
      {/* 草稿/断线订单徽章：有数量时才显示 */}
      {incomplete > 0 && (
        <div className="mt-2 flex items-center gap-1 bg-yellow-900/30 border border-yellow-800/50 rounded-md px-2 py-1">
          <span className="text-yellow-400 text-[10px]">⚠️</span>
          <span className="text-yellow-400 text-[10px] font-medium">
            {incomplete} 待核实
          </span>
        </div>
      )}
    </div>
  );
}

function Card({ title, children }) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-sm">
      <div className="px-6 py-4 border-b border-slate-800 bg-slate-900/50">
        <h3 className="text-lg font-medium text-white">{title}</h3>
      </div>
      <div className="p-6">
        {children}
      </div>
    </div>
  );
}

function InputGroup({ label, helpText, children }) {
  return (
    <div className="space-y-1">
      <label className="block text-sm font-medium text-slate-300">{label}</label>
      {children}
      {helpText && <p className="text-xs text-slate-500">{helpText}</p>}
    </div>
  );
}

function RadioOption({ label, description, value, current, onChange, color }) {
  const isSelected = current === value;
  
  // Tailwind color dynamic classes are tricky if fully interpolated, 
  // so we predefine a mapping for safety or use safe border colors
  const borderColors = {
    green: 'border-green-500',
    yellow: 'border-yellow-500',
    red: 'border-red-500',
    slate: 'border-slate-700'
  };

  const bgColors = {
    green: 'bg-green-950/20',
    yellow: 'bg-yellow-950/20',
    red: 'bg-red-950/20',
    slate: 'bg-slate-900'
  };

  const activeBorder = borderColors[color];
  const activeBg = bgColors[color];

  return (
    <label className={`
      relative flex cursor-pointer rounded-lg border p-4 shadow-sm focus:outline-none transition-all
      ${isSelected ? `${activeBorder} ${activeBg}` : 'border-slate-800 bg-slate-900 hover:border-slate-700'}
    `}>
      <input type="radio" className="sr-only" name="master_switch" value={value} checked={isSelected} onChange={(e) => onChange(e.target.value)} />
      <span className="flex flex-1">
        <span className="flex flex-col">
          <span className={`block text-sm font-medium ${isSelected ? 'text-white' : 'text-slate-300'}`}>{label}</span>
          <span className="mt-1 flex items-center text-xs text-slate-500">{description}</span>
        </span>
      </span>
      {isSelected && <CheckCircle2 className={`mx-auto h-5 w-5 text-${color}-500 absolute top-4 right-4`} />}
    </label>
  );
}

// Missing icon used in sidebar
function Activity(props) {
  return <svg {...props} xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={`lucide lucide-activity ${props.className}`}><path d="M22 12h-2.48a2 2 0 0 0-1.93 1.46l-2.35 8.36a.25.25 0 0 1-.48 0L9.24 2.18a.25.25 0 0 0-.48 0l-2.35 8.36A2 2 0 0 1 4.49 12H2"/></svg>
}

// Subcomponent to trigger automatic scroll to bottom of transcript box
function AutoScrollTrigger({ transcripts }) {
  useEffect(() => {
    const container = document.getElementById('transcript-container');
    if (container) {
      container.scrollTop = container.scrollHeight;
    }
  }, [transcripts]);
  return null;
}

// ----------------------------------------------------------------------
// 辅助组件：打字机效果文本，针对流式转录条目
// ----------------------------------------------------------------------
function TypewriterText({ text, isStreaming }) {
  const [displayed, setDisplayed] = useState('');
  const targetRef = useRef(text);
  const timerRef = useRef(null);

  useEffect(() => {
    targetRef.current = text;

    // 如果已显示文本超过目标（不应出现），直接重置
    if (displayed.length > text.length) {
      setDisplayed(text);
      return;
    }

    // 如果已显示的和目标一致，无需动画
    if (displayed === text) return;

    // 启动逐字显示计时器，25ms/局 ≈ 40字/秒
    if (timerRef.current) return; // 已经在跑了
    timerRef.current = setInterval(() => {
      setDisplayed(prev => {
        const target = targetRef.current;
        if (prev.length >= target.length) {
          clearInterval(timerRef.current);
          timerRef.current = null;
          return target;
        }
        return target.slice(0, prev.length + 1);
      });
    }, 18); // 18ms ≈ 55字/秒

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [text]); // eslint-disable-line react-hooks/exhaustive-deps

  // 如果已完成（is_final）直接显示全文
  useEffect(() => {
    if (!isStreaming) {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
      setDisplayed(text);
    }
  }, [isStreaming, text]);

  return (
    <>
      {displayed}
      {isStreaming && <span className="stream-cursor" />}
    </>
  );
}

// ----------------------------------------------------------------------
// 辅助组件：实时订单小票 (Live Receipt) 覆盖在 Dashboard 右侧
// ----------------------------------------------------------------------
function LiveReceipt({ liveOrder, activeCallCount, lang }) {
  // 待机状态：无通话 且 无小票数据时才显示等待占位
  if (activeCallCount === 0 && !liveOrder) {
    return (
      <Card className="flex-1 h-full min-h-[400px] flex items-center justify-center" title={lang === 'zh' ? '实时订单追踪' : 'Live Order Receipt'}>
        <div className="text-slate-500 flex flex-col items-center gap-3 w-full h-full justify-center opacity-60">
          <Activity size={48} className="text-slate-700" />
          <p>{lang === 'zh' ? '等待顾客来电排单...' : 'Waiting for incoming calls...'}</p>
        </div>
      </Card>
    );
  }

  // 活跃通话无订单数据
  if (!liveOrder) {
    return (
      <Card className="flex-1 h-full min-h-[400px]" title={lang === 'zh' ? '实时订单追踪' : 'Live Order Receipt'}>
        <div className="text-indigo-400 flex flex-col items-center gap-3 w-full h-full justify-center animate-pulse">
          <Bot size={40} className="mb-2" />
          <p>{lang === 'zh' ? 'AI 正在聆听顾客点单...' : 'AI is listening to the customer...'}</p>
        </div>
      </Card>
    );
  }

  // 小票渲染
  return (
    <Card className="flex-1 min-h-[500px] h-full overflow-hidden flex flex-col" title={lang === 'zh' ? '实时订单小票 (POS)' : 'Live POS Receipt'}>
      <div className="bg-white text-black p-4 font-mono text-sm leading-tight flex-1 overflow-y-auto w-full shadow-inner rounded-md h-[400px]">
        {/* Header */}
        <div className="text-center font-bold text-lg mb-2 border-b-2 border-black pb-2">
          NOODLE BOX<br/>
          <span className="text-sm font-normal">REAL-TIME PREVIEW</span>
        </div>

        {/* Items List */}
        <div className="my-2 space-y-3">
          <div className="flex font-bold pb-1 border-b border-gray-400">
            <span className="flex-1">Product</span>
            <span className="w-16 text-right">Price</span>
          </div>

          {liveOrder.items && liveOrder.items.length > 0 ? (
            liveOrder.items.map((item, idx) => (
              <div key={idx} className="flex flex-col">
                <div className="flex font-bold">
                  <span className="flex-1 leading-tight">{item.quantity} * {item.name}</span>
                  <span className="w-16 text-right">{(item.unit_price * item.quantity).toFixed(2)}</span>
                </div>
                {/* Options List */}
                {item.options && item.options.length > 0 && (
                  <div className="pl-4 text-xs mt-0.5 space-y-0.5">
                    {item.options.map((opt, oIdx) => (
                      <div key={oIdx} className="flex">
                        <span className="w-4">&lt;&gt;</span>
                        <span className="flex-1 uppercase">{typeof opt === 'string' ? opt : (opt.name || opt.option || '')}</span>
                        {opt.price_adjustment > 0 && <span className="w-10 text-right">+ {opt.price_adjustment.toFixed(2)}</span>}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))
          ) : (
             <div className="text-center italic opacity-50 py-4">No items yet</div>
          )}
        </div>

        {/* Order Notes */}
        {liveOrder.note && (
          <div className="mt-3 pt-2 border-t border-dashed border-gray-400 text-xs">
            <span className="font-bold">NOTE:</span>
            <p className="mt-0.5 italic text-gray-600 break-words">{liveOrder.note}</p>
          </div>
        )}

        {/* Totals */}
        <div className="mt-4 pt-2 border-t-2 border-black space-y-1 text-right">
          <div className="flex justify-between">
            <span className="font-bold">Subtotal</span>
            <span>€{liveOrder.subtotal != null ? Number(liveOrder.subtotal).toFixed(2) : '0.00'}</span>
          </div>
          <div className="flex justify-between">
            <span className="font-bold">Delivery Fee</span>
            <span>+ €{liveOrder.delivery_fee != null ? Number(liveOrder.delivery_fee).toFixed(2) : '0.00'}</span>
          </div>
          <div className="flex justify-between text-lg font-bold mt-2 pt-2 border-t border-gray-400">
            <span>TOTAL</span>
            <span>€{liveOrder.total != null ? Number(liveOrder.total).toFixed(2) : '0.00'}</span>
          </div>
          <div className="flex justify-between pt-1">
            <span className="font-bold">Payment Method</span>
            <span className="uppercase">{liveOrder.payment_method || 'PENDING'}</span>
          </div>
        </div>
      </div>
    </Card>
  );
}

function OrdersModal({ isOpen, onClose, orders, selectedOrder, setSelectedOrder, onDeleteOrder, t }) {
  if (!isOpen) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-xl shadow-2xl w-full max-w-5xl h-[80vh] flex flex-col overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-800 flex justify-between items-center bg-slate-800/50">
          <h2 className="text-lg font-semibold text-white flex items-center gap-2">
            {selectedOrder ? (
              <>
                <button onClick={() => setSelectedOrder(null)} className="text-slate-400 hover:text-white px-2 py-1 rounded bg-slate-800">
                  ← 返回列表
                </button>
                <span>订单详情: {selectedOrder.id}</span>
              </>
            ) : <><CheckCircle2 size={18} className="text-green-400" /> 今日订单 <span className="text-yellow-400 text-sm font-normal ml-2">⚠️ 未完成/错误通话置顶</span></>}
          </h2>
          <button onClick={onClose} className="text-slate-400 hover:text-white p-2">✕</button>
        </div>
        <OrdersView 
          orders={orders} 
          selectedOrder={selectedOrder} 
          setSelectedOrder={setSelectedOrder} 
          onDeleteOrder={onDeleteOrder} 
          t={t} 
        />
      </div>
    </div>
  );
}

// 抽取出来的复用订单视图（列表 + 详情）
function OrdersView({ orders, selectedOrder, setSelectedOrder, onDeleteOrder, t }) {
  return (
    <div className="flex-1 overflow-hidden flex bg-slate-950 rounded-b-xl lg:rounded-none">
      {!selectedOrder ? (
        // List View
        <div className="flex-1 overflow-y-auto p-6 scrollbar-thin scrollbar-thumb-slate-700">
          {orders.length === 0 ? (
            <div className="text-center text-slate-500 py-10">{t('noHistoryOrders')}</div>

              ) : (
                <div className="space-y-3">
                  {orders.map(o => (
                    <div 
                      key={o.id} 
                      onClick={() => setSelectedOrder(o)}
                      className={`p-4 rounded-lg border cursor-pointer hover:bg-slate-800 transition-colors flex justify-between items-center ${
                        o.source.includes('Incomplete') 
                          ? 'bg-yellow-950/40 border-yellow-800/50' 
                          : 'bg-slate-800/20 border-slate-700/50'
                      }`}
                    >
                      <div>
                        <div className="flex items-center gap-2 mb-1">
                          <span className="font-medium text-white">{o.customer_name || 'Unknown'}</span>
                          <span className="text-xs text-slate-400">{o.customer_phone}</span>
                          {o.source.includes('Incomplete') && (
                            <span className="text-[10px] bg-yellow-900/60 text-yellow-300 px-2 py-0.5 rounded-full border border-yellow-700">⚠️ {t('draftIncomplete')}</span>
                          )}
                        </div>
                        <div className="text-xs text-slate-500 flex gap-4">
                          <span>📅 {new Date(o.created_at).toLocaleString()}</span>
                          <span>🚚 {o.service_type} ({o.delivery_area})</span>
                          <span>💳 {o.payment_method}</span>
                        </div>
                        {(o.notes || o.note) && (
                          <div className="text-xs text-amber-400/80 mt-1 flex items-center gap-1 max-w-xs">
                            <span>📝</span>
                            <span className="truncate">{o.notes || o.note}</span>
                          </div>
                        )}
                      </div>
                      <div className="text-right flex flex-col items-end gap-1.5">
                        <div className="text-lg font-bold text-green-400">€{parseFloat(o.total_value).toFixed(2)}</div>
                        <div className="flex items-center gap-3">
                          <span className="text-xs text-slate-500">
                            {(() => {
                              try {
                                return (typeof o.items === 'string' ? JSON.parse(o.items) : (o.items || [])).length;
                              } catch(e) { return 0; }
                            })()} {t('itemUnit')}
                          </span>
                          <button 
                            onClick={(e) => onDeleteOrder(o.id, e)} 
                            className="text-red-400 hover:text-red-300 p-1 rounded hover:bg-red-400/20 transition-colors"
                            title={t('deleteOrder')}
                          >
                            <Trash2 size={16} />
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            // Detail View
            <div className="flex-1 flex overflow-hidden">
              {/* Left: Transcript */}
              <div className="flex-1 border-r border-slate-800 flex flex-col bg-slate-950">
                <div className="p-3 bg-slate-800/30 text-xs font-semibold text-slate-400 border-b border-slate-800">
                  {t('transcriptTitle')}
                </div>
                <div className="flex-1 overflow-y-auto p-4 space-y-4 right-pane-scrollbar">
                  {(() => {
                    let ts = [];
                    try {
                      ts = typeof selectedOrder.transcript === 'string' ? JSON.parse(selectedOrder.transcript) : (selectedOrder.transcript || []);
                    } catch(e) {}
                    if (!ts || ts.length === 0) return <div className="text-center text-slate-600 py-10">{t('noTranscript')}</div>;
                    
                    return ts.map((msg, i) => (
                       <div key={i} className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
                         <span className="text-[10px] text-slate-500 mb-1 px-1">
                             {msg.role === 'user' ? t('userRole') : t('aiRole')}
                         </span>
                         <div className={`px-4 py-2 rounded-2xl max-w-[85%] text-sm leading-relaxed ${
                           msg.role === 'user' 
                              ? 'bg-indigo-600/80 text-white rounded-tr-none' 
                              : msg.role === 'thought'
                                ? 'bg-slate-800/50 text-slate-400 italic text-xs border border-slate-700/50 rounded-tl-none'
                                : 'bg-slate-800 text-slate-200 border border-slate-700 rounded-tl-none'
                         }`}>
                           {msg.text}
                         </div>
                       </div>
                    ));
                  })()}
                </div>
              </div>

              {/* Right: Order Detail */}
              <div className="w-[350px] bg-slate-900 flex flex-col overflow-y-auto right-pane-scrollbar">
                 <div className="p-4 border-b border-slate-800 shrink-0">
                    <h3 className="text-lg font-bold text-white mb-3">{t('orderContentTitle')}</h3>
                    <div className="space-y-1.5 text-sm text-slate-300">
                      <p className="flex justify-between"><span className="text-slate-500">{t('orderIdLabel')}</span> <span className="text-xs">{selectedOrder.id}</span></p>
                      <p className="flex justify-between"><span className="text-slate-500">{t('orderCustomerLabel')}</span> <span>{selectedOrder.customer_name}</span></p>
                      <p className="flex justify-between"><span className="text-slate-500">{t('orderPhoneLabel')}</span> <span>{selectedOrder.customer_phone}</span></p>
                      <p className="flex justify-between"><span className="text-slate-500">{t('orderAddressLabel')}</span> <span className="text-right max-w-[200px] truncate" title={selectedOrder.address}>{selectedOrder.address || 'N/A'}</span></p>
                      <p className="flex justify-between"><span className="text-slate-500">{t('orderDeliveryLabel')}</span> <span>{selectedOrder.service_type} - {selectedOrder.delivery_area}</span></p>
                      <div className="mt-2 pt-2 border-t border-slate-800">
                        <p className="text-slate-500 mb-1">{t('orderNoteLabel')}</p>
                        <p className="text-yellow-400 text-xs bg-yellow-950/20 p-2 rounded border border-yellow-900/40">
                          {selectedOrder.note || selectedOrder.notes || t('orderNoteEmpty')}
                        </p>
                      </div>
                    </div>
                 </div>
                   <div className="p-4 flex-1">
                    <h4 className="text-sm font-semibold text-slate-400 mb-3">{t('itemReceipt')}</h4>
                    <div className="space-y-3">
                      {(() => {
                        let itms = [];
                        try {
                          itms = typeof selectedOrder.items === 'string' ? JSON.parse(selectedOrder.items) : (selectedOrder.items || []);
                        } catch(e) {}
                        
                        return itms.map((item, i) => (
                        <div key={i} className="flex justify-between items-start text-sm border-b border-slate-800/50 pb-2">
                           <div className="flex-1 pr-2">
                             <div className="font-medium text-slate-200">
                               {item.quantity && item.quantity > 1 ? `${item.quantity} x ` : ''}{item.name || 'Unknown Item'}
                             </div>
                             {item.options && item.options.length > 0 && (
                               <div className="text-xs text-slate-500 pl-2 mt-0.5">
                                 {item.options.map((opt, oIdx) => (
                                   <div key={oIdx}>
                                     + {typeof opt === 'string' ? opt : (opt.name || opt.option || JSON.stringify(opt))}
                                     {opt.price_adjustment ? ` (€${opt.price_adjustment.toFixed(2)})` : ''}
                                   </div>
                                 ))}
                               </div>
                             )}
                           </div>
                           <div className="font-semibold tabular-nums text-slate-300">
                             €{parseFloat((item.unit_price || item.price || 0) * (item.quantity || 1)).toFixed(2)}
                           </div>
                        </div>
                      ))})()}
                    </div>
                 </div>
                 <div className="p-4 border-t border-slate-800 bg-slate-800/20 shrink-0">
                    <div className="flex justify-between text-sm mb-1">
                      <span className="text-slate-400">{t('deliveryFeeLabel')}</span>
                      <span>€{parseFloat(selectedOrder.delivery_fee || 0).toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between text-lg font-bold mt-2 pt-2 border-t border-slate-700">
                      <span>{t('totalLabel')} ({selectedOrder.payment_method}):</span>
                      <span className="text-green-400">€{parseFloat(selectedOrder.total_value).toFixed(2)}</span>
                    </div>
                 </div>
              </div>
            </div>
          )}
    </div>
  );
}

export default App;

function LoginScreen({ setSysToken, setSysRole, t, lang, setLang }) {
  const [password, setPassword] = React.useState('');
  const [error, setError] = React.useState('');
  const [loading, setLoading] = React.useState(false);

  const handleLogin = async (role) => {
    setError('');
    setLoading(true);
    try {
      const payload = role === 'admin' ? { password } : { role: 'staff' };
      const res = await axios.post(`${API_URL}/login`, payload);
      if (res.data.token) {
        localStorage.setItem('sys_token', res.data.token);
        localStorage.setItem('sys_role', res.data.role);
        setSysToken(res.data.token);
        setSysRole(res.data.role);
        // Force reload so Axios interceptors and fetchSettings trigger cleanly from scratch
        window.location.reload();
      }
    } catch (err) {
      console.error(err);
      setError(err.response?.data?.detail || err.message || t('unauthorized'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col items-center justify-center p-4">
      <div className="absolute top-4 right-4">
        <button onClick={() => setLang(lang === 'zh' ? 'en' : 'zh')} className="flex items-center gap-2 px-3 py-1.5 rounded-md text-sm border border-slate-700 text-slate-300 hover:bg-slate-800 transition-colors">
          <Globe size={16} /> {lang === 'zh' ? 'English' : '中文'}
        </button>
      </div>

      <div className="mb-10 text-center">
        <img src="/logo.png" alt="Logo" className="h-20 mx-auto mb-6 drop-shadow-lg" />
        <h1 className="text-3xl font-bold text-white tracking-tight">{t('brandName')}</h1>
        <p className="text-slate-500 mt-2">{t('loginTitle')}</p>
      </div>

      <div className="w-full max-w-2xl grid grid-cols-1 md:grid-cols-2 gap-6">
        
        {/* Staff Card */}
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-8 hover:border-indigo-500/50 transition-all flex flex-col justify-between group h-full cursor-default">
          <div>
            <div className="w-12 h-12 bg-indigo-900/30 rounded-xl flex items-center justify-center mb-6 border border-indigo-500/30">
              <Users className="text-indigo-400" size={24} />
            </div>
            <h2 className="text-xl font-bold text-white mb-2">{t('staffAccess')}</h2>
            <p className="text-slate-400 text-sm mb-8 leading-relaxed">{t('staffDesc')}</p>
          </div>
          {error && <p className="text-red-400 text-sm mb-4 bg-red-950/30 p-2 rounded border border-red-900/50 select-none break-all">{error}</p>}
          <button 
            disabled={loading}
            onClick={() => handleLogin('staff')}
            className="w-full py-3 bg-slate-800 hover:bg-indigo-600 text-white rounded-xl font-medium transition-colors border border-slate-700 hover:border-indigo-500 group-hover:shadow-[0_0_20px_rgba(79,70,229,0.2)]"
          >
            {t('loginBtn')} 
          </button>
        </div>

        {/* Admin Card */}
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-8 hover:border-red-500/50 transition-all flex flex-col justify-between group h-full relative overflow-hidden">
          <div className="absolute top-0 right-0 w-32 h-32 bg-red-500/5 rounded-bl-full pointer-events-none"></div>
          <div className="relative z-10">
            <div className="w-12 h-12 bg-red-900/30 rounded-xl flex items-center justify-center mb-6 border border-red-500/30">
              <Settings className="text-red-400" size={24} />
            </div>
            <h2 className="text-xl font-bold text-white mb-2">{t('adminAccess')}</h2>
            <p className="text-slate-400 text-sm mb-6 leading-relaxed">{t('adminDesc')}</p>
            
            <div className="space-y-2 mb-6">
              <label className="text-xs font-medium text-slate-500 uppercase tracking-wider">{t('passwordLabel')}</label>
              <input 
                type="password"
                className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-red-500 focus:ring-1 focus:ring-red-500 transition-all"
                placeholder={t('enterPassword')}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleLogin('admin')}
              />
            </div>
            {error && <p className="text-red-400 text-sm mb-4 bg-red-950/30 p-2 rounded border border-red-900/50 select-none">{error}</p>}
          </div>
          
          <button 
            disabled={loading || !password}
            onClick={() => handleLogin('admin')}
            className="relative z-10 w-full py-3 bg-red-950/40 hover:bg-red-600 text-red-200 hover:text-white rounded-xl font-medium transition-colors border border-red-900/50 hover:border-red-500 disabled:opacity-50 disabled:cursor-not-allowed group-hover:shadow-[0_0_20px_rgba(220,38,38,0.2)]"
          >
            {t('loginBtn')}
          </button>
        </div>

      </div>
    </div>
  );
}

function LockedView({ t }) {
  const handleLogout = () => {
    localStorage.removeItem('sys_token');
    localStorage.removeItem('sys_role');
    window.location.reload();
  };

  return (
    <div className="h-[80%] flex items-center justify-center p-8 animate-in fade-in zoom-in duration-300">
      <div className="max-w-md w-full bg-slate-900 border border-slate-800 rounded-2xl p-10 text-center shadow-2xl relative overflow-hidden">
        <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-red-500 to-orange-500"></div>
        <div className="w-20 h-20 bg-red-950/50 rounded-full flex items-center justify-center mx-auto mb-6 border border-red-900/50">
          <Lock size={32} className="text-red-500" />
        </div>
        <h2 className="text-2xl font-bold text-white mb-3">{t('unauthorized')}</h2>
        <p className="text-slate-400 leading-relaxed mb-8">
          {t('lockedDesc')}
        </p>
        <button 
          onClick={handleLogout}
          className="px-6 py-2.5 bg-slate-800 hover:bg-slate-700 text-white rounded-lg transition-colors border border-slate-700 font-medium"
        >
          {t('logout')} & Switch Account
        </button>
      </div>
    </div>
  );
}
