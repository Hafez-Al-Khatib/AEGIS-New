import { useEffect, useState } from 'react';
import { getVitals } from '../api';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area } from 'recharts';
import { 
    Activity, 
    Heart, 
    Droplets, 
    Shield, 
    AlertTriangle, 
    TrendingUp, 
    TrendingDown,
    Clock,
    Zap,
    ThermometerSun,
    Waves,
    RefreshCw
} from 'lucide-react';

// Advanced Agent Components
import HealthGoals from './HealthGoals';
import WeeklyBriefing from './WeeklyBriefing';
import MedicationSafetyChecker from './MedicationSafetyChecker';
import ContactsList from './ContactsList';

export default function Dashboard() {
    const [vitals, setVitals] = useState([]);
    const [latest, setLatest] = useState({ heart_rate: '--', spo2: '--' });
    const [loading, setLoading] = useState(true);
    const [lastUpdate, setLastUpdate] = useState(null);

    // Fetch data every 5 seconds
    useEffect(() => {
        const fetchData = async () => {
            try {
                const data = await getVitals();
                console.log("Raw vitals data:", data); // Debug
                
                if (!data || data.length === 0) {
                    console.log("No vitals data returned");
                    setLoading(false);
                    return;
                }
                
                const formattedData = data.map(d => ({
                    ...d,
                    time: d.time || d.timestamp,
                    timeStr: new Date(d.time || d.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
                })).sort((a, b) => new Date(a.time) - new Date(b.time));
                
                console.log("Formatted vitals:", formattedData.slice(0, 3)); // Debug first 3
                
                setVitals(formattedData);
                if (formattedData.length > 0) {
                    setLatest(formattedData[formattedData.length - 1]);
                }
                setLastUpdate(new Date());
                setLoading(false);
            } catch (error) {
                console.error("Failed to fetch vitals", error);
                setLoading(false);
            }
        };

        fetchData();
        const interval = setInterval(fetchData, 5000);
        return () => clearInterval(interval);
    }, []);

    // Determine vital status
    const getHeartRateStatus = (hr) => {
        if (hr === '--') return { status: 'unknown', color: 'slate' };
        const val = parseInt(hr);
        if (val < 60) return { status: 'Low', color: 'amber', icon: TrendingDown };
        if (val > 100) return { status: 'Elevated', color: 'rose', icon: TrendingUp };
        return { status: 'Normal', color: 'emerald', icon: Activity };
    };

    const getSpO2Status = (spo2) => {
        if (spo2 === '--') return { status: 'unknown', color: 'slate' };
        const val = parseInt(spo2);
        if (val < 95) return { status: 'Low', color: 'rose', icon: AlertTriangle };
        return { status: 'Optimal', color: 'emerald', icon: Activity };
    };

    const hrStatus = getHeartRateStatus(latest.heart_rate);
    const spo2Status = getSpO2Status(latest.spo2);

    const StatCard = ({ title, value, unit, icon: Icon, gradient, status, statusColor, statusIcon: StatusIcon, trend }) => (
        <div className="card group relative overflow-hidden">
            {/* Gradient Background */}
            <div className={`absolute inset-0 bg-gradient-to-br ${gradient} opacity-0 group-hover:opacity-5 transition-opacity duration-500`} />
            
            {/* Decorative Icon */}
            <div className="absolute -top-4 -right-4 opacity-5 group-hover:opacity-10 transition-opacity duration-500">
                <Icon size={100} strokeWidth={1} />
            </div>
            
            <div className="relative z-10">
                {/* Header */}
                <div className="flex items-center justify-between mb-4">
                    <div className={`p-3 rounded-xl bg-gradient-to-br ${gradient} shadow-lg`}>
                        <Icon className="w-6 h-6 text-white" />
                    </div>
                    {status && status !== 'unknown' && (
                        <div className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-${statusColor}-100 text-${statusColor}-700`}>
                            {StatusIcon && <StatusIcon className="w-3 h-3" />}
                            {status}
                        </div>
                    )}
                </div>
                
                {/* Value */}
                <div className="mb-1">
                    <p className="text-sm font-medium text-slate-500 mb-1">{title}</p>
                    <div className="flex items-baseline gap-2">
                        <span className="text-4xl font-bold text-slate-900">{value}</span>
                        <span className="text-lg font-medium text-slate-400">{unit}</span>
                    </div>
                </div>
                
                {/* Trend Indicator */}
                {trend && (
                    <div className="mt-4 pt-4 border-t border-slate-100 flex items-center gap-2">
                        <div className={`p-1 rounded bg-${trend.color}-100`}>
                            {trend.direction === 'up' ? (
                                <TrendingUp className={`w-4 h-4 text-${trend.color}-600`} />
                            ) : (
                                <TrendingDown className={`w-4 h-4 text-${trend.color}-600`} />
                            )}
                        </div>
                        <span className="text-sm text-slate-600">{trend.text}</span>
                    </div>
                )}
            </div>
        </div>
    );

    return (
        <div className="p-6 lg:p-8 max-w-7xl mx-auto space-y-8 animate-fadeIn">
            {/* Header */}
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                <div>
                    <h1 className="text-3xl lg:text-4xl font-bold text-slate-900 tracking-tight">
                        Live Monitor
                    </h1>
                    <p className="text-slate-500 mt-1 flex items-center gap-2">
                        Real-time patient telemetry
                        {lastUpdate && (
                            <span className="text-xs text-slate-400 flex items-center gap-1">
                                <Clock className="w-3 h-3" />
                                Updated {lastUpdate.toLocaleTimeString()}
                            </span>
                        )}
                    </p>
                </div>
                <div className="flex gap-3">
                    <a 
                        href="/chat" 
                        className="flex items-center gap-2 px-5 py-2.5 bg-gradient-to-r from-teal-500 to-cyan-500 hover:from-teal-400 hover:to-cyan-400 text-white rounded-xl text-sm font-semibold transition-all shadow-lg shadow-teal-500/25 hover:shadow-teal-500/40 hover:-translate-y-0.5"
                    >
                        <Zap className="w-4 h-4" />
                        Ask Sentinel
                    </a>
                    <div className="flex items-center gap-2 px-4 py-2.5 bg-emerald-50 text-emerald-700 rounded-xl text-sm font-semibold border border-emerald-200">
                        <div className="relative">
                            <div className="w-2 h-2 bg-emerald-500 rounded-full" />
                            <div className="absolute inset-0 w-2 h-2 bg-emerald-500 rounded-full animate-ping" />
                        </div>
                        System Online
                    </div>
                </div>
            </div>

            {/* Vital Signs Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
                <StatCard
                    title="Heart Rate"
                    value={latest.heart_rate}
                    unit="bpm"
                    icon={Heart}
                    gradient="from-rose-500 to-pink-600"
                    status={hrStatus.status}
                    statusColor={hrStatus.color}
                    statusIcon={hrStatus.icon}
                />
                <StatCard
                    title="Blood Oxygen"
                    value={latest.spo2}
                    unit="%"
                    icon={Droplets}
                    gradient="from-cyan-500 to-blue-600"
                    status={spo2Status.status}
                    statusColor={spo2Status.color}
                    statusIcon={spo2Status.icon}
                />
                <StatCard
                    title="Sentinel Status"
                    value="Active"
                    unit=""
                    icon={Shield}
                    gradient="from-emerald-500 to-teal-600"
                    status="Monitoring"
                    statusColor="emerald"
                    statusIcon={Activity}
                />
                <StatCard
                    title="Risk Level"
                    value="Low"
                    unit=""
                    icon={AlertTriangle}
                    gradient="from-amber-500 to-orange-600"
                    status="Normal"
                    statusColor="emerald"
                    statusIcon={Activity}
                />
            </div>

            {/* Chart Section */}
            <div className="card p-6 lg:p-8">
                <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
                    <div>
                        <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
                            <Activity className="w-5 h-5 text-teal-600" />
                            Biometric Trends
                        </h2>
                        <p className="text-sm text-slate-500 mt-1">Real-time monitoring over the last hour</p>
                    </div>
                    <div className="flex items-center gap-4">
                        <div className="flex items-center gap-2">
                            <div className="w-3 h-3 rounded-full bg-gradient-to-r from-rose-500 to-pink-500" />
                            <span className="text-sm font-medium text-slate-600">Heart Rate</span>
                        </div>
                        <div className="flex items-center gap-2">
                            <div className="w-3 h-3 rounded-full bg-gradient-to-r from-cyan-500 to-blue-500" />
                            <span className="text-sm font-medium text-slate-600">SpO2</span>
                        </div>
                        <button className="p-2 hover:bg-slate-100 rounded-lg transition-colors text-slate-500">
                            <RefreshCw className="w-4 h-4" />
                        </button>
                    </div>
                </div>

                <div className="h-[400px] w-full">
                    {loading ? (
                        <div className="h-full flex items-center justify-center">
                            <div className="flex flex-col items-center gap-3">
                                <div className="w-10 h-10 border-4 border-teal-200 border-t-teal-600 rounded-full animate-spin" />
                                <p className="text-sm text-slate-500">Loading vitals data...</p>
                            </div>
                        </div>
                    ) : vitals.length === 0 ? (
                        <div className="h-full flex items-center justify-center">
                            <div className="text-center">
                                <Waves className="w-12 h-12 text-slate-300 mx-auto mb-3" />
                                <p className="text-slate-500">No vitals data available</p>
                                <p className="text-sm text-slate-400 mt-1">Connect a monitoring device to start</p>
                            </div>
                        </div>
                    ) : (
                        <ResponsiveContainer width="100%" height="100%">
                            <AreaChart data={vitals} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                                <defs>
                                    <linearGradient id="colorHr" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="5%" stopColor="#f43f5e" stopOpacity={0.3} />
                                        <stop offset="95%" stopColor="#f43f5e" stopOpacity={0} />
                                    </linearGradient>
                                    <linearGradient id="colorSpo2" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="5%" stopColor="#0ea5e9" stopOpacity={0.3} />
                                        <stop offset="95%" stopColor="#0ea5e9" stopOpacity={0} />
                                    </linearGradient>
                                </defs>
                                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                                <XAxis
                                    dataKey="timeStr"
                                    stroke="#94a3b8"
                                    fontSize={11}
                                    tickLine={false}
                                    axisLine={false}
                                />
                                <YAxis
                                    domain={[40, 140]}
                                    stroke="#94a3b8"
                                    fontSize={11}
                                    tickLine={false}
                                    axisLine={false}
                                    width={40}
                                />
                                <Tooltip
                                    contentStyle={{
                                        backgroundColor: 'rgba(255, 255, 255, 0.95)',
                                        borderRadius: '12px',
                                        border: '1px solid #e2e8f0',
                                        boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.1)',
                                        padding: '12px'
                                    }}
                                    labelStyle={{ fontWeight: 600, marginBottom: '4px' }}
                                />
                                <Area
                                    type="monotone"
                                    dataKey="heart_rate"
                                    stroke="#f43f5e"
                                    strokeWidth={2.5}
                                    fillOpacity={1}
                                    fill="url(#colorHr)"
                                    name="Heart Rate"
                                />
                                <Area
                                    type="monotone"
                                    dataKey="spo2"
                                    stroke="#0ea5e9"
                                    strokeWidth={2.5}
                                    fillOpacity={1}
                                    fill="url(#colorSpo2)"
                                    name="SpO2"
                                />
                            </AreaChart>
                        </ResponsiveContainer>
                    )}
                </div>
            </div>

            {/* Advanced Agents Section */}
            <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-4 gap-6">
                <WeeklyBriefing />
                <HealthGoals />
                <MedicationSafetyChecker />
                <ContactsList />
            </div>

            {/* Quick Actions */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <a href="/analyze" className="card p-4 flex items-center gap-3 hover:border-blue-200 cursor-pointer group">
                    <div className="p-2.5 bg-blue-100 rounded-xl group-hover:bg-blue-200 transition-colors">
                        <ThermometerSun className="w-5 h-5 text-blue-600" />
                    </div>
                    <div>
                        <p className="font-semibold text-slate-800">Analyze Record</p>
                        <p className="text-xs text-slate-500">Upload documents</p>
                    </div>
                </a>
                <a href="/chat" className="card p-4 flex items-center gap-3 hover:border-indigo-200 cursor-pointer group">
                    <div className="p-2.5 bg-indigo-100 rounded-xl group-hover:bg-indigo-200 transition-colors">
                        <Zap className="w-5 h-5 text-indigo-600" />
                    </div>
                    <div>
                        <p className="font-semibold text-slate-800">Chat with AI</p>
                        <p className="text-xs text-slate-500">Ask questions</p>
                    </div>
                </a>
                <div className="card p-4 flex items-center gap-3 hover:border-emerald-200 cursor-pointer group">
                    <div className="p-2.5 bg-emerald-100 rounded-xl group-hover:bg-emerald-200 transition-colors">
                        <Activity className="w-5 h-5 text-emerald-600" />
                    </div>
                    <div>
                        <p className="font-semibold text-slate-800">Health Report</p>
                        <p className="text-xs text-slate-500">View summary</p>
                    </div>
                </div>
                <div className="card p-4 flex items-center gap-3 hover:border-rose-200 cursor-pointer group">
                    <div className="p-2.5 bg-rose-100 rounded-xl group-hover:bg-rose-200 transition-colors">
                        <AlertTriangle className="w-5 h-5 text-rose-600" />
                    </div>
                    <div>
                        <p className="font-semibold text-slate-800">Emergency</p>
                        <p className="text-xs text-slate-500">Get help now</p>
                    </div>
                </div>
            </div>
        </div>
    );
}