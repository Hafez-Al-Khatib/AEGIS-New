import { useState, useEffect } from 'react';
import { getWeeklyBriefing } from '../api';
import { 
    Calendar, 
    RefreshCw, 
    Loader2,
    TrendingUp,
    Sun
} from 'lucide-react';

export default function WeeklyBriefing() {
    const [briefing, setBriefing] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        fetchBriefing();
    }, []);

    const fetchBriefing = async () => {
        setLoading(true);
        setError(null);
        try {
            const data = await getWeeklyBriefing();
            setBriefing(data);
        } catch (err) {
            setError('Unable to load briefing');
            console.error('Error fetching briefing:', err);
        } finally {
            setLoading(false);
        }
    };

    // Parse markdown-style text to clean display
    const parseText = (text) => {
        if (!text) return text;
        // Convert **bold** to styled spans
        return text
            .replace(/\*\*([^*]+)\*\*/g, '<strong class="font-semibold text-slate-800">$1</strong>')
            .replace(/\*([^*]+)\*/g, '<em class="text-amber-700">$1</em>');
    };

    // Parse the briefing text into structured sections
    const parseBriefing = (text) => {
        if (!text) return { title: '', items: [], closing: '' };
        
        const lines = text.split('\n').filter(l => l.trim());
        const result = { title: '', items: [], closing: '' };
        
        lines.forEach(line => {
            const trimmed = line.trim();
            // Match headers like "## Monday Morning Briefing" or lines with "Week of"
            if (trimmed.match(/^#+\s/) || trimmed.includes('Morning Briefing') || trimmed.includes('Week of')) {
                result.title = trimmed.replace(/^#+\s*/, '').replace(/\*\*/g, '').replace(/-\s*/, '').trim();
            } 
            // Match bullet points: *, -, •, or numbered (1., 2.)
            else if (trimmed.match(/^\*\s+\*\*/) || trimmed.match(/^\d+\.|^[-•]\s/)) {
                // Extract content after bullet marker
                const content = trimmed
                    .replace(/^\*\s+/, '')  // Remove leading * 
                    .replace(/^\d+\.\s*/, '')  // Remove numbered bullets
                    .replace(/^[-•]\s*/, '');  // Remove dash/dot bullets
                result.items.push(content);
            }
            // Match closing italics like *Keep up the great work!*
            else if (trimmed.match(/^\*[^*]+\*$/) && !trimmed.includes('**')) {
                result.closing = trimmed.replace(/^\*|\*$/g, '');
            }
        });
        
        return result;
    };

    const parsed = briefing ? parseBriefing(briefing.briefing) : null;

    // Get icon for item type
    const getItemIcon = (text) => {
        const lower = text.toLowerCase();
        if (lower.includes('sleep')) return '😴';
        if (lower.includes('heart') || lower.includes('cardio')) return '❤️';
        if (lower.includes('medication') || lower.includes('missed')) return '💊';
        if (lower.includes('exercise') || lower.includes('walk') || lower.includes('step')) return '🏃';
        if (lower.includes('water') || lower.includes('hydrat')) return '💧';
        if (lower.includes('stress')) return '🧘';
        return '📌';
    };

    return (
        <div className="card p-6 space-y-4">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <div className="p-2 rounded-xl bg-amber-100">
                        <Sun className="w-5 h-5 text-amber-600" />
                    </div>
                    <div>
                        <h3 className="font-semibold text-slate-800">Weekly Briefing</h3>
                        <p className="text-xs text-slate-400">Monday Morning Report</p>
                    </div>
                </div>
                <button
                    onClick={fetchBriefing}
                    disabled={loading}
                    className="p-2 rounded-lg hover:bg-slate-100 transition-colors disabled:opacity-50"
                >
                    <RefreshCw className={`w-5 h-5 text-slate-600 ${loading ? 'animate-spin' : ''}`} />
                </button>
            </div>

            {/* Content */}
            {loading ? (
                <div className="flex items-center justify-center py-8">
                    <Loader2 className="w-6 h-6 animate-spin text-amber-500" />
                </div>
            ) : error ? (
                <div className="text-center py-8">
                    <p className="text-sm text-slate-400">{error}</p>
                    <button
                        onClick={fetchBriefing}
                        className="mt-2 text-sm text-amber-600 hover:underline"
                    >
                        Try again
                    </button>
                </div>
            ) : parsed ? (
                <div className="space-y-4">
                    {/* Title Card */}
                    {parsed.title && (
                        <div className="flex items-center gap-2 px-4 py-3 rounded-xl bg-gradient-to-r from-amber-500 to-orange-500 text-white">
                            <Calendar className="w-5 h-5" />
                            <span className="font-semibold">{parsed.title}</span>
                        </div>
                    )}

                    {/* Items */}
                    <div className="space-y-3">
                        {parsed.items.map((item, idx) => {
                            const cleanItem = item.replace(/\*\*/g, '');
                            const [label, ...rest] = cleanItem.split(':');
                            const hasLabel = rest.length > 0;
                            
                            return (
                                <div 
                                    key={idx} 
                                    className="p-4 rounded-xl bg-slate-50 border border-slate-100 hover:border-amber-200 transition-colors"
                                >
                                    <div className="flex items-start gap-3">
                                        <span className="text-xl">{getItemIcon(cleanItem)}</span>
                                        <div className="flex-1">
                                            {hasLabel ? (
                                                <>
                                                    <p className="font-semibold text-slate-800 mb-1">{label}</p>
                                                    <p className="text-sm text-slate-600">{rest.join(':').trim()}</p>
                                                </>
                                            ) : (
                                                <p className="text-sm text-slate-700">{cleanItem}</p>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            );
                        })}
                    </div>

                    {/* Closing Message */}
                    {parsed.closing && (
                        <div className="text-center py-3 px-4 rounded-xl bg-emerald-50 border border-emerald-100">
                            <p className="text-sm font-medium text-emerald-700 flex items-center justify-center gap-2">
                                <span>✨</span>
                                {parsed.closing}
                                <span>✨</span>
                            </p>
                        </div>
                    )}

                    {/* Timestamp */}
                    {briefing.generated_at && (
                        <div className="flex items-center gap-2 text-xs text-slate-400 pt-2">
                            <Calendar className="w-3 h-3" />
                            <span>Generated: {new Date(briefing.generated_at).toLocaleString()}</span>
                        </div>
                    )}
                </div>
            ) : (
                <div className="text-center py-8">
                    <p className="text-sm text-slate-400">No briefing data available</p>
                </div>
            )}
        </div>
    );
}
