import React, { useState, useEffect, useRef } from 'react';
import { Phone, PhoneOff, Mic, Activity, User, LogOut } from 'lucide-react';

const WebCallSimulator = ({ t, aiBusy }) => {
  const [isCalling, setIsCalling] = useState(false);
  const [phoneNumber, setPhoneNumber] = useState('10000');
  const [status, setStatus] = useState('Ready');
  
  // Audio Context and WeboSocket Ref
  const wsRef = useRef(null);
  const audioContextRef = useRef(null);
  const mediaStreamRef = useRef(null);
  const processorRef = useRef(null);
  const nextPlayTimeRef = useRef(0);
  const isCallingRef = useRef(false);
  
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const currentToken = localStorage.getItem('admin_token') || '';
  const tokenParam = currentToken ? `?token=${currentToken}` : '';
  const API_URL_WS = window.location.host.includes('localhost:5173') 
    ? `ws://localhost:5000/api/admin/web_call${tokenParam}`
    : `${protocol}//${window.location.host}/api/admin/web_call${tokenParam}`;

  const playBase64Audio = (base64Audio, sampleRate = 24000) => {
    if (!audioContextRef.current) return;
    
    try {
        // Safely parse Base64 avoiding odd-length Int16Array crash
        let safeBase64 = base64Audio;
        while (safeBase64.length % 4 !== 0) {
            safeBase64 += '=';
        }
        const binary = atob(safeBase64);
        const validLength = binary.length - (binary.length % 2);
        const bytes = new Uint8Array(validLength);
        for (let i = 0; i < validLength; i++) {
            bytes[i] = binary.charCodeAt(i);
        }
        
        // Create AudioBuffer from 16-bit PCM
        const view = new Int16Array(bytes.buffer, 0, validLength / 2);
        const audioBuffer = audioContextRef.current.createBuffer(1, view.length, sampleRate);
        const channelData = audioBuffer.getChannelData(0);
        for (let i = 0; i < view.length; i++) {
            channelData[i] = view[i] / 32768.0; 
        }
        
        const source = audioContextRef.current.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(audioContextRef.current.destination);
        
        const currentTime = audioContextRef.current.currentTime;
        const startTime = Math.max(currentTime, nextPlayTimeRef.current);
        source.start(startTime);
        nextPlayTimeRef.current = startTime + audioBuffer.duration;
    } catch (e) {
        console.error("Audio playback error:", e);
    }
  };

  const startCall = async () => {
    setIsCalling(true);
    isCallingRef.current = true;
    setStatus('Connecting...');
    nextPlayTimeRef.current = 0;
    
    try {
        // 1. Initialize AudioContext synchronously within the user click gesture
        const audioContext = new (window.AudioContext || window.webkitAudioContext)({
            sampleRate: 16000 // Force 16k for Gemini input
        });
        audioContextRef.current = audioContext;

        if (audioContext.state === 'suspended') {
            await audioContext.resume();
        }

        // 2. Request microphone access
        const stream = await navigator.mediaDevices.getUserMedia({ 
            audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } 
        });
        mediaStreamRef.current = stream;

        // 3. Initialize WebSocket AFTER we have mic access
        wsRef.current = new WebSocket(API_URL_WS);
        
        wsRef.current.onopen = async () => {
            if (audioContext.state === 'suspended') {
                await audioContext.resume();
            }
            setStatus('Connected. Starting stream...');
            wsRef.current.send(JSON.stringify({
               event: 'start',
               customer_number: phoneNumber
            }));
            
            // 4. Hook up audio processing pipeline
            const source = audioContext.createMediaStreamSource(stream);
            
            // Use ScriptProcessorNode for raw PCM extraction
            const processor = audioContext.createScriptProcessor(4096, 1, 1);
            processorRef.current = processor;
            
            processor.onaudioprocess = (e) => {
                if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN || !isCallingRef.current) return;
                
                const inputData = e.inputBuffer.getChannelData(0);
                
                // Convert Float32 to Int16
                const pcm16 = new Int16Array(inputData.length);
                for (let i = 0; i < inputData.length; i++) {
                    let s = Math.max(-1, Math.min(1, inputData[i]));
                    pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
                }
                
                // Convert to Base64 (using the fast chunked apply method)
                const uint8Array = new Uint8Array(pcm16.buffer);
                let binary = '';
                const chunkSize = 8192;
                for (let i = 0; i < uint8Array.length; i += chunkSize) {
                    binary += String.fromCharCode.apply(null, uint8Array.subarray(i, i + chunkSize));
                }
                const base64 = window.btoa(binary);
                
                wsRef.current.send(JSON.stringify({
                    event: 'media',
                    payload: base64
                }));
            };
            
            source.connect(processor);
            processor.connect(audioContext.destination);
            setStatus('Recording...');
        };
        
        wsRef.current.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.event === 'media') {
                playBase64Audio(data.payload, data.sampleRate || 24000);
            } else if (data.event === 'clear') {
                nextPlayTimeRef.current = audioContextRef.current ? audioContextRef.current.currentTime : 0;
            } else if (data.event === 'close') {
                stopCall();
                setStatus('Call ended by AI.');
            }
        };
        
        wsRef.current.onclose = () => {
            stopCall();
        };
        
        wsRef.current.onerror = (err) => {
            console.error("WebSocket error:", err);
            setStatus('WebSocket Error');
            stopCall();
        };

    } catch (err) {
        console.error('Microphone or setup error:', err);
        setStatus('Mic access denied or setup error.');
        stopCall();
    }
  };

  const stopCall = () => {
    setIsCalling(false);
    isCallingRef.current = false;
    
    if (wsRef.current) {
        if (wsRef.current.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify({event: 'stop'}));
        }
        wsRef.current.close();
        wsRef.current = null;
    }
    
    if (processorRef.current) {
        processorRef.current.disconnect();
        processorRef.current = null;
    }
    
    if (mediaStreamRef.current) {
        mediaStreamRef.current.getTracks().forEach(track => track.stop());
        mediaStreamRef.current = null;
    }
    
    if (audioContextRef.current) {
        audioContextRef.current.close();
        audioContextRef.current = null;
    }
    nextPlayTimeRef.current = 0;
    setStatus('Ready');
  };
  
  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopCall();
    };
  }, []);

  return (
    <div className="bg-slate-900 border border-slate-700 rounded-xl p-5 mt-6 mb-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-bold text-white flex items-center">
          <Phone className="w-5 h-5 mr-2 text-indigo-400" />
          {t?.('webSimTitle') || 'WebRTC Call Simulator'}
        </h3>
        {isCalling && (
          <div className="flex items-center space-x-2 text-emerald-400/80 animate-pulse">
             <Activity className="w-4 h-4" />
             <span className="text-xs font-semibold uppercase tracking-wider">{t?.('liveAudio') || 'Live Audio'}</span>
          </div>
        )}
      </div>
      
      <p className="text-xs mb-5">
        <span className="text-slate-400">{t?.('status') || 'Status'}: </span>
        <span className="text-indigo-300 font-mono font-medium">{status}</span>
      </p>

      <div className="flex flex-col gap-4">
        <div>
          <label className="block text-xs font-semibold text-slate-300 mb-1 flex items-center">
            <User className="w-4 h-4 mr-1"/> {t?.('virtualNumber') || 'Virtual Phone Number'}
          </label>
          <input
            type="text"
            className="w-full bg-slate-800 border border-slate-700 text-white placeholder-slate-500 rounded-lg p-3 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition-colors"
            value={phoneNumber}
            onChange={(e) => setPhoneNumber(e.target.value)}
            disabled={isCalling}
            placeholder="e.g. +35383123456"
          />
        </div>
        
        <div>
          {!isCalling ? (
            <button 
              onClick={startCall}
              disabled={aiBusy}
              className={`w-full font-medium p-3 rounded-lg flex items-center justify-center transition-colors ${
                 aiBusy 
                   ? 'bg-slate-800 text-slate-500 cursor-not-allowed border border-slate-700' 
                   : 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-900/20'
              }`}
            >
              <Mic className={`w-4 h-4 mr-2 ${aiBusy ? 'text-slate-600' : ''}`} /> 
              {aiBusy ? (t?.('aiBusyBtn') || 'AI Currently Busy') : (t?.('startCall') || 'Start Voice Call')}
            </button>
          ) : (
             <button 
              onClick={stopCall}
              className="w-full bg-rose-600 hover:bg-rose-500 text-white font-medium p-3 rounded-lg flex items-center justify-center transition-colors shadow-lg shadow-rose-900/50"
            >
              <PhoneOff className="w-4 h-4 mr-2" /> {t?.('endCall') || 'End Call'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default WebCallSimulator;
