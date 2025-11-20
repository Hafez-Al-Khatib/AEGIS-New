from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
from PIL import Image
import torch
import PyPDF2
import pydicom
from pydicom.data import get_testdata_files
import numpy as np
import json
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path
import os

# We use the 2B model because it's lightweight but excellent at OCR
MODEL_ID = "Qwen/Qwen2-VL-2B-Instruct"


class DocumentMemory:
    """
    In-memory storage system for document summaries and extracted information
    Uses semantic indexing for efficient retrieval
    """
    
    def __init__(self, max_documents: int = 1000):
        self.documents: Dict[str, dict] = {}
        self.max_documents = max_documents
        self.document_index: List[str] = []  # For FIFO removal if limit exceeded
        
    def store_document(self, 
                      doc_id: str,
                      content: str,
                      summary: str,
                      doc_type: str,
                      metadata: Dict = None) -> Dict:
        """
        Store a document summary and content in memory
        
        Args:
            doc_id: Unique document identifier
            content: Full extracted content
            summary: AI-generated summary
            doc_type: Type of document (medical_report, lab_result, prescription, etc.)
            metadata: Additional metadata (patient_id, date, etc.)
        """
        if len(self.documents) >= self.max_documents:
            # Remove oldest document (FIFO)
            oldest_id = self.document_index.pop(0)
            del self.documents[oldest_id]
        
        doc_record = {
            "id": doc_id,
            "content": content,
            "summary": summary,
            "type": doc_type,
            "metadata": metadata or {},
            "stored_at": datetime.now().isoformat(),
            "keywords": self._extract_keywords(summary)
        }
        
        self.documents[doc_id] = doc_record
        self.document_index.append(doc_id)
        
        return doc_record
    
    def retrieve_document(self, doc_id: str) -> Optional[Dict]:
        """Retrieve a document by ID"""
        return self.documents.get(doc_id)
    
    def search_by_keyword(self, keyword: str) -> List[Dict]:
        """Search documents by keyword"""
        results = []
        keyword_lower = keyword.lower()
        
        for doc in self.documents.values():
            if keyword_lower in doc["summary"].lower() or \
               any(keyword_lower in k.lower() for k in doc["keywords"]):
                results.append(doc)
        
        return results
    
    def search_by_type(self, doc_type: str) -> List[Dict]:
        """Search documents by type"""
        return [doc for doc in self.documents.values() if doc["type"] == doc_type]
    
    def search_by_patient(self, patient_id: str) -> List[Dict]:
        """Search documents by patient ID"""
        return [doc for doc in self.documents.values() 
                if doc.get("metadata", {}).get("patient_id") == patient_id]
    
    def list_all_documents(self, limit: int = 50) -> List[Dict]:
        """List all stored documents"""
        return list(self.documents.values())[-limit:]
    
    def get_summary(self) -> Dict:
        """Get summary statistics of stored documents"""
        return {
            "total_documents": len(self.documents),
            "document_types": self._count_by_type(),
            "storage_capacity": f"{len(self.documents)}/{self.max_documents}",
            "latest_documents": [doc["id"] for doc in self.documents.values()][-5:]
        }
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Simple keyword extraction from summary"""
        # Extract capitalized words as keywords
        words = text.split()
        keywords = [w.strip('.,!?;:') for w in words 
                   if len(w) > 3 and w[0].isupper()]
        return list(set(keywords))[:10]  # Return unique keywords, limit to 10
    
    def _count_by_type(self) -> Dict[str, int]:
        """Count documents by type"""
        counts = {}
        for doc in self.documents.values():
            doc_type = doc["type"]
            counts[doc_type] = counts.get(doc_type, 0) + 1
        return counts
    
    def clear_memory(self):
        """Clear all documents from memory"""
        self.documents.clear()
        self.document_index.clear()


class VisionAgent:
    """Enhanced Vision Agent with PDF and image processing"""
    _instance = None
    
    def __init__(self):
        print("Loading Ingestor Agent (Qwen2-VL)...")
        # Load efficiently on GPU if available, else CPU
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
        self.model = Qwen2VLForConditionalGeneration.from_pretrained(
            MODEL_ID, 
            torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
            device_map="auto"
        )
        self.processor = AutoProcessor.from_pretrained(MODEL_ID)
        self.memory = DocumentMemory()
        print("Ingestor Agent Ready.")

    def analyze_image(self, image_path: str, prompt_text: str = "Extract all text from this image."):
        """Analyze a single image"""
        image = Image.open(image_path)
        
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": prompt_text},
                ],
            }
        ]
        
        # Prepare inputs
        text = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        image_inputs, video_inputs = self.processor.process_vision_info(messages)
        inputs = self.processor(
            text=[text],
            images=image_inputs,
            padding=True,
            return_tensors="pt",
        ).to(self.device)

        # Generate output
        generated_ids = self.model.generate(**inputs, max_new_tokens=512)
        output_text = self.processor.batch_decode(
            generated_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False
        )
        
        return output_text[0]
    
    def process_pdf(self, pdf_path: str) -> str:
        """Extract text from PDF file"""
        text_content = []
        
        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                for page_num, page in enumerate(pdf_reader.pages):
                    text = page.extract_text()
                    text_content.append(f"--- Page {page_num + 1} ---\n{text}")
            
            return "\n".join(text_content)
        except Exception as e:
            return f"Error reading PDF: {str(e)}"
    
    def process_image(self, image_path: str) -> str:
        """Extract text from image"""
        prompt = """
        Carefully analyze this document/image. Extract ALL visible text.
        Maintain the structure and hierarchy of the information.
        """
        return self.analyze_image(image_path, prompt)
    
    def process_dicom(self, dicom_path: str) -> Dict:
        """
        Process DICOM medical image file
        Extracts metadata, pixel data, and clinical information
        
        Args:
            dicom_path: Path to DICOM (.dcm) file
            
        Returns:
            Dictionary with DICOM metadata and analysis
        """
        try:
            # Load DICOM file
            dicom_file = pydicom.dcmread(dicom_path)
            
            # Extract key metadata
            dicom_info = {
                "patient_name": str(dicom_file.get("PatientName", "Unknown")),
                "patient_id": str(dicom_file.get("PatientID", "Unknown")),
                "patient_age": str(dicom_file.get("PatientAge", "Unknown")),
                "patient_sex": str(dicom_file.get("PatientSex", "Unknown")),
                "modality": str(dicom_file.get("Modality", "Unknown")),
                "study_date": str(dicom_file.get("StudyDate", "Unknown")),
                "study_time": str(dicom_file.get("StudyTime", "Unknown")),
                "study_description": str(dicom_file.get("StudyDescription", "Unknown")),
                "series_description": str(dicom_file.get("SeriesDescription", "Unknown")),
                "series_number": str(dicom_file.get("SeriesNumber", "Unknown")),
                "institution_name": str(dicom_file.get("InstitutionName", "Unknown")),
                "referring_physician": str(dicom_file.get("ReferringPhysicianName", "Unknown")),
                "performing_physician": str(dicom_file.get("PerformingPhysicianName", "Unknown")),
                "body_part": str(dicom_file.get("BodyPartExamined", "Unknown")),
                "manufacturer": str(dicom_file.get("Manufacturer", "Unknown")),
                "manufacturer_model": str(dicom_file.get("ManufacturerModelName", "Unknown")),
            }
            
            # Handle pixel data if available
            pixel_data_info = {}
            if hasattr(dicom_file, "pixel_array"):
                try:
                    pixel_array = dicom_file.pixel_array
                    pixel_data_info = {
                        "image_shape": str(pixel_array.shape),
                        "pixel_count": int(np.prod(pixel_array.shape)) if len(pixel_array.shape) > 0 else 0,
                        "min_value": float(np.min(pixel_array)),
                        "max_value": float(np.max(pixel_array)),
                        "mean_value": float(np.mean(pixel_array))
                    }
                    
                    # Convert pixel array to image for analysis
                    if len(pixel_array.shape) == 2:
                        # Grayscale image (common for medical imaging)
                        # Normalize to 0-255 range for PIL
                        normalized = ((pixel_array - np.min(pixel_array)) / 
                                    (np.max(pixel_array) - np.min(pixel_array)) * 255).astype(np.uint8)
                        img = Image.fromarray(normalized)
                    elif len(pixel_array.shape) == 3:
                        # RGB or similar
                        img = Image.fromarray((pixel_array / 255).astype(np.uint8))
                    else:
                        img = None
                    
                    # Analyze the image if possible
                    if img:
                        temp_img_path = f"temp_dicom_{datetime.now().timestamp()}.png"
                        img.save(temp_img_path)
                        image_analysis = self.analyze_image(
                            temp_img_path,
                            "Analyze this medical imaging scan. Describe any visible structures, abnormalities, or findings."
                        )
                        pixel_data_info["image_analysis"] = image_analysis
                        if os.path.exists(temp_img_path):
                            os.remove(temp_img_path)
                except Exception as e:
                    pixel_data_info["error"] = f"Could not process pixel data: {str(e)}"
            
            # Combine all information
            dicom_analysis = {
                "metadata": dicom_info,
                "pixel_data": pixel_data_info,
                "file_size": os.path.getsize(dicom_path),
                "processing_timestamp": datetime.now().isoformat()
            }
            
            return dicom_analysis
            
        except Exception as e:
            return {"error": f"Error processing DICOM file: {str(e)}"}
    
    def ingest_document(self, 
                       file_path: str, 
                       doc_type: str = "unknown",
                       patient_id: Optional[str] = None,
                       summarize: bool = True) -> Dict:
        """
        Ingest a document (PDF, image, or DICOM) and store in memory
        
        Args:
            file_path: Path to PDF, image, or DICOM file
            doc_type: Type of document (medical_report, lab_result, prescription, imaging, dicom_scan, etc.)
            patient_id: Optional patient ID for association
            summarize: Whether to generate summary
            
        Returns:
            Dictionary with extracted content, summary, and memory storage result
        """
        file_ext = Path(file_path).suffix.lower()
        
        # Extract content based on file type
        if file_ext == '.pdf':
            content = self.process_pdf(file_path)
        elif file_ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']:
            content = self.process_image(file_path)
        elif file_ext in ['.dcm', '.dicom']:
            # Process DICOM file
            dicom_data = self.process_dicom(file_path)
            if "error" in dicom_data:
                return {"error": dicom_data["error"]}
            # Convert DICOM analysis to text format
            content = json.dumps(dicom_data, indent=2)
            doc_type = "dicom_scan"  # Override doc_type for DICOM
        else:
            return {"error": f"Unsupported file type: {file_ext}"}
        
        # Generate summary if requested
        summary = ""
        if summarize:
            summary = self._generate_summary(content, doc_type)
        
        # Create document ID
        doc_id = f"{doc_type}_{datetime.now().timestamp()}"
        
        # Store in memory
        metadata = {"patient_id": patient_id} if patient_id else {}
        stored_doc = self.memory.store_document(
            doc_id=doc_id,
            content=content,
            summary=summary,
            doc_type=doc_type,
            metadata=metadata
        )
        
        return {
            "status": "success",
            "document_id": doc_id,
            "content": content,
            "summary": summary,
            "stored": stored_doc,
            "file_type": file_ext
        }
    
    def _generate_summary(self, content: str, doc_type: str) -> str:
        """Generate AI summary of document content"""
        # For now, use extractive summarization
        # In production, integrate with LLM MCP for better summaries
        lines = content.split('\n')
        important_lines = [line for line in lines if line.strip() and len(line) > 20]
        
        # Take first 10 important lines as summary
        summary = "\n".join(important_lines[:10])
        
        if len(content) > 500:
            summary += f"\n\n[Document contains {len(content)} characters]"
        
        return summary
    
    def search_memory(self, query: str, search_type: str = "keyword") -> List[Dict]:
        """
        Search the document memory
        
        Args:
            query: Search query
            search_type: "keyword", "type", or "patient"
            
        Returns:
            List of matching documents
        """
        if search_type == "keyword":
            return self.memory.search_by_keyword(query)
        elif search_type == "type":
            return self.memory.search_by_type(query)
        elif search_type == "patient":
            return self.memory.search_by_patient(query)
        return []
    
    def get_memory_stats(self) -> Dict:
        """Get memory statistics"""
        return self.memory.get_summary()
    
    def clear_memory(self):
        """Clear all stored documents"""
        self.memory.clear_memory()


# Singleton to prevent reloading model constantly
vision_agent = VisionAgent()


def extract_medical_text(file_path: str, patient_id: Optional[str] = None) -> Dict:
    """
    Ingest medical document (PDF or image), summarize, and store in memory
    
    Args:
        file_path: Path to medical document (PDF or image)
        patient_id: Optional patient ID
        
    Returns:
        Dictionary with extracted content, summary, and document ID
    """
    result = vision_agent.ingest_document(
        file_path=file_path,
        doc_type="medical_report",
        patient_id=patient_id,
        summarize=True
    )
    return result


def search_patient_documents(patient_id: str) -> List[Dict]:
    """Search all documents for a specific patient"""
    return vision_agent.search_memory(patient_id, search_type="patient")


def get_memory_info() -> Dict:
    """Get information about stored documents in memory"""
    return vision_agent.get_memory_stats()