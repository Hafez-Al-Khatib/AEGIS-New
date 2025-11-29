import { useState } from 'react';
import { checkMedicationSafety } from '../api';
import { 
    Pill, 
    Search, 
    AlertTriangle, 
    CheckCircle2, 
    Loader2,
    Info
} from 'lucide-react';

export default function MedicationSafetyChecker() {
    const [medName, setMedName] = useState('');
    const [symptom, setSymptom] = useState('');
    const [result, setResult] = useState(null);
    const [loading, setLoading] = useState(false);

    const handleCheck = async () => {
        if (!medName.trim() || !symptom.trim()) return;
        
        setLoading(true);
        setResult(null);
        
        try {
            const data = await checkMedicationSafety(medName, symptom);
            setResult(data);
        } catch (error) {
            setResult({ result: 'Error checking medication safety' });
            console.error('Error:', error);
        } finally {
            setLoading(false);
        }
    };

    // Determine result type for styling
    const getResultType = () => {
        if (!result) return null;
        const text = result.result.toLowerCase();
        if (text.includes('known side effect') || text.includes('is associated')) return 'warning';
        if (text.includes('not found') || text.includes('no known')) return 'safe';
        return 'info';
    };

    const resultType = getResultType();

    return (
        <div className="card p-6 space-y-4">
            {/* Header */}
            <div className="flex items-center gap-3">
                <div className="p-2 rounded-xl bg-rose-100">
                    <Pill className="w-5 h-5 text-rose-600" />
                </div>
                <div>
                    <h3 className="font-semibold text-slate-800">Medication Safety</h3>
                    <p className="text-xs text-slate-400">Check side effects (OpenFDA)</p>
                </div>
            </div>

            {/* Input Fields */}
            <div className="space-y-3">
                <input
                    type="text"
                    value={medName}
                    onChange={(e) => setMedName(e.target.value)}
                    placeholder="Medication name (e.g., Aspirin)"
                    className="w-full px-3 py-2 rounded-lg border border-slate-200 focus:border-rose-500 focus:ring-2 focus:ring-rose-500/20 outline-none text-sm"
                />
                <input
                    type="text"
                    value={symptom}
                    onChange={(e) => setSymptom(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleCheck()}
                    placeholder="Symptom to check (e.g., bleeding)"
                    className="w-full px-3 py-2 rounded-lg border border-slate-200 focus:border-rose-500 focus:ring-2 focus:ring-rose-500/20 outline-none text-sm"
                />
                <button
                    onClick={handleCheck}
                    disabled={loading || !medName.trim() || !symptom.trim()}
                    className="w-full flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-rose-500 text-white text-sm font-medium hover:bg-rose-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                    {loading ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                        <Search className="w-4 h-4" />
                    )}
                    Check Safety
                </button>
            </div>

            {/* Result */}
            {result && (
                <div className={`p-4 rounded-xl border ${
                    resultType === 'warning' 
                        ? 'bg-amber-50 border-amber-200' 
                        : resultType === 'safe'
                        ? 'bg-green-50 border-green-200'
                        : 'bg-blue-50 border-blue-200'
                }`}>
                    <div className="flex items-start gap-3">
                        {resultType === 'warning' ? (
                            <AlertTriangle className="w-5 h-5 text-amber-500 mt-0.5 shrink-0" />
                        ) : resultType === 'safe' ? (
                            <CheckCircle2 className="w-5 h-5 text-green-500 mt-0.5 shrink-0" />
                        ) : (
                            <Info className="w-5 h-5 text-blue-500 mt-0.5 shrink-0" />
                        )}
                        <div>
                            <p className={`text-sm font-medium ${
                                resultType === 'warning' 
                                    ? 'text-amber-800' 
                                    : resultType === 'safe'
                                    ? 'text-green-800'
                                    : 'text-blue-800'
                            }`}>
                                {result.medication} + {result.symptom}
                            </p>
                            <p className={`text-sm mt-1 ${
                                resultType === 'warning' 
                                    ? 'text-amber-700' 
                                    : resultType === 'safe'
                                    ? 'text-green-700'
                                    : 'text-blue-700'
                            }`}>
                                {result.result}
                            </p>
                        </div>
                    </div>
                </div>
            )}

            {/* Disclaimer */}
            <p className="text-xs text-slate-400 text-center">
                Data from FDA Adverse Event Reporting System. Always consult a healthcare professional.
            </p>
        </div>
    );
}
