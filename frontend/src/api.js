import axios from 'axios';

// Point to FastAPI backend
const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

const api = axios.create({
    baseURL: API_URL,
});

// Interceptor: Attach Token to every request
api.interceptors.request.use((config) => {
    const token = localStorage.getItem('token');
    if (token) {
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

export const register = async (email, password) => {
    const response = await api.post('/users/', {
        email: email,
        password: password
    });
    return response.data;
};

export const login = async (username, password) => {
    const formData = new FormData();
    formData.append('username', username);
    formData.append('password', password);
    const response = await api.post('/token', formData);
    return response.data;
};

export const getVitals = async (range = '-7d') => {
    const response = await api.get(`/vitals/me?range=${range}`);
    return response.data;
};

export const uploadDocument = async (file) => {
    console.log("uploadDocument called with:", file);
    const formData = new FormData();
    formData.append('file', file);
    try {
        const response = await api.post('/analyze/document', formData, {
            headers: { 'Content-Type': 'multipart/form-data' }
        });
        console.log("API Response:", response);
        return response.data;
    } catch (error) {
        console.error("API Error:", error);
        throw error;
    }
};

// ============== ADVANCED AGENTS API ==============

export const getWeeklyBriefing = async () => {
    const response = await api.get('/briefing/weekly');
    return response.data;
};

export const getHealthGoals = async () => {
    const response = await api.get('/goals/me');
    return response.data;
};

export const createHealthGoal = async (description) => {
    const response = await api.post('/goals/me', { description });
    return response.data;
};

export const updateGoalProgress = async (goalId, progress) => {
    const response = await api.put(`/goals/${goalId}?progress=${progress}`);
    return response.data;
};

export const getDailySummaries = async (days = 7) => {
    const response = await api.get(`/summaries/daily?days=${days}`);
    return response.data;
};

export const checkMedicationSafety = async (medName, symptom) => {
    const response = await api.post(`/safety/check?med_name=${encodeURIComponent(medName)}&symptom=${encodeURIComponent(symptom)}`);
    return response.data;
};

export const awardXP = async (taskName) => {
    const response = await api.post(`/gamification/xp?task_name=${encodeURIComponent(taskName)}`);
    return response.data;
};

// ============== CONTACTS API ==============

export const getEmergencyContacts = async () => {
    const response = await api.get('/emergency/contacts');
    return response.data;
};

export const addEmergencyContact = async (contact) => {
    const response = await api.post('/emergency/contacts', contact);
    return response.data;
};

export const deleteEmergencyContact = async (contactId) => {
    const response = await api.delete(`/emergency/contacts/${contactId}`);
    return response.data;
};

export const getPhysicians = async () => {
    const response = await api.get('/physicians/me');
    return response.data;
};

export const addPhysician = async (physician) => {
    const response = await api.post('/physicians/me', physician);
    return response.data;
};

export const deletePhysician = async (physicianId) => {
    const response = await api.delete(`/physicians/${physicianId}`);
    return response.data;
};

export default api;