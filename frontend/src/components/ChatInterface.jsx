import React, { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
    Send,
    Plus,
    MessageSquare,
    Trash2,
    Menu,
    X,
    Sparkles,
    Mic,
    Copy,
    Check,
    Clock,
    Search,
    FileText,
    MapPin,
    AlertTriangle,
    Stethoscope,
    Activity,
    Pill,
    Heart,
    Shield,
    Loader2,
    ChevronRight,
    Map,
    BookOpen,
    Zap,
    User as UserIcon,
    Brain,
    Database,
    Phone,
    Volume2,
    VolumeX,
    Camera
} from 'lucide-react';
import MapView from './MapView';

// AEGIS Color Theme Constants
const AEGIS_THEME = {
    primary: 'from-teal-500 to-cyan-500',
    primarySolid: 'bg-teal-500',
    accent: 'from-cyan-400 to-blue-500',
    background: 'from-slate-950 via-slate-900 to-slate-950',
    surface: 'bg-slate-900/50',
    surfaceHover: 'hover:bg-slate-800/50',
    border: 'border-slate-800/50',
    text: 'text-slate-100',
    textMuted: 'text-slate-400',
    glow: 'shadow-teal-500/20'
};

// Tool configurations with icons and colors
const TOOL_CONFIG = {
    'SEARCH': { icon: Search, label: 'Searching medical knowledge...', color: 'text-blue-400', bg: 'bg-blue-500/10' },
    'GUIDANCE': { icon: BookOpen, label: 'Finding clinical guidelines...', color: 'text-cyan-400', bg: 'bg-cyan-500/10' },
    'READ_HISTORY': { icon: FileText, label: 'Reading medical records...', color: 'text-purple-400', bg: 'bg-purple-500/10' },
    'LOCATE': { icon: MapPin, label: 'Finding nearby facilities...', color: 'text-green-400', bg: 'bg-green-500/10' },
    'FIND_PROVIDERS': { icon: Stethoscope, label: 'Searching for providers...', color: 'text-teal-400', bg: 'bg-teal-500/10' },
    'GET_PROFILE': { icon: UserIcon, label: 'Loading patient profile...', color: 'text-indigo-400', bg: 'bg-indigo-500/10' },
    'CHECK_SAFETY': { icon: Shield, label: 'Checking medication safety...', color: 'text-amber-400', bg: 'bg-amber-500/10' },
    'GET_SUMMARIES': { icon: Activity, label: 'Analyzing health data...', color: 'text-rose-400', bg: 'bg-rose-500/10' },
    'SAVE_SUMMARY': { icon: FileText, label: 'Saving daily summary...', color: 'text-orange-400', bg: 'bg-orange-500/10' },
    'ANALYZE_HEALTH': { icon: Brain, label: 'Analyzing health topic...', color: 'text-pink-400', bg: 'bg-pink-500/10' },
    'WATCH_VITALS': { icon: Activity, label: 'Reading Galaxy Watch...', color: 'text-cyan-400', bg: 'bg-cyan-500/10' },
    'GET_BRIEFING': { icon: Brain, label: 'Generating health briefing...', color: 'text-violet-400', bg: 'bg-violet-500/10' },
    'CALL_PHYSICIAN': { icon: Phone, label: 'Initiating call...', color: 'text-emerald-400', bg: 'bg-emerald-500/10' },
    'SAVE_PHYSICIAN': { icon: Database, label: 'Saving contact...', color: 'text-sky-400', bg: 'bg-sky-500/10' },
};

const ChatInterface = () => {
    const [sessions, setSessions] = useState([]);
    const [currentSessionId, setCurrentSessionId] = useState(null);
    const [messages, setMessages] = useState([]);
    const [input, setInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [isStreaming, setIsStreaming] = useState(false);
    const [isSidebarOpen, setIsSidebarOpen] = useState(true);
    const [copiedIndex, setCopiedIndex] = useState(null);
    const [currentTool, setCurrentTool] = useState(null);
    const [toolHistory, setToolHistory] = useState([]); // Track tools used in current response
    const [visibleMaps, setVisibleMaps] = useState({});
    const [userLocation, setUserLocation] = useState(null);
    const [isListening, setIsListening] = useState(false);
    const [voiceMode, setVoiceMode] = useState(false);

    // Camera State
    const [isCameraOpen, setIsCameraOpen] = useState(false);
    const [capturedImage, setCapturedImage] = useState(null);

    const messagesEndRef = useRef(null);
    const inputRef = useRef(null);
    const recognitionRef = useRef(null);
    const audioRef = useRef(new Audio());
    const videoRef = useRef(null);
    const canvasRef = useRef(null);

    // Initialize Speech Recognition
    useEffect(() => {
        if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
            const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
            recognitionRef.current = new SpeechRecognition();
            recognitionRef.current.continuous = false;
            recognitionRef.current.interimResults = false;
            recognitionRef.current.lang = 'en-US';

            recognitionRef.current.onresult = (event) => {
                const transcript = event.results[0][0].transcript;
                setInput(transcript);
                handleSend(transcript); // Auto-send on voice input
            };

            recognitionRef.current.onend = () => {
                setIsListening(false);
            };

            recognitionRef.current.onerror = (event) => {
                console.error("Speech recognition error", event.error);
                setIsListening(false);
            };
        }
    }, []);

    const toggleListening = () => {
        if (isListening) {
            recognitionRef.current?.stop();
            setIsListening(false);
        } else {
            recognitionRef.current?.start();
            setIsListening(true);
            setVoiceMode(true); // Auto-enable voice mode when using mic
        }
    };

    const playAudio = (url) => {
        if (!voiceMode) return;
        audioRef.current.src = `http://localhost:8000${url}`;
        audioRef.current.play().catch(e => console.error("Audio play error:", e));
    };

    // Camera Functions
    const [devices, setDevices] = useState([]);
    const [selectedDeviceId, setSelectedDeviceId] = useState('');

    const startCamera = async (deviceId = null) => {
        setIsCameraOpen(true);

        const stopCurrentStream = () => {
            if (videoRef.current && videoRef.current.srcObject) {
                const tracks = videoRef.current.srcObject.getTracks();
                tracks.forEach(track => track.stop());
            }
        };

        stopCurrentStream();

        try {
            let stream;
            let usedDeviceId = deviceId;

            if (deviceId) {
                stream = await navigator.mediaDevices.getUserMedia({ video: { deviceId: { exact: deviceId } } });
            } else {
                // Try default first
                try {
                    stream = await navigator.mediaDevices.getUserMedia({ video: true });
                } catch (defaultErr) {
                    console.warn("Default camera failed, attempting to switch...", defaultErr);

                    // If default fails, enumerate and try the next available one
                    const deviceList = await navigator.mediaDevices.enumerateDevices();
                    const videoDevices = deviceList.filter(device => device.kind === 'videoinput');
                    setDevices(videoDevices);

                    if (videoDevices.length > 1) {
                        // Try the second device (often the rear camera or external webcam)
                        const nextDevice = videoDevices[1];
                        console.log("Switching to fallback camera:", nextDevice.label);
                        stream = await navigator.mediaDevices.getUserMedia({ video: { deviceId: { exact: nextDevice.deviceId } } });
                        usedDeviceId = nextDevice.deviceId;
                    } else {
                        throw defaultErr; // No other options, re-throw
                    }
                }
            }

            if (videoRef.current) {
                videoRef.current.srcObject = stream;
            }

            // Enumerate devices after getting permission
            const deviceList = await navigator.mediaDevices.enumerateDevices();
            const videoDevices = deviceList.filter(device => device.kind === 'videoinput');
            setDevices(videoDevices);

            if (!usedDeviceId && stream) {
                const track = stream.getVideoTracks()[0];
                const settings = track.getSettings();
                usedDeviceId = settings.deviceId || (videoDevices.length > 0 ? videoDevices[0].deviceId : '');
            }
            setSelectedDeviceId(usedDeviceId);

        } catch (err) {
            console.error("Error accessing camera:", err);
            setIsCameraOpen(false);

            let errorMessage = "Could not access camera.";
            if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
                errorMessage = "Camera permission denied. Please allow camera access in your browser settings.";
            } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
                errorMessage = "No camera found on your device.";
            } else if (err.name === 'NotReadableError' || err.name === 'TrackStartError') {
                errorMessage = "Camera is currently in use by another application.";
            } else if (err.name === 'OverconstrainedError') {
                errorMessage = "The requested camera is not available.";
            } else {
                errorMessage = `Camera error: ${err.name} - ${err.message}`;
            }

            alert(errorMessage);
        }
    };

    const stopCamera = () => {
        if (videoRef.current && videoRef.current.srcObject) {
            const tracks = videoRef.current.srcObject.getTracks();
            tracks.forEach(track => track.stop());
            videoRef.current.srcObject = null;
        }
        setIsCameraOpen(false);
        setCapturedImage(null);
    };

    const handleDeviceChange = (e) => {
        const newDeviceId = e.target.value;
        setSelectedDeviceId(newDeviceId);
        startCamera(newDeviceId);
    };

    const captureImage = () => {
        if (videoRef.current && canvasRef.current) {
            const context = canvasRef.current.getContext('2d');
            context.drawImage(videoRef.current, 0, 0, 640, 480);
            const imageDataUrl = canvasRef.current.toDataURL('image/jpeg');
            setCapturedImage(imageDataUrl);

            // Stop camera stream after capture
            if (videoRef.current.srcObject) {
                const tracks = videoRef.current.srcObject.getTracks();
                tracks.forEach(track => track.stop());
            }
        }
    };

    const sendImageAnalysis = async () => {
        if (!capturedImage) return;

        // Convert base64 to blob
        const res = await fetch(capturedImage);
        const blob = await res.blob();
        const file = new File([blob], "capture.jpg", { type: "image/jpeg" });

        const formData = new FormData();
        formData.append('file', file);
        formData.append('prompt', "Analyze this image. If it's a medication, identify it and check for safety. If it's a medical report, summarize it.");

        // Add user message to chat immediately
        const userMsg = {
            role: 'user',
            content: "📷 [Analyzing Image...]",
            timestamp: new Date().toISOString()
        };
        setMessages(prev => [...prev, userMsg]);
        setIsCameraOpen(false);
        setCapturedImage(null);
        setIsLoading(true);

        try {
            const token = localStorage.getItem('token');
            const response = await fetch('http://localhost:8000/analyze/vision', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`
                },
                body: formData
            });

            const data = await response.json();

            // Add bot response
            const botMsg = {
                role: 'assistant',
                content: data.analysis,
                timestamp: new Date().toISOString()
            };
            setMessages(prev => [...prev, botMsg]);

        } catch (error) {
            console.error("Vision analysis failed:", error);
            setMessages(prev => [...prev, {
                role: 'assistant',
                content: "Sorry, I couldn't analyze that image. Please try again.",
                timestamp: new Date().toISOString(),
                isError: true
            }]);
        } finally {
            setIsLoading(false);
        }
    };

    // Request browser geolocation on mount
    useEffect(() => {
        if (navigator.geolocation) {
            navigator.geolocation.getCurrentPosition(
                (position) => {
                    setUserLocation({
                        lat: position.coords.latitude,
                        lon: position.coords.longitude
                    });
                },
                (error) => {
                    console.log("[Location] Geolocation unavailable:", error.message);
                },
                { enableHighAccuracy: false, timeout: 10000 }
            );
        }
    }, []);

    // Check if message contains location data
    const hasLocationData = (content) => {
        if (!content) return false;
        return content.includes('google.com/maps/dir') &&
            content.includes('destination=');
    };

    const toggleMap = (index) => {
        setVisibleMaps(prev => ({ ...prev, [index]: !prev[index] }));
    };

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages]);

    useEffect(() => {
        fetchSessions();
    }, []);

    const fetchSessions = async () => {
        try {
            const token = localStorage.getItem('token');
            const res = await fetch('http://localhost:8000/chat/sessions', {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (res.ok) {
                const data = await res.json();
                setSessions(data);
            }
        } catch (err) {
            console.error("Failed to fetch sessions", err);
        }
    };

    const createNewSession = async () => {
        try {
            const token = localStorage.getItem('token');
            const res = await fetch('http://localhost:8000/chat/sessions', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({ title: "New Chat" })
            });
            if (res.ok) {
                const session = await res.json();
                setSessions([session, ...sessions]);
                setCurrentSessionId(session.id);
                setMessages([{
                    role: 'assistant',
                    content: `# Welcome to AEGIS Health Assistant 👋

I'm **Sentinel**, your AI-powered health companion. I can help you with:

- 📋 **Medical Records** — Review your health history and test results
- 💊 **Medication Safety** — Check drug interactions and side effects  
- 🏥 **Find Care** — Locate hospitals, pharmacies, and specialists nearby
- 📊 **Health Insights** — Analyze trends and get personalized guidance
- 📞 **Connect with Doctors** — Schedule calls with your physicians

*How can I assist you today?*`,
                    timestamp: new Date().toISOString()
                }]);
            }
        } catch (err) {
            console.error("Failed to create session", err);
        }
    };

    const loadSession = async (sessionId) => {
        setCurrentSessionId(sessionId);
        setIsLoading(true);
        try {
            const token = localStorage.getItem('token');
            const res = await fetch(`http://localhost:8000/chat/sessions/${sessionId}`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (res.ok) {
                const data = await res.json();
                setMessages(data.length > 0 ? data : [{
                    role: 'assistant',
                    content: "Hello! I'm Sentinel. How can I help you today?",
                    timestamp: new Date().toISOString()
                }]);
            }
        } catch (err) {
            console.error("Failed to load session", err);
        } finally {
            setIsLoading(false);
        }
    };

    const deleteSession = async (e, sessionId) => {
        e.stopPropagation();
        if (!confirm("Delete this chat?")) return;
        try {
            const token = localStorage.getItem('token');
            await fetch(`http://localhost:8000/chat/sessions/${sessionId}`, {
                method: 'DELETE',
                headers: { 'Authorization': `Bearer ${token}` }
            });
            setSessions(sessions.filter(s => s.id !== sessionId));
            if (currentSessionId === sessionId) {
                setCurrentSessionId(null);
                setMessages([]);
            }
        } catch (err) {
            console.error("Failed to delete session", err);
        }
    };

    const copyToClipboard = (text, index) => {
        navigator.clipboard.writeText(text);
        setCopiedIndex(index);
        setTimeout(() => setCopiedIndex(null), 2000);
    };

    // Parse tool calls from streaming response
    const parseToolCall = (content) => {
        const toolPatterns = Object.keys(TOOL_CONFIG);
        for (const tool of toolPatterns) {
            const regex = new RegExp(`\\[${tool}:\\s*([^\\]]+)\\]`);
            const match = content.match(regex);
            if (match) {
                return { tool, args: match[1] };
            }
        }
        return null;
    };

    const handleSend = async (overrideInput = null) => {
        const textToSend = overrideInput || input;
        if (!textToSend.trim()) return;

        let activeSessionId = currentSessionId;
        if (!activeSessionId) {
            const token = localStorage.getItem('token');
            const res = await fetch('http://localhost:8000/chat/sessions', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({ title: textToSend.substring(0, 30) || "New Chat" })
            });
            if (res.ok) {
                const session = await res.json();
                setSessions([session, ...sessions]);
                setCurrentSessionId(session.id);
                activeSessionId = session.id;
            }
        }

        const userMessage = {
            role: 'user',
            content: textToSend,
            timestamp: new Date().toISOString()
        };
        setMessages(prev => [...prev, userMessage]);
        setInput('');
        setIsLoading(true);
        setIsStreaming(true);
        setToolHistory([]);

        // Add placeholder for bot response
        setMessages(prev => [...prev, {
            role: 'assistant',
            content: '',
            timestamp: new Date().toISOString(),
            isStreaming: true,
            toolsUsed: []
        }]);

        try {
            const token = localStorage.getItem('token');
            const response = await fetch('http://localhost:8000/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({
                    message: userMessage.content,
                    session_id: activeSessionId,
                    history: messages.slice(-5).map(m => ({ role: m.role, content: m.content })),
                    voice_enabled: voiceMode,
                    ...(userLocation && { user_location: userLocation })
                })
            });

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let botContent = '';
            let usedTools = [];

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value);
                const lines = chunk.split('\n');

                for (const line of lines) {
                    if (line.trim()) {
                        try {
                            const data = JSON.parse(line);
                            if (data.token) {
                                botContent += data.token;

                                // Check for tool calls
                                const toolCall = parseToolCall(botContent);
                                if (toolCall && !usedTools.find(t => t.tool === toolCall.tool)) {
                                    setCurrentTool(toolCall);
                                    usedTools.push(toolCall);
                                    setToolHistory([...usedTools]);
                                }

                                setMessages(prev => {
                                    const newMsgs = [...prev];
                                    newMsgs[newMsgs.length - 1].content = botContent;
                                    newMsgs[newMsgs.length - 1].toolsUsed = usedTools;
                                    return newMsgs;
                                });
                            } else if (data.audio_url) {
                                playAudio(data.audio_url);
                            }
                        } catch (e) {
                            // Skip parse errors
                        }
                    }
                }
            }

            // Mark streaming as complete
            setMessages(prev => {
                const newMsgs = [...prev];
                newMsgs[newMsgs.length - 1].isStreaming = false;
                return newMsgs;
            });

        } catch (error) {
            setMessages(prev => {
                const newMsgs = [...prev];
                newMsgs[newMsgs.length - 1].content = `⚠️ Connection error. Please try again.`;
                newMsgs[newMsgs.length - 1].isError = true;
                newMsgs[newMsgs.length - 1].isStreaming = false;
                return newMsgs;
            });
        } finally {
            setIsLoading(false);
            setIsStreaming(false);
            setCurrentTool(null);
        }
    };

    const handleKeyPress = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    // Clean tool syntax from displayed content
    const cleanContent = (content) => {
        if (!content) return '';
        // Remove [TOOL: args] patterns from display
        return content.replace(/\[([A-Z_]+):\s*[^\]]+\]/g, '').trim();
    };

    // Custom markdown components for styling
    const MarkdownComponents = {
        h1: ({ children }) => <h1 className="text-2xl font-bold text-white mb-4 mt-2">{children}</h1>,
        h2: ({ children }) => <h2 className="text-xl font-semibold text-white mb-3 mt-4">{children}</h2>,
        h3: ({ children }) => <h3 className="text-lg font-semibold text-teal-300 mb-2 mt-3">{children}</h3>,
        p: ({ children }) => <p className="text-slate-300 leading-relaxed mb-3 last:mb-0">{children}</p>,
        ul: ({ children }) => <ul className="space-y-2 mb-4">{children}</ul>,
        ol: ({ children }) => <ol className="list-decimal list-inside space-y-2 mb-4 text-slate-300">{children}</ol>,
        li: ({ children }) => (
            <li className="flex items-start gap-2 text-slate-300">
                <span className="text-teal-400 mt-1">•</span>
                <span>{children}</span>
            </li>
        ),
        strong: ({ children }) => <strong className="font-semibold text-white">{children}</strong>,
        em: ({ children }) => <em className="text-slate-400 italic">{children}</em>,
        code: ({ inline, children }) =>
            inline ? (
                <code className="px-1.5 py-0.5 bg-slate-800 text-teal-300 rounded text-sm font-mono">{children}</code>
            ) : (
                <pre className="bg-slate-800/80 rounded-lg p-4 overflow-x-auto mb-4">
                    <code className="text-sm text-slate-300 font-mono">{children}</code>
                </pre>
            ),
        a: ({ href, children }) => (
            <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="text-teal-400 hover:text-teal-300 underline underline-offset-2 transition-colors"
            >
                {children}
            </a>
        ),
        blockquote: ({ children }) => (
            <blockquote className="border-l-2 border-teal-500 pl-4 my-4 text-slate-400 italic">
                {children}
            </blockquote>
        ),
        hr: () => <hr className="border-slate-700 my-6" />,
    };

    // Render tool indicator pill
    const ToolIndicator = ({ tool, isActive }) => {
        const config = TOOL_CONFIG[tool.tool] || { icon: Zap, label: 'Processing...', color: 'text-slate-400', bg: 'bg-slate-500/10' };
        const Icon = config.icon;

        return (
            <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-sm ${config.bg} ${config.color} ${isActive ? 'animate-pulse' : 'opacity-70'}`}>
                {isActive ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                    <Icon className="w-3.5 h-3.5" />
                )}
                <span className="font-medium">{config.label}</span>
            </div>
        );
    };

    return (
        <div className={`flex h-[calc(100vh-4rem)] bg-gradient-to-br ${AEGIS_THEME.background} text-white overflow-hidden`}>
            {/* Ambient background effects */}
            <div className="fixed inset-0 pointer-events-none overflow-hidden">
                <div className="absolute top-0 left-1/4 w-96 h-96 bg-teal-500/5 rounded-full blur-3xl animate-pulse" style={{ animationDuration: '4s' }} />
                <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-cyan-500/5 rounded-full blur-3xl animate-pulse" style={{ animationDuration: '6s' }} />
                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[800px] bg-gradient-radial from-teal-500/3 to-transparent rounded-full" />
            </div>

            {/* Sidebar */}
            <div className={`${isSidebarOpen ? 'w-72' : 'w-0'} ${AEGIS_THEME.surface} backdrop-blur-xl border-r ${AEGIS_THEME.border} transition-all duration-300 flex flex-col overflow-hidden relative z-10`}>
                {/* Sidebar Header */}
                <div className="p-4 border-b border-slate-800/50">
                    <button
                        onClick={createNewSession}
                        className={`w-full flex items-center justify-center gap-2 bg-gradient-to-r ${AEGIS_THEME.primary} hover:opacity-90 text-white p-3 rounded-xl transition-all shadow-lg ${AEGIS_THEME.glow} hover:shadow-teal-500/30`}
                    >
                        <Plus className="w-5 h-5" />
                        <span className="font-semibold">New Conversation</span>
                    </button>
                </div>

                {/* Session List */}
                <div className="flex-1 overflow-y-auto p-3 space-y-1">
                    {sessions.length === 0 ? (
                        <div className="text-center py-8 text-slate-500">
                            <MessageSquare className="w-8 h-8 mx-auto mb-2 opacity-50" />
                            <p className="text-sm">No conversations yet</p>
                        </div>
                    ) : (
                        sessions.map(session => (
                            <div
                                key={session.id}
                                onClick={() => loadSession(session.id)}
                                className={`group flex items-center justify-between p-3 rounded-xl cursor-pointer transition-all duration-200 ${currentSessionId === session.id
                                    ? 'bg-teal-500/20 text-white border border-teal-500/30'
                                    : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200'
                                    }`}
                            >
                                <div className="flex items-center gap-3 overflow-hidden">
                                    <div className={`p-1.5 rounded-lg ${currentSessionId === session.id ? 'bg-teal-500/20' : 'bg-slate-800'}`}>
                                        <MessageSquare className="w-4 h-4" />
                                    </div>
                                    <span className="truncate text-sm font-medium">{session.title || "Untitled"}</span>
                                </div>
                                <button
                                    onClick={(e) => deleteSession(e, session.id)}
                                    className="opacity-0 group-hover:opacity-100 p-1.5 hover:bg-red-500/20 hover:text-red-400 rounded-lg transition-all"
                                >
                                    <Trash2 className="w-4 h-4" />
                                </button>
                            </div>
                        ))
                    )}
                </div>

                {/* Sidebar Footer */}
                <div className="p-4 border-t border-slate-800/50">
                    <div className="flex items-center gap-3 p-3 rounded-xl bg-slate-800/30">
                        <div className={`p-2 bg-gradient-to-r ${AEGIS_THEME.primary} rounded-lg`}>
                            <Shield className="w-4 h-4 text-white" />
                        </div>
                        <div>
                            <p className="text-sm font-medium text-slate-300">AEGIS Sentinel</p>
                            <p className="text-xs text-slate-500">AI Health Assistant</p>
                        </div>
                    </div>
                </div>
            </div>

            {/* Main Chat Area */}
            <div className="flex-1 flex flex-col h-full relative z-10">
                {/* Header */}
                <div className="h-16 border-b border-slate-800/50 flex items-center justify-between px-6 bg-slate-900/80 backdrop-blur-xl">
                    <div className="flex items-center gap-4">
                        <button
                            onClick={() => setIsSidebarOpen(!isSidebarOpen)}
                            className="p-2 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-colors"
                        >
                            {isSidebarOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
                        </button>
                        <div className="flex items-center gap-3">
                            <div className="relative">
                                <div className={`p-2.5 bg-gradient-to-br ${AEGIS_THEME.primary} rounded-xl shadow-lg ${AEGIS_THEME.glow}`}>
                                    <Stethoscope className="w-5 h-5 text-white" />
                                </div>
                                <span className="absolute -bottom-0.5 -right-0.5 w-3 h-3 bg-emerald-500 rounded-full border-2 border-slate-900 animate-pulse" />
                            </div>
                            <div>
                                <h1 className="font-bold text-white tracking-tight">Sentinel</h1>
                                <div className="flex items-center gap-2">
                                    <span className="text-xs text-emerald-400 font-medium">Online</span>
                                    {isStreaming && (
                                        <span className="flex items-center gap-1 text-xs text-teal-400">
                                            <Loader2 className="w-3 h-3 animate-spin" />
                                            Processing
                                        </span>
                                    )}
                                </div>
                            </div>

                            {/* Voice Mode Toggle */}
                            <button
                                onClick={() => setVoiceMode(!voiceMode)}
                                className={`ml-2 p-2 rounded-lg transition-all ${voiceMode ? 'bg-teal-500/20 text-teal-400' : 'text-slate-500 hover:text-slate-300'}`}
                                title={voiceMode ? "Voice Mode On" : "Voice Mode Off"}
                            >
                                {voiceMode ? <Volume2 className="w-4 h-4" /> : <VolumeX className="w-4 h-4" />}
                            </button>
                        </div>
                    </div>

                    {/* Active Tool Indicator */}
                    {currentTool && (
                        <ToolIndicator tool={currentTool} isActive={true} />
                    )}
                </div>

                {/* Messages Area */}
                <div className="flex-1 overflow-y-auto relative">
                    <div className="max-w-4xl mx-auto px-4 py-6 space-y-6">
                        {messages.length === 0 && (
                            <div className="h-full flex flex-col items-center justify-center text-center py-20 animate-fadeIn">
                                <div className={`p-6 bg-gradient-to-br ${AEGIS_THEME.primary} rounded-3xl shadow-2xl ${AEGIS_THEME.glow} mb-6`}>
                                    <Shield className="w-16 h-16 text-white" />
                                </div>
                                <h2 className="text-2xl font-bold text-white mb-2">Welcome to AEGIS</h2>
                                <p className="text-slate-400 mb-6 max-w-md">
                                    Your advanced AI guardian for personalized health intelligence and support.
                                </p>
                                <button
                                    onClick={createNewSession}
                                    className={`flex items-center gap-2 px-6 py-3 bg-gradient-to-r ${AEGIS_THEME.primary} text-white rounded-xl font-medium transition-all shadow-lg ${AEGIS_THEME.glow} hover:shadow-teal-500/40 hover:-translate-y-0.5`}
                                >
                                    <Plus className="w-5 h-5" />
                                    Start New Chat
                                </button>
                            </div>
                        )}

                        {messages.map((msg, idx) => {
                            // Skip empty assistant messages (they're placeholders for loading)
                            if (msg.role === 'assistant' && !msg.content && msg.isStreaming) {
                                return null;
                            }

                            return (
                                <div
                                    key={idx}
                                    className={`animate-fadeIn ${msg.role === 'user' ? 'flex justify-end' : ''}`}
                                    style={{ animationDelay: `${Math.min(idx * 30, 200)}ms` }}
                                >
                                    {msg.role === 'user' ? (
                                        // User Message - Right aligned, minimal
                                        <div className="max-w-[85%] md:max-w-[70%]">
                                            <div className="bg-gradient-to-r from-teal-600 to-cyan-600 text-white px-5 py-3 rounded-2xl rounded-br-md shadow-lg">
                                                <p className="text-sm leading-relaxed whitespace-pre-wrap">{msg.content}</p>
                                            </div>
                                            <div className="flex justify-end mt-1.5 pr-1">
                                                <span className="text-xs text-slate-500">
                                                    {msg.timestamp && new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                                                </span>
                                            </div>
                                        </div>
                                    ) : (
                                        // Assistant Message - Full width, clean
                                        <div className="w-full">
                                            {/* Tools used indicator */}
                                            {msg.toolsUsed && msg.toolsUsed.length > 0 && (
                                                <div className="flex flex-wrap gap-2 mb-3">
                                                    {msg.toolsUsed.map((tool, tidx) => (
                                                        <ToolIndicator key={tidx} tool={tool} isActive={msg.isStreaming && tidx === msg.toolsUsed.length - 1} />
                                                    ))}
                                                </div>
                                            )}

                                            {/* Message content */}
                                            <div className={`group relative ${msg.isError ? 'bg-red-500/10 border border-red-500/20 rounded-xl p-4' : ''}`}>
                                                {msg.isError ? (
                                                    <div className="flex items-center gap-3 text-red-400">
                                                        <AlertTriangle className="w-5 h-5" />
                                                        <span>{msg.content}</span>
                                                    </div>
                                                ) : (
                                                    <div className="prose prose-invert prose-sm max-w-none">
                                                        <ReactMarkdown
                                                            remarkPlugins={[remarkGfm]}
                                                            components={MarkdownComponents}
                                                        >
                                                            {cleanContent(msg.content)}
                                                        </ReactMarkdown>
                                                    </div>
                                                )}

                                                {/* Streaming cursor */}
                                                {msg.isStreaming && (
                                                    <span className="inline-block w-2 h-5 bg-teal-400 ml-1 animate-pulse rounded-sm" />
                                                )}

                                                {/* Map button */}
                                                {!msg.isStreaming && hasLocationData(msg.content) && (
                                                    <button
                                                        onClick={() => toggleMap(idx)}
                                                        className="mt-4 flex items-center gap-2 px-4 py-2 bg-teal-500/10 hover:bg-teal-500/20 border border-teal-500/30 rounded-lg text-teal-400 text-sm transition-all"
                                                    >
                                                        <Map className="w-4 h-4" />
                                                        {visibleMaps[idx] ? 'Hide Map' : 'Show on Map'}
                                                    </button>
                                                )}

                                                {/* Map View */}
                                                {visibleMaps[idx] && hasLocationData(msg.content) && (
                                                    <div className="mt-4 rounded-xl overflow-hidden border border-slate-700">
                                                        <MapView
                                                            content={msg.content}
                                                            onClose={() => toggleMap(idx)}
                                                            userLocation={userLocation}
                                                        />
                                                    </div>
                                                )}

                                                {/* Copy button */}
                                                {!msg.isStreaming && msg.content && (
                                                    <div className="absolute -right-2 top-0 opacity-0 group-hover:opacity-100 transition-opacity">
                                                        <button
                                                            onClick={() => copyToClipboard(cleanContent(msg.content), idx)}
                                                            className="p-2 text-slate-500 hover:text-white hover:bg-slate-800 rounded-lg transition-colors"
                                                        >
                                                            {copiedIndex === idx ? (
                                                                <Check className="w-4 h-4 text-emerald-400" />
                                                            ) : (
                                                                <Copy className="w-4 h-4" />
                                                            )}
                                                        </button>
                                                    </div>
                                                )}
                                            </div>

                                            {/* Timestamp */}
                                            {!msg.isStreaming && msg.timestamp && (
                                                <div className="mt-2">
                                                    <span className="text-xs text-slate-500">
                                                        {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                                                    </span>
                                                </div>
                                            )}
                                        </div>
                                    )}
                                </div>
                            );
                        })}

                        {/* Thinking indicator - only show when loading with no content yet */}
                        {isLoading && messages.length > 0 && messages[messages.length - 1]?.content === '' && !currentTool && (
                            <div className="flex items-center gap-4 p-4 bg-slate-800/30 rounded-xl border border-slate-700/50 animate-fadeIn">
                                <div className="relative">
                                    <div className="w-10 h-10 rounded-full bg-gradient-to-r from-teal-500 to-cyan-500 animate-pulse flex items-center justify-center">
                                        <Brain className="w-5 h-5 text-white" />
                                    </div>
                                    <div className="absolute inset-0 rounded-full bg-gradient-to-r from-teal-500 to-cyan-500 animate-ping opacity-20" />
                                </div>
                                <div>
                                    <p className="text-white font-medium">Analyzing your request...</p>
                                    <p className="text-slate-400 text-sm">Sentinel is thinking</p>
                                </div>
                            </div>
                        )}

                        {/* Tool execution indicator */}
                        {isLoading && currentTool && messages[messages.length - 1]?.content === '' && (
                            <div className="flex items-center gap-4 p-4 bg-slate-800/30 rounded-xl border border-teal-500/30 animate-fadeIn">
                                <div className="relative">
                                    <div className={`w-10 h-10 rounded-full ${TOOL_CONFIG[currentTool.tool]?.bg || 'bg-teal-500/20'} flex items-center justify-center`}>
                                        {React.createElement(TOOL_CONFIG[currentTool.tool]?.icon || Zap, {
                                            className: `w-5 h-5 ${TOOL_CONFIG[currentTool.tool]?.color || 'text-teal-400'}`
                                        })}
                                    </div>
                                    <Loader2 className="absolute -top-1 -right-1 w-4 h-4 text-teal-400 animate-spin" />
                                </div>
                                <div className="flex-1">
                                    <p className="text-white font-medium">{TOOL_CONFIG[currentTool.tool]?.label || 'Processing...'}</p>
                                    <p className="text-slate-400 font-mono text-xs mt-0.5 truncate max-w-md">{currentTool.args}</p>
                                </div>
                            </div>
                        )}

                        <div ref={messagesEndRef} />
                    </div>
                </div>

                {/* Camera Modal */}
                {isCameraOpen && (
                    <div className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4">
                        <div className="bg-gray-900 rounded-2xl p-6 max-w-2xl w-full border border-gray-700">
                            <div className="flex justify-between items-center mb-4">
                                <h3 className="text-xl font-semibold text-white">Scan & Analyze</h3>
                                <div className="flex items-center gap-2">
                                    {devices.length > 1 && !capturedImage && (
                                        <select
                                            value={selectedDeviceId}
                                            onChange={handleDeviceChange}
                                            className="bg-slate-800 text-white text-sm rounded-lg border border-slate-700 p-2 outline-none focus:border-teal-500"
                                        >
                                            {devices.map(device => (
                                                <option key={device.deviceId} value={device.deviceId}>
                                                    {device.label || `Camera ${devices.indexOf(device) + 1}`}
                                                </option>
                                            ))}
                                        </select>
                                    )}
                                    <button onClick={stopCamera} className="text-gray-400 hover:text-white">
                                        <X size={24} />
                                    </button>
                                </div>
                            </div>

                            <div className="relative aspect-video bg-black rounded-lg overflow-hidden mb-4 border border-gray-700">
                                {!capturedImage ? (
                                    <video
                                        ref={videoRef}
                                        autoPlay
                                        playsInline
                                        className="w-full h-full object-cover"
                                    />
                                ) : (
                                    <img
                                        src={capturedImage}
                                        alt="Captured"
                                        className="w-full h-full object-contain"
                                    />
                                )}
                                <canvas ref={canvasRef} width="640" height="480" className="hidden" />
                            </div>

                            <div className="flex justify-center gap-4">
                                {!capturedImage ? (
                                    <button
                                        onClick={captureImage}
                                        className="bg-white text-black px-6 py-3 rounded-full font-bold hover:bg-gray-200 transition-colors flex items-center gap-2"
                                    >
                                        <Camera size={20} /> Capture
                                    </button>
                                ) : (
                                    <>
                                        <button
                                            onClick={() => {
                                                setCapturedImage(null);
                                                startCamera();
                                            }}
                                            className="bg-gray-700 text-white px-6 py-3 rounded-full font-medium hover:bg-gray-600 transition-colors"
                                        >
                                            Retake
                                        </button>
                                        <button
                                            onClick={sendImageAnalysis}
                                            className="bg-teal-500 text-white px-6 py-3 rounded-full font-bold hover:bg-teal-400 transition-colors flex items-center gap-2"
                                        >
                                            <Send size={20} /> Analyze
                                        </button>
                                    </>
                                )}
                            </div>
                        </div>
                    </div>
                )}

                {/* Input Area */}
                <div className="p-4 bg-slate-900/80 backdrop-blur-xl border-t border-slate-800/50">
                    <div className="max-w-4xl mx-auto">
                        <div className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-2 flex items-center gap-2 shadow-xl backdrop-blur-sm focus-within:border-teal-500/50 focus-within:shadow-teal-500/10 transition-all">
                            {/* Camera Button */}
                            <button
                                onClick={startCamera}
                                className="p-3 text-gray-400 hover:text-teal-400 transition-colors rounded-full hover:bg-gray-700/50"
                                title="Scan Image"
                            >
                                <Camera size={20} />
                            </button>

                            {/* Voice Button */}
                            <button
                                onClick={toggleListening}
                                className={`p-2.5 rounded-xl transition-colors ${isListening
                                    ? 'bg-red-500/20 text-red-400 animate-pulse'
                                    : 'text-slate-500 hover:text-teal-400 hover:bg-slate-700/50'
                                    }`}
                                title="Voice Input"
                            >
                                <Mic className={`w-5 h-5 ${isListening ? 'animate-bounce' : ''}`} />
                            </button>

                            {/* Text Input */}
                            <input
                                ref={inputRef}
                                type="text"
                                value={input}
                                onChange={(e) => setInput(e.target.value)}
                                onKeyPress={handleKeyPress}
                                placeholder="Ask about your health, medications, or find care..."
                                className="flex-1 bg-transparent border-none outline-none text-white placeholder-slate-500 px-2 text-sm"
                                disabled={isLoading}
                            />

                            {/* Send Button */}
                            <button
                                onClick={handleSend}
                                disabled={isLoading || !input.trim()}
                                className={`p-2.5 rounded-xl transition-all duration-200 ${input.trim()
                                    ? `bg-gradient-to-r ${AEGIS_THEME.primary} hover:opacity-90 text-white shadow-lg ${AEGIS_THEME.glow} hover:shadow-teal-500/40`
                                    : 'bg-slate-700/50 text-slate-500 cursor-not-allowed'
                                    }`}
                            >
                                {isLoading ? (
                                    <Loader2 className="w-5 h-5 animate-spin" />
                                ) : (
                                    <Send className="w-5 h-5" />
                                )}
                            </button>
                        </div>

                        {/* Disclaimer */}
                        <p className="text-center text-xs text-slate-600 mt-3">
                            AEGIS provides health assistance. Always consult healthcare professionals for medical decisions.
                        </p>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default ChatInterface;
