import { useState, useEffect } from 'react';
import { getHealthGoals, createHealthGoal, updateGoalProgress, awardXP } from '../api';
import { 
    Target, 
    Plus, 
    CheckCircle2, 
    Circle, 
    Trophy,
    Sparkles,
    Loader2,
    Salad,
    Dumbbell,
    Pill,
    Activity,
    Heart,
    Wand2,
    Info,
    AlertCircle,
    Clock
} from 'lucide-react';

export default function HealthGoals() {
    const [goals, setGoals] = useState([]);
    const [loading, setLoading] = useState(true);
    const [newGoal, setNewGoal] = useState('');
    const [showInput, setShowInput] = useState(false);
    const [xpMessage, setXpMessage] = useState(null);

    useEffect(() => {
        fetchGoals();
    }, []);

    const fetchGoals = async () => {
        try {
            const data = await getHealthGoals();
            setGoals(data);
        } catch (error) {
            console.error('Error fetching goals:', error);
        } finally {
            setLoading(false);
        }
    };

    const handleAddGoal = async () => {
        if (!newGoal.trim()) return;
        try {
            const goal = await createHealthGoal(newGoal);
            setGoals([goal, ...goals]);
            setNewGoal('');
            setShowInput(false);
        } catch (error) {
            console.error('Error creating goal:', error);
        }
    };

    const handleCompleteGoal = async (goal) => {
        try {
            await updateGoalProgress(goal.id, 100);
            // Award XP for completing the goal
            const xpResult = await awardXP(`Completed: ${goal.description}`);
            setXpMessage(xpResult.result);
            setTimeout(() => setXpMessage(null), 3000);
            fetchGoals();
        } catch (error) {
            console.error('Error completing goal:', error);
        }
    };

    const activeGoals = goals.filter(g => g.status === 'active');
    const completedGoals = goals.filter(g => g.status === 'completed');

    // Category icon mapping
    const getCategoryIcon = (category) => {
        switch (category) {
            case 'diet': return Salad;
            case 'exercise': return Dumbbell;
            case 'medication': return Pill;
            case 'monitoring': return Activity;
            case 'lifestyle': return Heart;
            default: return Target;
        }
    };

    // Priority color mapping
    const getPriorityColor = (priority) => {
        switch (priority) {
            case 'high': return 'bg-rose-100 text-rose-700 border-rose-200';
            case 'medium': return 'bg-amber-100 text-amber-700 border-amber-200';
            case 'low': return 'bg-emerald-100 text-emerald-700 border-emerald-200';
            default: return 'bg-slate-100 text-slate-700 border-slate-200';
        }
    };

    // Category color mapping
    const getCategoryColor = (category) => {
        switch (category) {
            case 'diet': return 'bg-green-100 text-green-600';
            case 'exercise': return 'bg-orange-100 text-orange-600';
            case 'medication': return 'bg-blue-100 text-blue-600';
            case 'monitoring': return 'bg-purple-100 text-purple-600';
            case 'lifestyle': return 'bg-pink-100 text-pink-600';
            default: return 'bg-slate-100 text-slate-600';
        }
    };

    if (loading) {
        return (
            <div className="card p-6 flex items-center justify-center">
                <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
            </div>
        );
    }

    return (
        <div className="card p-6 space-y-4">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <div className="p-2 rounded-xl bg-purple-100">
                        <Target className="w-5 h-5 text-purple-600" />
                    </div>
                    <div>
                        <h3 className="font-semibold text-slate-800">Health Goals</h3>
                        <p className="text-xs text-slate-500">{activeGoals.length} active</p>
                    </div>
                </div>
                <div className="flex gap-2">
                    <a 
                        href="/chat?prompt=Help me create a health plan"
                        className="p-2 rounded-lg bg-gradient-to-r from-purple-500 to-indigo-500 text-white hover:from-purple-600 hover:to-indigo-600 transition-all shadow-sm"
                        title="Generate AI Lifestyle Plan"
                    >
                        <Wand2 className="w-4 h-4" />
                    </a>
                    <button
                        onClick={() => setShowInput(!showInput)}
                        className="p-2 rounded-lg hover:bg-slate-100 transition-colors"
                    >
                        <Plus className="w-5 h-5 text-slate-600" />
                    </button>
                </div>
            </div>

            {/* XP Notification */}
            {xpMessage && (
                <div className="flex items-center gap-2 p-3 rounded-lg bg-amber-50 border border-amber-200 animate-pulse">
                    <Trophy className="w-5 h-5 text-amber-500" />
                    <span className="text-sm text-amber-700">{xpMessage}</span>
                    <Sparkles className="w-4 h-4 text-amber-400" />
                </div>
            )}

            {/* Add Goal Input */}
            {showInput && (
                <div className="flex gap-2">
                    <input
                        type="text"
                        value={newGoal}
                        onChange={(e) => setNewGoal(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && handleAddGoal()}
                        placeholder="e.g., Walk 10,000 steps daily"
                        className="flex-1 px-3 py-2 rounded-lg border border-slate-200 focus:border-purple-500 focus:ring-2 focus:ring-purple-500/20 outline-none text-sm"
                    />
                    <button
                        onClick={handleAddGoal}
                        className="px-4 py-2 rounded-lg bg-purple-500 text-white text-sm font-medium hover:bg-purple-600 transition-colors"
                    >
                        Add
                    </button>
                </div>
            )}

            {/* Active Goals */}
            <div className="space-y-3">
                {activeGoals.length === 0 ? (
                    <div className="text-center py-6">
                        <Target className="w-10 h-10 text-slate-200 mx-auto mb-2" />
                        <p className="text-sm text-slate-400">No active goals</p>
                        <a 
                            href="/chat?prompt=Help me create a health plan"
                            className="text-xs text-purple-500 hover:text-purple-600 mt-1 inline-block"
                        >
                            Let AI create goals for you →
                        </a>
                    </div>
                ) : (
                    activeGoals.map((goal) => {
                        const CategoryIcon = getCategoryIcon(goal.category);
                        return (
                            <div
                                key={goal.id}
                                className="p-3 rounded-xl border border-slate-100 hover:border-slate-200 bg-white hover:shadow-sm transition-all group"
                            >
                                {/* Top Row: Category + Priority + Complete */}
                                <div className="flex items-center justify-between mb-2">
                                    <div className="flex items-center gap-2">
                                        <div className={`p-1.5 rounded-lg ${getCategoryColor(goal.category)}`}>
                                            <CategoryIcon className="w-3.5 h-3.5" />
                                        </div>
                                        {goal.category && (
                                            <span className="text-xs font-medium text-slate-500 capitalize">
                                                {goal.category}
                                            </span>
                                        )}
                                    </div>
                                    <div className="flex items-center gap-2">
                                        {goal.priority && (
                                            <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${getPriorityColor(goal.priority)}`}>
                                                {goal.priority.toUpperCase()}
                                            </span>
                                        )}
                                        <button
                                            onClick={() => handleCompleteGoal(goal)}
                                            className="text-slate-300 hover:text-green-500 transition-colors"
                                            title="Mark complete"
                                        >
                                            <Circle className="w-5 h-5" />
                                        </button>
                                    </div>
                                </div>
                                
                                {/* Description */}
                                <p className="text-sm font-medium text-slate-700 mb-2">
                                    {goal.description}
                                </p>
                                
                                {/* Meta info */}
                                <div className="flex items-center justify-between text-xs text-slate-400">
                                    <div className="flex items-center gap-3">
                                        {goal.condition_link && (
                                            <span className="flex items-center gap-1">
                                                <AlertCircle className="w-3 h-3" />
                                                {goal.condition_link}
                                            </span>
                                        )}
                                        {goal.deadline && (
                                            <span className="flex items-center gap-1">
                                                <Clock className="w-3 h-3" />
                                                {goal.deadline}
                                            </span>
                                        )}
                                    </div>
                                    {/* Progress bar */}
                                    <div className="w-16 h-1.5 rounded-full bg-slate-100 overflow-hidden">
                                        <div 
                                            className="h-full bg-purple-500 rounded-full transition-all"
                                            style={{ width: `${goal.progress || 0}%` }}
                                        />
                                    </div>
                                </div>
                                
                                {/* Rationale (show on hover) */}
                                {goal.rationale && (
                                    <div className="mt-2 pt-2 border-t border-slate-50 opacity-0 group-hover:opacity-100 transition-opacity">
                                        <p className="text-[11px] text-slate-400 italic flex items-start gap-1">
                                            <Info className="w-3 h-3 mt-0.5 flex-shrink-0" />
                                            {goal.rationale}
                                        </p>
                                    </div>
                                )}
                            </div>
                        );
                    })
                )}
            </div>

            {/* Completed Goals */}
            {completedGoals.length > 0 && (
                <div className="pt-4 border-t border-slate-100">
                    <p className="text-xs font-medium text-slate-400 uppercase mb-2">Completed</p>
                    <div className="space-y-2">
                        {completedGoals.slice(0, 3).map((goal) => (
                            <div
                                key={goal.id}
                                className="flex items-center gap-3 p-2 rounded-lg opacity-60"
                            >
                                <CheckCircle2 className="w-5 h-5 text-green-500" />
                                <span className="text-sm text-slate-500 line-through">{goal.description}</span>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}
