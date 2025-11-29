try:
    from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
except ImportError:
    print("Warning: Qwen2VLForConditionalGeneration not found in transformers. Vision Agent will be disabled.")
    Qwen2VLForConditionalGeneration = None
    AutoProcessor = None
import torch
from PIL import Image
import io
import re
import time
import os

class VisionAgent:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(VisionAgent, cls).__new__(cls)
            cls._instance.model = None
            cls._instance.processor = None
            cls._instance.device = None
            cls._instance.load_model()
        return cls._instance

    def load_model(self):
        print("Loading Vision Agent (Qwen2-VL) on GPU...")
        try:
            # Check if CUDA is available
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            print(f"Using device: {self.device}")
            
            self.model = Qwen2VLForConditionalGeneration.from_pretrained(
                "Qwen/Qwen2-VL-2B-Instruct",
                torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
                device_map="auto",  # Automatically distribute across GPUs
                low_cpu_mem_usage=True,  # Optimize memory usage
            )
            self.processor = AutoProcessor.from_pretrained("Qwen/Qwen2-VL-2B-Instruct")
            print(f"Vision Agent Loaded Successfully on {self.device}.")
        except Exception as e:
            print(f"Failed to load Vision Agent model: {e}")
            print("Running in MOCK mode for Vision Agent.")
            self.model = None
            self.device = "cpu"

    def analyze_image(self, image_file, prompt_text="Describe this image"):
        if self.model is None:
            # Return mock markdown
            return """Couldn't perform analysis. VLM model not found."""

        try:
            from qwen_vl_utils import process_vision_info
        except ImportError:
            print("qwen_vl_utils not found. Returning mock data.")
            return """**Patient Name:** Mock Patient (Dependency Missing)
**Date:** 2024-11-24

### Lab Results
| Test Name | Value | Unit | Reference Range |
|-----------|-------|------|-----------------|
| Heart Rate | 70 | bpm | 60-100 |

### Clinical Findings
- System alert: Missing python package

### Raw Text
Mock Data (Dependency Missing)"""

        if isinstance(image_file, str):
            # It's a file path
            image = Image.open(image_file)
        else:
            # It's bytes
            image = Image.open(io.BytesIO(image_file))
        
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": prompt_text},
                ],
            }
        ]
        
        text = self.processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        
        image_inputs, video_inputs = process_vision_info(messages)
        
        inputs = self.processor(
            text=[text],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        )
        
        inputs = inputs.to(self.device)
        
        generated_ids = self.model.generate(
            **inputs, 
            max_new_tokens=1024,  # Reduced - medical records don't need 2048 tokens
            repetition_penalty=1.15,  # Penalize repeated tokens
            no_repeat_ngram_size=3,  # Prevent repeating 3-grams
            do_sample=False,  # Deterministic output for medical accuracy
        )
        
        generated_ids_trimmed = [
            out_ids[len(in_ids) :] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
        ]
        
        output_text = self.processor.batch_decode(
            generated_ids_trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
        )
        
        return output_text[0]

ingestor = VisionAgent()

def strip_html_tags(text: str) -> str:
    """Remove HTML tags from text, leaving only the content."""
    # Remove HTML tags but keep the text content
    clean = re.sub(r'<[^>]+>', '', text)
    # Remove excessive whitespace
    clean = re.sub(r'\n\s*\n\s*\n+', '\n\n', clean)
    return clean.strip()

def extract_medical_data(image_path: str, user_id: int = None) -> dict:
    """
    Extracts medical data from the given image path using the Vision Agent.
    Supports PDF files by converting ALL pages to images and performing OCR.
    Returns a dict with markdown-formatted text (better for LLM reasoning).
    """
    # Markdown Prompt
    markdown_prompt = """
    You are a medical transcriptionist. Your task is to transcribe the medical record from the image into markdown format. The medical record may be in a tabular format, an image, a text document, or something similar, or a combination of these.
    
    IMPORTANT: Clearly distinguish between the PATIENT (the person being tested/treated) and any REFERRING PHYSICIAN or DOCTOR who signed the document.
    
    Output your response in the following format:
    
    ### Patient Name
    [Patient Name - the person receiving care]
    
    ### Date
    [Date of test/visit]
    
    ### Referring Physician (if mentioned)
    [Doctor's name who ordered tests or is treating the patient, if present]

    ### Clinical Findings / Lab Results
    - [finding 1]
    - [finding 2]
    
    ### Raw Text / Additional Details
    [Enter all other details here. It could be just text OCR, or it could be image analysis, like echocardiogram, EKG, etc.]
    
    Remember: Output PLAIN MARKDOWN only, NO HTML tags like <h5>, <span>, <hr>, etc. If a table is found, output it as a markdown table to show structure.
    """

    content_to_save = ""
    page_count = 0

    try:
        if image_path.lower().endswith(".pdf"):
            import fitz  # PyMuPDF
            doc = fitz.open(image_path)
            print(f"Processing PDF with {len(doc)} pages...")
            
            all_pages_md = ""

            for i, page in enumerate(doc):
                print(f"OCR Processing Page {i+1}/{len(doc)}...")
                pix = page.get_pixmap()
                img_data = pix.tobytes("png")
                
                # OCR with Markdown output
                page_md = ingestor.analyze_image(img_data, markdown_prompt)
                # Clean HTML if present
                page_md = strip_html_tags(page_md)
                
                print(f"[DEBUG] Page {i+1} Response (first 300 chars):")
                print(page_md[:300])
                
                all_pages_md += f"\n\n---\n## Page {i+1}\n---\n{page_md}\n"
            
            content_to_save = all_pages_md
            page_count = len(doc)
        else: # Fallback for single images
            print("Processing single image...")
            md = ingestor.analyze_image(image_path, markdown_prompt)
            # Clean HTML if present
            md = strip_html_tags(md)
            
            print(f"[DEBUG] Single Image Response (first 300 chars):")
            print(md[:300])
            
            content_to_save = md
            page_count = 1

    except ImportError:
        print("PyMuPDF (fitz) not found. Cannot process PDF.")
        return {"error": "PyMuPDF not installed"}
    except Exception as e:
        print(f"Error processing: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}

    # Save to Knowledge Base (user-specific directory)
    kb_base = "d:\\Aegis\\knowledge_base"
    
    # Create user-specific subdirectory
    if user_id:
        kb_dir = os.path.join(kb_base, f"user_{user_id}")
    else:
        kb_dir = os.path.join(kb_base, "anonymous")
    
    timestamp = int(time.time())
    filename = f"{timestamp}_medical_record.md"
    filepath = os.path.join(kb_dir, filename)
    
    try:
        # Ensure the directory exists
        os.makedirs(kb_dir, exist_ok=True)
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content_to_save)
        print(f"[INGESTOR] Saved record to Knowledge Base: {filepath}")
    except Exception as e:
        print(f"[INGESTOR ERROR] Failed to save to KB: {e}")
        filepath = None  # Indicate failure to save

    return {
        "markdown": content_to_save,
        "page_count": page_count,
        "status": "success",
        "kb_path": filepath
    }