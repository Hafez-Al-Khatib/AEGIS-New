import { useState, useEffect } from 'react';
import { 
    Phone, 
    User, 
    UserPlus, 
    Trash2, 
    AlertCircle, 
    Stethoscope,
    MessageCircle,
    Building2,
    Heart,
    Shield,
    X,
    Plus,
    Loader2
} from 'lucide-react';
import { 
    getEmergencyContacts, 
    addEmergencyContact, 
    deleteEmergencyContact,
    getPhysicians,
    addPhysician,
    deletePhysician
} from '../api';

export default function ContactsList() {
    const [activeTab, setActiveTab] = useState('emergency');
    const [emergencyContacts, setEmergencyContacts] = useState([]);
    const [physicians, setPhysicians] = useState([]);
    const [loading, setLoading] = useState(true);
    const [showAddModal, setShowAddModal] = useState(false);
    const [error, setError] = useState(null);

    // Form state
    const [newContact, setNewContact] = useState({
        name: '',
        phone_number: '',
        relationship: '',
        // Physician fields
        specialty: '',
        clinic: ''
    });

    useEffect(() => {
        fetchContacts();
    }, []);

    const fetchContacts = async () => {
        setLoading(true);
        setError(null);
        try {
            const [emergencyData, physiciansData] = await Promise.all([
                getEmergencyContacts().catch(() => []),
                getPhysicians().catch(() => [])
            ]);
            setEmergencyContacts(emergencyData || []);
            setPhysicians(physiciansData || []);
        } catch (err) {
            console.error('Failed to fetch contacts:', err);
            setError('Failed to load contacts');
        } finally {
            setLoading(false);
        }
    };

    const handleAddContact = async (e) => {
        e.preventDefault();
        setError(null);
        
        try {
            if (activeTab === 'emergency') {
                await addEmergencyContact({
                    name: newContact.name,
                    phone_number: newContact.phone_number,
                    relationship: newContact.relationship
                });
            } else {
                await addPhysician({
                    name: newContact.name,
                    phone: newContact.phone_number,
                    specialty: newContact.specialty,
                    clinic: newContact.clinic
                });
            }
            
            setShowAddModal(false);
            setNewContact({ name: '', phone_number: '', relationship: '', specialty: '', clinic: '' });
            fetchContacts();
        } catch (err) {
            console.error('Failed to add contact:', err);
            setError('Failed to add contact. Please try again.');
        }
    };

    const handleDeleteEmergencyContact = async (id) => {
        if (!confirm('Are you sure you want to remove this emergency contact?')) return;
        
        try {
            await deleteEmergencyContact(id);
            fetchContacts();
        } catch (err) {
            console.error('Failed to delete contact:', err);
            setError('Failed to delete contact');
        }
    };

    const handleDeletePhysician = async (id) => {
        if (!confirm('Are you sure you want to remove this physician?')) return;
        
        try {
            await deletePhysician(id);
            fetchContacts();
        } catch (err) {
            console.error('Failed to delete physician:', err);
            setError('Failed to delete physician');
        }
    };

    const EmergencyContactCard = ({ contact }) => (
        <div className="flex items-center justify-between p-4 bg-white rounded-xl border border-slate-200 hover:border-rose-200 hover:shadow-md transition-all group">
            <div className="flex items-center gap-4">
                <div className="p-3 bg-rose-100 rounded-xl">
                    <Heart className="w-5 h-5 text-rose-600" />
                </div>
                <div>
                    <h4 className="font-semibold text-slate-800">{contact.name}</h4>
                    <p className="text-sm text-slate-500">{contact.relationship}</p>
                    <div className="flex items-center gap-2 mt-1">
                        <Phone className="w-3 h-3 text-slate-400" />
                        <span className="text-sm text-slate-600">{contact.phone_number}</span>
                    </div>
                </div>
            </div>
            <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                <a 
                    href={`tel:${contact.phone_number}`}
                    className="p-2 bg-emerald-100 text-emerald-600 rounded-lg hover:bg-emerald-200 transition-colors"
                    title="Call"
                >
                    <Phone className="w-4 h-4" />
                </a>
                <button 
                    onClick={() => handleDeleteEmergencyContact(contact.id)}
                    className="p-2 bg-rose-100 text-rose-600 rounded-lg hover:bg-rose-200 transition-colors"
                    title="Remove"
                >
                    <Trash2 className="w-4 h-4" />
                </button>
            </div>
        </div>
    );

    const PhysicianCard = ({ physician }) => (
        <div className="flex items-center justify-between p-4 bg-white rounded-xl border border-slate-200 hover:border-teal-200 hover:shadow-md transition-all group">
            <div className="flex items-center gap-4">
                <div className="p-3 bg-teal-100 rounded-xl">
                    <Stethoscope className="w-5 h-5 text-teal-600" />
                </div>
                <div>
                    <h4 className="font-semibold text-slate-800">{physician.name}</h4>
                    <p className="text-sm text-teal-600 font-medium">{physician.specialty}</p>
                    {physician.clinic && (
                        <div className="flex items-center gap-1.5 mt-1">
                            <Building2 className="w-3 h-3 text-slate-400" />
                            <span className="text-sm text-slate-500">{physician.clinic}</span>
                        </div>
                    )}
                    {physician.phone && (
                        <div className="flex items-center gap-1.5 mt-0.5">
                            <Phone className="w-3 h-3 text-slate-400" />
                            <span className="text-sm text-slate-600">{physician.phone}</span>
                        </div>
                    )}
                </div>
            </div>
            <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                {physician.phone && (
                    <>
                        <a 
                            href={`tel:${physician.phone}`}
                            className="p-2 bg-emerald-100 text-emerald-600 rounded-lg hover:bg-emerald-200 transition-colors"
                            title="Call"
                        >
                            <Phone className="w-4 h-4" />
                        </a>
                        <a 
                            href={`https://wa.me/${physician.phone.replace(/[^0-9]/g, '')}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="p-2 bg-green-100 text-green-600 rounded-lg hover:bg-green-200 transition-colors"
                            title="WhatsApp"
                        >
                            <MessageCircle className="w-4 h-4" />
                        </a>
                    </>
                )}
                <button 
                    onClick={() => handleDeletePhysician(physician.id)}
                    className="p-2 bg-rose-100 text-rose-600 rounded-lg hover:bg-rose-200 transition-colors"
                    title="Remove"
                >
                    <Trash2 className="w-4 h-4" />
                </button>
            </div>
        </div>
    );

    return (
        <div className="card">
            {/* Header */}
            <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-3">
                    <div className="p-2.5 bg-gradient-to-br from-violet-500 to-purple-600 rounded-xl shadow-lg">
                        <User className="w-5 h-5 text-white" />
                    </div>
                    <div>
                        <h3 className="font-bold text-slate-800">My Contacts</h3>
                        <p className="text-xs text-slate-500">Emergency & Healthcare</p>
                    </div>
                </div>
                <button
                    onClick={() => setShowAddModal(true)}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-violet-100 text-violet-700 rounded-lg text-sm font-medium hover:bg-violet-200 transition-colors"
                >
                    <Plus className="w-4 h-4" />
                    Add
                </button>
            </div>

            {/* Tabs */}
            <div className="flex gap-2 mb-4">
                <button
                    onClick={() => setActiveTab('emergency')}
                    className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                        activeTab === 'emergency'
                            ? 'bg-rose-100 text-rose-700'
                            : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                    }`}
                >
                    <Shield className="w-4 h-4" />
                    Emergency ({emergencyContacts.length})
                </button>
                <button
                    onClick={() => setActiveTab('physicians')}
                    className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                        activeTab === 'physicians'
                            ? 'bg-teal-100 text-teal-700'
                            : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                    }`}
                >
                    <Stethoscope className="w-4 h-4" />
                    Physicians ({physicians.length})
                </button>
            </div>

            {/* Error Display */}
            {error && (
                <div className="flex items-center gap-2 p-3 mb-4 bg-rose-50 text-rose-700 rounded-lg text-sm">
                    <AlertCircle className="w-4 h-4" />
                    {error}
                </div>
            )}

            {/* Content */}
            {loading ? (
                <div className="flex items-center justify-center py-12">
                    <Loader2 className="w-6 h-6 text-violet-500 animate-spin" />
                </div>
            ) : (
                <div className="space-y-3 max-h-80 overflow-y-auto pr-1">
                    {activeTab === 'emergency' ? (
                        emergencyContacts.length > 0 ? (
                            emergencyContacts.map(contact => (
                                <EmergencyContactCard key={contact.id} contact={contact} />
                            ))
                        ) : (
                            <div className="text-center py-8">
                                <Shield className="w-12 h-12 text-slate-300 mx-auto mb-3" />
                                <p className="text-slate-500">No emergency contacts yet</p>
                                <p className="text-xs text-slate-400 mt-1">Add contacts who should be notified in emergencies</p>
                            </div>
                        )
                    ) : (
                        physicians.length > 0 ? (
                            physicians.map(physician => (
                                <PhysicianCard key={physician.id} physician={physician} />
                            ))
                        ) : (
                            <div className="text-center py-8">
                                <Stethoscope className="w-12 h-12 text-slate-300 mx-auto mb-3" />
                                <p className="text-slate-500">No physicians saved</p>
                                <p className="text-xs text-slate-400 mt-1">Save your healthcare providers for quick access</p>
                            </div>
                        )
                    )}
                </div>
            )}

            {/* Add Contact Modal */}
            {showAddModal && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
                    <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md animate-fadeIn">
                        <div className="flex items-center justify-between p-5 border-b">
                            <h3 className="font-bold text-lg text-slate-800">
                                Add {activeTab === 'emergency' ? 'Emergency Contact' : 'Physician'}
                            </h3>
                            <button 
                                onClick={() => setShowAddModal(false)}
                                className="p-1.5 hover:bg-slate-100 rounded-lg transition-colors"
                            >
                                <X className="w-5 h-5 text-slate-500" />
                            </button>
                        </div>
                        
                        <form onSubmit={handleAddContact} className="p-5 space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-slate-700 mb-1.5">
                                    Name
                                </label>
                                <input
                                    type="text"
                                    required
                                    value={newContact.name}
                                    onChange={(e) => setNewContact({...newContact, name: e.target.value})}
                                    className="w-full px-4 py-2.5 border border-slate-200 rounded-xl focus:ring-2 focus:ring-violet-500 focus:border-transparent transition-all"
                                    placeholder={activeTab === 'emergency' ? "John Doe" : "Dr. Jane Smith"}
                                />
                            </div>
                            
                            <div>
                                <label className="block text-sm font-medium text-slate-700 mb-1.5">
                                    Phone Number
                                </label>
                                <input
                                    type="tel"
                                    required
                                    value={newContact.phone_number}
                                    onChange={(e) => setNewContact({...newContact, phone_number: e.target.value})}
                                    className="w-full px-4 py-2.5 border border-slate-200 rounded-xl focus:ring-2 focus:ring-violet-500 focus:border-transparent transition-all"
                                    placeholder="+1 (555) 123-4567"
                                />
                            </div>
                            
                            {activeTab === 'emergency' ? (
                                <div>
                                    <label className="block text-sm font-medium text-slate-700 mb-1.5">
                                        Relationship
                                    </label>
                                    <select
                                        value={newContact.relationship}
                                        onChange={(e) => setNewContact({...newContact, relationship: e.target.value})}
                                        className="w-full px-4 py-2.5 border border-slate-200 rounded-xl focus:ring-2 focus:ring-violet-500 focus:border-transparent transition-all"
                                    >
                                        <option value="">Select relationship</option>
                                        <option value="Spouse">Spouse</option>
                                        <option value="Parent">Parent</option>
                                        <option value="Child">Child</option>
                                        <option value="Sibling">Sibling</option>
                                        <option value="Friend">Friend</option>
                                        <option value="Caregiver">Caregiver</option>
                                        <option value="Other">Other</option>
                                    </select>
                                </div>
                            ) : (
                                <>
                                    <div>
                                        <label className="block text-sm font-medium text-slate-700 mb-1.5">
                                            Specialty
                                        </label>
                                        <input
                                            type="text"
                                            value={newContact.specialty}
                                            onChange={(e) => setNewContact({...newContact, specialty: e.target.value})}
                                            className="w-full px-4 py-2.5 border border-slate-200 rounded-xl focus:ring-2 focus:ring-violet-500 focus:border-transparent transition-all"
                                            placeholder="Cardiology, General Practice, etc."
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-sm font-medium text-slate-700 mb-1.5">
                                            Clinic/Hospital
                                        </label>
                                        <input
                                            type="text"
                                            value={newContact.clinic}
                                            onChange={(e) => setNewContact({...newContact, clinic: e.target.value})}
                                            className="w-full px-4 py-2.5 border border-slate-200 rounded-xl focus:ring-2 focus:ring-violet-500 focus:border-transparent transition-all"
                                            placeholder="City Medical Center"
                                        />
                                    </div>
                                </>
                            )}
                            
                            <div className="flex gap-3 pt-2">
                                <button
                                    type="button"
                                    onClick={() => setShowAddModal(false)}
                                    className="flex-1 px-4 py-2.5 border border-slate-200 text-slate-700 rounded-xl font-medium hover:bg-slate-50 transition-colors"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="submit"
                                    className="flex-1 px-4 py-2.5 bg-gradient-to-r from-violet-500 to-purple-600 text-white rounded-xl font-medium hover:from-violet-600 hover:to-purple-700 transition-all shadow-lg shadow-violet-500/25"
                                >
                                    <span className="flex items-center justify-center gap-2">
                                        <UserPlus className="w-4 h-4" />
                                        Add Contact
                                    </span>
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
}
