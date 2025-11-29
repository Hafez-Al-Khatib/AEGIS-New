
import { useState, useEffect } from 'react';
import { uploadDocument } from '../api';
import { Upload, FileText, BrainCircuit, AlertTriangle, CheckCircle, Loader2, Stethoscope, Phone, MapPin, Activity, Search } from 'lucide-react';

export default function AgentAnalysis() {
    const [file, setFile] = useState(null);
    const [result, setResult] = useState(null);
    const [loading, setLoading] = useState(false);
    const [dragActive, setDragActive] = useState(false);

    const handleDrag = (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (e.type === "dragenter" || e.type === "dragover") {
            setDragActive(true);
        } else if (e.type === "dragleave") {
            setDragActive(false);
        }
    };

    const handleDrop = (e) => {
        e.preventDefault();
        e.stopPropagation();
        setDragActive(false);
        if (e.dataTransfer.files && e.dataTransfer.files[0]) {
            setFile(e.dataTransfer.files[0]);
        }
    };

    const handleChange = (e) => {
        e.preventDefault();
        if (e.target.files && e.target.files[0]) {
            setFile(e.target.files[0]);
        }
    };

    const handleAnalyze = async () => {
        if (!file) return;
        setLoading(true);
        setResult(null);

        try {
            const data = await uploadDocument(file);
            setResult(data);
        } catch (error) {
            console.error("Analysis Failed:", error);
            alert("Analysis Failed: " + error.message);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="p-8 max-w-7xl mx-auto space-y-8">
            <div className="text-center space-y-4">
                <h1 className="text-4xl font-bold text-slate-900 tracking-tight">Medical Document Analysis</h1>
                <p className="text-slate-500 max-w-2xl mx-auto">
                    Upload medical records for automated transcription and analysis. Documents are saved to your Knowledge Base for future reference via Sentinel Chat.
                </p>
            </div>

            {/* Upload Section */}
            <div
                className={`card border-2 border-dashed transition-all duration-300 ${dragActive ? 'border-teal-500 bg-teal-50/50' : 'border-slate-200 hover:border-teal-300'}`}
                onDragEnter={handleDrag}
                onDragLeave={handleDrag}
                onDragOver={handleDrag}
                onDrop={handleDrop}
            >
                <input
                    type="file"
                    onChange={handleChange}
                    className="hidden"
                    id="file-upload"
                    accept="image/*,.pdf"
                />
                <label htmlFor="file-upload" className="cursor-pointer flex flex-col items-center gap-6 py-12">
                    <div className={`p-6 rounded-full transition-colors ${file ? 'bg-emerald-100 text-emerald-600' : 'bg-teal-50 text-teal-600'}`}>
                        {file ? <CheckCircle size={48} /> : <Upload size={48} />}
                    </div>
                    <div className="text-center space-y-2">
                        <span className="text-xl font-semibold text-slate-700 block">
                            {file ? file.name : "Drop medical record here"}
                        </span>
                        <span className="text-sm text-slate-400">
                            {file ? "Ready for analysis" : "or click to browse (JPG, PNG, PDF)"}
                        </span>
                    </div>
                </label>

                {file && (
                    <div className="flex justify-center pb-8">
                        <button
                            onClick={handleAnalyze}
                            disabled={loading}
                            className="btn-primary flex items-center gap-2"
                        >
                            {loading ? <Loader2 className="animate-spin" /> : <BrainCircuit />}
                            {loading ? "Agents Processing..." : "Start Multi-Agent Analysis"}
                        </button>
                    </div>
                )}
            </div>

            {/* Results */}
            {result && (
                <div className="space-y-6">
                    {/* Success Banner */}
                    <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-xl flex items-start gap-4">
                        <div className="p-2 bg-emerald-100 text-emerald-600 rounded-full">
                            <CheckCircle size={24} />
                        </div>
                        <div className="flex-1">
                            <h3 className="font-bold text-emerald-700">Document Processed Successfully</h3>
                            <p className="text-sm text-emerald-600 mt-1">
                                {result.message} ({result.page_count} page{result.page_count > 1 ? 's' : ''})
                            </p>
                            <p className="text-xs text-emerald-500 mt-2 font-mono">
                                Saved to: {result.kb_path}
                            </p>
                        </div>
                    </div>

                    {/* Medical Record Analysis */}
                    <div className="card space-y-4 border-l-4 border-l-teal-500 min-h-[600px]">
                        <div className="flex items-center justify-between pb-4 border-b border-slate-100">
                            <div className="flex items-center gap-3">
                                <div className="p-2 bg-teal-100 text-teal-600 rounded-lg">
                                    <FileText size={24} />
                                </div>
                                <div>
                                    <h2 className="font-bold text-slate-800">Medical Record Transcription</h2>
                                    <p className="text-xs text-slate-400">Automated OCR & Data Extraction</p>
                                </div>
                            </div>
                            <div className="text-xs text-slate-500">
                                Ask Sentinel Chat about this record
                            </div>
                        </div>

                        <div className="prose prose-slate prose-lg max-w-none">
                            <div className="whitespace-pre-wrap text-slate-600 leading-relaxed">
                                {result.analysis}
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
